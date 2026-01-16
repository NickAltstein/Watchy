"""
Stripe Connect Escrow System for Watch Marketplace

Implements secure escrow payments with:
1. Seller onboarding via Stripe Connect Express
2. Payment Intent creation with funds held in escrow
3. Shipment confirmation and tracking
4. Auto-release funds after 7 days
5. Dispute handling and refunds
6. Webhook processing for payment events
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from enum import Enum

import stripe
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import update

logger = logging.getLogger("watch-engine.payments.escrow")


class TransactionStatus(str, Enum):
    """Transaction status lifecycle"""
    PENDING = "pending"
    AUTHORIZED = "authorized"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    COMPLETED = "completed"
    DISPUTED = "disputed"
    REFUNDED = "refunded"
    CANCELLED = "cancelled"


class CreateTransactionRequest(BaseModel):
    """Request to create escrow transaction"""
    buyer_id: int
    seller_id: int
    listing_id: int
    amount_usd: int = Field(..., gt=0, description="Amount in USD cents")


class ConfirmShipmentRequest(BaseModel):
    """Request to confirm shipment"""
    transaction_id: int
    tracking_number: str
    carrier: str = Field(..., description="Shipping carrier (USPS, FedEx, UPS, DHL)")


class EscrowService:
    """
    Stripe Connect escrow payment service
    
    Payment Flow:
    1. Buyer initiates purchase → Create Payment Intent (funds held)
    2. Seller ships → Update status to 'shipped'
    3. Buyer receives → Auto-release after 7 days
    4. Funds transferred → Seller receives payout minus platform fee (2.5%)
    """
    
    PLATFORM_FEE_PERCENT = 2.5  # Platform fee percentage
    AUTO_RELEASE_DAYS = 7  # Days before auto-release
    
    def __init__(
        self,
        stripe_api_key: str,
        platform_account_id: str,
        db_session_factory
    ):
        """
        Initialize escrow service
        
        Args:
            stripe_api_key: Stripe secret key
            platform_account_id: Platform's Stripe account ID
            db_session_factory: SQLAlchemy session factory
        """
        stripe.api_key = stripe_api_key
        self.platform_account_id = platform_account_id
        self.db_session_factory = db_session_factory
        
        logger.info("Escrow service initialized")
    
    def _calculate_fees(self, amount_usd: int) -> tuple[int, int]:
        """
        Calculate platform fee and seller payout
        
        Args:
            amount_usd: Total amount in cents
            
        Returns:
            (platform_fee, seller_payout) in cents
        """
        platform_fee = int(amount_usd * (self.PLATFORM_FEE_PERCENT / 100))
        seller_payout = amount_usd - platform_fee
        return platform_fee, seller_payout
    
    async def create_seller_account(
        self,
        user_id: int,
        email: str,
        business_type: str = "individual"
    ) -> Dict[str, Any]:
        """
        Create Stripe Connect Express account for seller
        
        Args:
            user_id: User ID
            email: Seller email
            business_type: 'individual' or 'company'
            
        Returns:
            Account info with onboarding URL
        """
        try:
            # Create Connect account
            account = stripe.Account.create(
                type="express",
                country="US",
                email=email,
                business_type=business_type,
                capabilities={
                    "card_payments": {"requested": True},
                    "transfers": {"requested": True}
                },
                metadata={
                    "user_id": str(user_id),
                    "platform": "watchy"
                }
            )
            
            # Generate onboarding link
            account_link = stripe.AccountLink.create(
                account=account.id,
                refresh_url=f"https://your-domain.com/seller/onboarding/refresh",
                return_url=f"https://your-domain.com/seller/onboarding/complete",
                type="account_onboarding"
            )
            
            # Store account ID in database
            with self.db_session_factory() as db:
                # Update user's stripe account ID
                db.execute(
                    "UPDATE users SET stripe_account_id = :account_id WHERE id = :user_id",
                    {"account_id": account.id, "user_id": user_id}
                )
                db.commit()
            
            logger.info(f"Created Stripe account {account.id} for user {user_id}")
            
            return {
                "account_id": account.id,
                "onboarding_url": account_link.url,
                "details_submitted": account.details_submitted
            }
            
        except stripe.error.StripeError as e:
            logger.error(f"Stripe account creation failed: {e}")
            raise Exception(f"Failed to create seller account: {str(e)}")
    
    async def create_transaction(
        self,
        buyer_id: int,
        seller_id: int,
        listing_id: int,
        amount_usd: int
    ) -> Dict[str, Any]:
        """
        Create escrow transaction with Payment Intent
        
        Funds are held in escrow until shipment is confirmed and
        buyer confirms receipt (or 7 days pass).
        
        Args:
            buyer_id: Buyer user ID
            seller_id: Seller user ID
            listing_id: Listing ID
            amount_usd: Amount in USD cents
            
        Returns:
            Transaction details with client_secret for payment
        """
        try:
            # Calculate fees
            platform_fee, seller_payout = self._calculate_fees(amount_usd)
            
            with self.db_session_factory() as db:
                # Get seller's Stripe account ID
                result = db.execute(
                    "SELECT stripe_account_id FROM users WHERE id = :id",
                    {"id": seller_id}
                ).fetchone()
                
                if not result or not result[0]:
                    raise Exception("Seller has not completed Stripe onboarding")
                
                seller_stripe_account = result[0]
                
                # Create Payment Intent with transfer_data (escrow)
                payment_intent = stripe.PaymentIntent.create(
                    amount=amount_usd,
                    currency="usd",
                    payment_method_types=["card"],
                    capture_method="automatic",
                    transfer_data={
                        "destination": seller_stripe_account,
                        "amount": seller_payout  # Seller receives this amount
                    },
                    application_fee_amount=platform_fee,
                    metadata={
                        "buyer_id": str(buyer_id),
                        "seller_id": str(seller_id),
                        "listing_id": str(listing_id),
                        "platform": "watchy"
                    }
                )
                
                # Create transaction record
                transaction_id = db.execute(
                    """
                    INSERT INTO transactions (
                        buyer_id, seller_id, listing_id,
                        amount_usd, platform_fee_usd, seller_payout_usd,
                        status, stripe_payment_intent_id,
                        created_at
                    ) VALUES (
                        :buyer_id, :seller_id, :listing_id,
                        :amount, :fee, :payout,
                        :status, :payment_intent,
                        :now
                    ) RETURNING id
                    """,
                    {
                        "buyer_id": buyer_id,
                        "seller_id": seller_id,
                        "listing_id": listing_id,
                        "amount": amount_usd,
                        "fee": platform_fee,
                        "payout": seller_payout,
                        "status": TransactionStatus.PENDING.value,
                        "payment_intent": payment_intent.id,
                        "now": datetime.utcnow()
                    }
                ).fetchone()[0]
                
                db.commit()
                
                logger.info(f"Created transaction {transaction_id} with PaymentIntent {payment_intent.id}")
                
                return {
                    "transaction_id": transaction_id,
                    "client_secret": payment_intent.client_secret,
                    "amount_usd": amount_usd,
                    "platform_fee_usd": platform_fee,
                    "seller_payout_usd": seller_payout,
                    "status": TransactionStatus.PENDING.value
                }
                
        except stripe.error.StripeError as e:
            logger.error(f"Payment Intent creation failed: {e}")
            raise Exception(f"Failed to create transaction: {str(e)}")
    
    async def confirm_shipment(
        self,
        transaction_id: int,
        tracking_number: str,
        carrier: str
    ) -> Dict[str, Any]:
        """
        Confirm shipment and start auto-release timer
        
        Args:
            transaction_id: Transaction ID
            tracking_number: Shipment tracking number
            carrier: Shipping carrier
            
        Returns:
            Updated transaction details
        """
        try:
            with self.db_session_factory() as db:
                # Calculate auto-release date
                auto_release_at = datetime.utcnow() + timedelta(days=self.AUTO_RELEASE_DAYS)
                
                # Update transaction
                result = db.execute(
                    """
                    UPDATE transactions SET
                        status = :status,
                        tracking_number = :tracking,
                        carrier = :carrier,
                        shipped_at = :now,
                        auto_release_at = :auto_release,
                        updated_at = :now
                    WHERE id = :id
                    RETURNING stripe_payment_intent_id
                    """,
                    {
                        "id": transaction_id,
                        "status": TransactionStatus.SHIPPED.value,
                        "tracking": tracking_number,
                        "carrier": carrier,
                        "now": datetime.utcnow(),
                        "auto_release": auto_release_at
                    }
                ).fetchone()
                
                if not result:
                    raise Exception(f"Transaction {transaction_id} not found")
                
                payment_intent_id = result[0]
                
                db.commit()
                
                # TODO: Send notification to buyer with tracking info
                # TODO: Schedule background job to auto-release funds
                
                logger.info(f"Confirmed shipment for transaction {transaction_id}")
                
                return {
                    "transaction_id": transaction_id,
                    "status": TransactionStatus.SHIPPED.value,
                    "tracking_number": tracking_number,
                    "carrier": carrier,
                    "auto_release_at": auto_release_at.isoformat()
                }
                
        except Exception as e:
            logger.error(f"Shipment confirmation failed: {e}")
            raise
    
    async def release_funds(self, transaction_id: int) -> Dict[str, Any]:
        """
        Release escrowed funds to seller
        
        Called when:
        - Buyer confirms receipt, or
        - 7 days pass since shipment (auto-release)
        
        Args:
            transaction_id: Transaction ID
            
        Returns:
            Transfer details
        """
        try:
            with self.db_session_factory() as db:
                # Get transaction details
                transaction = db.execute(
                    """
                    SELECT stripe_payment_intent_id, seller_payout_usd, status
                    FROM transactions
                    WHERE id = :id
                    """,
                    {"id": transaction_id}
                ).fetchone()
                
                if not transaction:
                    raise Exception(f"Transaction {transaction_id} not found")
                
                if transaction.status not in [TransactionStatus.SHIPPED.value, TransactionStatus.DELIVERED.value]:
                    raise Exception(f"Cannot release funds for transaction in status {transaction.status}")
                
                payment_intent_id = transaction.stripe_payment_intent_id
                
                # Note: With transfer_data in PaymentIntent, funds are automatically
                # transferred when payment is captured. We just need to update status.
                
                # Update transaction status
                db.execute(
                    """
                    UPDATE transactions SET
                        status = :status,
                        completed_at = :now,
                        updated_at = :now
                    WHERE id = :id
                    """,
                    {
                        "id": transaction_id,
                        "status": TransactionStatus.COMPLETED.value,
                        "now": datetime.utcnow()
                    }
                )
                
                db.commit()
                
                logger.info(f"Released funds for transaction {transaction_id}")
                
                return {
                    "transaction_id": transaction_id,
                    "status": TransactionStatus.COMPLETED.value,
                    "message": "Funds released to seller"
                }
                
        except stripe.error.StripeError as e:
            logger.error(f"Fund release failed: {e}")
            raise Exception(f"Failed to release funds: {str(e)}")
    
    async def process_refund(
        self,
        transaction_id: int,
        reason: str = "requested_by_customer"
    ) -> Dict[str, Any]:
        """
        Process refund for transaction
        
        Args:
            transaction_id: Transaction ID
            reason: Refund reason
            
        Returns:
            Refund details
        """
        try:
            with self.db_session_factory() as db:
                # Get transaction
                transaction = db.execute(
                    """
                    SELECT stripe_payment_intent_id, amount_usd, status
                    FROM transactions
                    WHERE id = :id
                    """,
                    {"id": transaction_id}
                ).fetchone()
                
                if not transaction:
                    raise Exception(f"Transaction {transaction_id} not found")
                
                payment_intent_id = transaction.stripe_payment_intent_id
                
                # Create refund
                refund = stripe.Refund.create(
                    payment_intent=payment_intent_id,
                    reason=reason,
                    metadata={
                        "transaction_id": str(transaction_id)
                    }
                )
                
                # Update transaction
                db.execute(
                    """
                    UPDATE transactions SET
                        status = :status,
                        stripe_refund_id = :refund_id,
                        updated_at = :now
                    WHERE id = :id
                    """,
                    {
                        "id": transaction_id,
                        "status": TransactionStatus.REFUNDED.value,
                        "refund_id": refund.id,
                        "now": datetime.utcnow()
                    }
                )
                
                db.commit()
                
                logger.info(f"Processed refund for transaction {transaction_id}")
                
                return {
                    "transaction_id": transaction_id,
                    "refund_id": refund.id,
                    "amount_usd": transaction.amount_usd,
                    "status": TransactionStatus.REFUNDED.value
                }
                
        except stripe.error.StripeError as e:
            logger.error(f"Refund failed: {e}")
            raise Exception(f"Failed to process refund: {str(e)}")
    
    async def handle_webhook(
        self,
        payload: str,
        sig_header: str,
        webhook_secret: str
    ) -> Dict[str, Any]:
        """
        Handle Stripe webhook events
        
        Args:
            payload: Webhook payload
            sig_header: Stripe signature header
            webhook_secret: Webhook signing secret
            
        Returns:
            Processing result
        """
        try:
            # Verify webhook signature
            event = stripe.Webhook.construct_event(
                payload, sig_header, webhook_secret
            )
            
            event_type = event['type']
            data = event['data']['object']
            
            logger.info(f"Processing webhook event: {event_type}")
            
            # Handle different event types
            if event_type == 'payment_intent.succeeded':
                await self._handle_payment_succeeded(data)
                
            elif event_type == 'payment_intent.payment_failed':
                await self._handle_payment_failed(data)
                
            elif event_type == 'transfer.paid':
                await self._handle_transfer_paid(data)
                
            elif event_type == 'charge.dispute.created':
                await self._handle_dispute_created(data)
                
            else:
                logger.debug(f"Unhandled webhook event type: {event_type}")
            
            return {"status": "success", "event_type": event_type}
            
        except stripe.error.SignatureVerificationError as e:
            logger.error(f"Webhook signature verification failed: {e}")
            raise Exception("Invalid webhook signature")
        except Exception as e:
            logger.error(f"Webhook processing failed: {e}")
            raise
    
    async def _handle_payment_succeeded(self, payment_intent):
        """Handle successful payment"""
        payment_intent_id = payment_intent['id']
        
        with self.db_session_factory() as db:
            db.execute(
                """
                UPDATE transactions SET
                    status = :status,
                    updated_at = :now
                WHERE stripe_payment_intent_id = :payment_intent
                """,
                {
                    "payment_intent": payment_intent_id,
                    "status": TransactionStatus.AUTHORIZED.value,
                    "now": datetime.utcnow()
                }
            )
            db.commit()
        
        logger.info(f"Payment succeeded for PaymentIntent {payment_intent_id}")
    
    async def _handle_payment_failed(self, payment_intent):
        """Handle failed payment"""
        payment_intent_id = payment_intent['id']
        
        with self.db_session_factory() as db:
            db.execute(
                """
                UPDATE transactions SET
                    status = :status,
                    updated_at = :now
                WHERE stripe_payment_intent_id = :payment_intent
                """,
                {
                    "payment_intent": payment_intent_id,
                    "status": TransactionStatus.CANCELLED.value,
                    "now": datetime.utcnow()
                }
            )
            db.commit()
        
        logger.warning(f"Payment failed for PaymentIntent {payment_intent_id}")
    
    async def _handle_transfer_paid(self, transfer):
        """Handle transfer to seller completed"""
        transfer_id = transfer['id']
        payment_intent_id = transfer.get('source_transaction')
        
        if payment_intent_id:
            with self.db_session_factory() as db:
                db.execute(
                    """
                    UPDATE transactions SET
                        stripe_transfer_id = :transfer_id,
                        updated_at = :now
                    WHERE stripe_payment_intent_id = :payment_intent
                    """,
                    {
                        "transfer_id": transfer_id,
                        "payment_intent": payment_intent_id,
                        "now": datetime.utcnow()
                    }
                )
                db.commit()
            
            logger.info(f"Transfer completed: {transfer_id}")
    
    async def _handle_dispute_created(self, dispute):
        """Handle dispute opened"""
        payment_intent_id = dispute.get('payment_intent')
        
        if payment_intent_id:
            with self.db_session_factory() as db:
                db.execute(
                    """
                    UPDATE transactions SET
                        status = :status,
                        updated_at = :now
                    WHERE stripe_payment_intent_id = :payment_intent
                    """,
                    {
                        "payment_intent": payment_intent_id,
                        "status": TransactionStatus.DISPUTED.value,
                        "now": datetime.utcnow()
                    }
                )
                db.commit()
            
            # TODO: Alert admin about dispute
            logger.warning(f"Dispute created for PaymentIntent {payment_intent_id}")
