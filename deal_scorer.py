"""
Advanced Deal Scoring Engine with Multi-Factor Analysis

Provides sophisticated scoring for luxury watch deals with:
- Multi-factor analysis (condition, inclusions, seller, urgency)
- Risk assessment and red flag detection
- Arbitrage opportunity detection
- Transparent scoring explanations
- ROI and profit potential calculations
"""

import logging
from typing import Dict, List, Optional, Tuple, Literal
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field, validator

logger = logging.getLogger("watch-engine.deal_scorer")


class DealTier(str, Enum):
    """Deal classification tiers"""
    URGENT = "URGENT"      # 350+ points
    PUSH = "PUSH"          # 200-349 points
    NORMAL = "NORMAL"      # 100-199 points
    SKIP = "SKIP"          # 0-99 points
    OVERPRICED = "OVERPRICED"  # <0 points


class RiskLevel(str, Enum):
    """Risk assessment levels"""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ConditionGrade(str, Enum):
    """Watch condition grades"""
    NIB = "NIB"           # New in box
    UNWORN = "UNWORN"     # Unworn/mint
    EXCELLENT = "EXCELLENT"  # 9-10/10
    GOOD = "GOOD"         # 7-8/10
    FAIR = "FAIR"         # 5-6/10
    POOR = "POOR"         # <5/10
    UNKNOWN = "UNKNOWN"


class SellerType(str, Enum):
    """Seller reputation types"""
    VERIFIED_DEALER = "VERIFIED_DEALER"
    ESTABLISHED_DEALER = "ESTABLISHED_DEALER"
    PRIVATE_TRUSTED = "PRIVATE_TRUSTED"
    PRIVATE_NEW = "PRIVATE_NEW"
    UNKNOWN = "UNKNOWN"


class MarketTrend(str, Enum):
    """Market price trend direction"""
    RISING = "RISING"
    STABLE = "STABLE"
    FALLING = "FALLING"
    UNKNOWN = "UNKNOWN"


class DealFactors(BaseModel):
    """Input factors for deal scoring"""
    market_price: int = Field(..., gt=0, description="Current market price in USD")
    listing_price: int = Field(..., gt=0, description="Listing/asking price in USD")
    
    # Condition factors
    condition: ConditionGrade = Field(default=ConditionGrade.UNKNOWN)
    has_box: bool = Field(default=False)
    has_papers: bool = Field(default=False)
    has_warranty: bool = Field(default=False)
    is_full_set: bool = Field(default=False)
    
    # Seller factors
    seller_type: SellerType = Field(default=SellerType.UNKNOWN)
    seller_rating: Optional[float] = Field(default=None, ge=0, le=5)
    seller_transaction_count: int = Field(default=0, ge=0)
    
    # Urgency signals
    quick_sale_indicated: bool = Field(default=False)
    price_reduced: bool = Field(default=False)
    motivated_seller: bool = Field(default=False)
    
    # Market context
    market_trend: MarketTrend = Field(default=MarketTrend.UNKNOWN)
    comparable_count: int = Field(default=0, ge=0)
    rarity_score: int = Field(default=0, ge=0, le=30)
    
    # Risk factors
    too_cheap: bool = Field(default=False)
    vague_photos: bool = Field(default=False)
    new_seller_suspicious: bool = Field(default=False)
    payment_red_flags: bool = Field(default=False)
    contradictory_info: bool = Field(default=False)
    
    def model_post_init(self, __context):
        """Validate after all fields are set"""
        if self.listing_price > self.market_price * 3:
            logger.warning(f"Listing price ${self.listing_price} is >3x market price")


class ArbitrageOpportunity(BaseModel):
    """Arbitrage opportunity details"""
    source_platform: str
    target_platform: str
    buy_price: int
    sell_price: int
    source_fees: float
    target_fees: float
    shipping_cost: float
    insurance_cost: float
    total_costs: float
    gross_profit: int
    net_profit: int
    roi_percentage: float
    is_viable: bool


class RiskAssessment(BaseModel):
    """Deal risk assessment"""
    level: RiskLevel
    score: int = Field(ge=0, le=100)
    red_flags: List[str] = Field(default_factory=list)
    concerns: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)


class ScoringBreakdown(BaseModel):
    """Detailed scoring breakdown"""
    base_score: int
    condition_bonus: int
    inclusions_bonus: int
    seller_bonus: int
    urgency_bonus: int
    market_trend_adjustment: int
    rarity_bonus: int
    risk_penalty: int
    final_score: int
    discount_percentage: float


class DealScore(BaseModel):
    """Complete deal scoring result"""
    score: int = Field(ge=-500, le=500)
    tier: DealTier
    breakdown: ScoringBreakdown
    explanation: str
    risk_assessment: RiskAssessment
    arbitrage: Optional[ArbitrageOpportunity] = None
    confidence: int = Field(ge=0, le=100)
    timestamp: datetime = Field(default_factory=datetime.now)


class DealScorer:
    """
    Advanced deal scoring engine with multi-factor analysis.
    
    Scoring Formula:
    Base Score = ((market_price - listing_price) / market_price) * 1000
    
    Adjustments:
    + Condition bonus (0-20 points)
    + Full set bonus (0-15 points)
    + Seller reputation (0-10 points)
    + Urgency indicators (0-5 points)
    + Market momentum (-20 to +20 points)
    + Rarity factor (0-30 points)
    - Risk penalty (0-50 points)
    
    Final Score = clamp(Base Score + Adjustments, -500, 500)
    """
    
    # Configuration constants
    SCORE_MULTIPLIER = 1000
    MIN_SCORE = -500
    MAX_SCORE = 500
    
    # Tier thresholds
    TIER_THRESHOLDS = {
        DealTier.URGENT: 350,
        DealTier.PUSH: 200,
        DealTier.NORMAL: 100,
        DealTier.SKIP: 0,
    }
    
    # Condition bonuses
    CONDITION_BONUSES = {
        ConditionGrade.NIB: 20,
        ConditionGrade.UNWORN: 18,
        ConditionGrade.EXCELLENT: 15,
        ConditionGrade.GOOD: 10,
        ConditionGrade.FAIR: 5,
        ConditionGrade.POOR: 0,
        ConditionGrade.UNKNOWN: 0,
    }
    
    # Seller bonuses
    SELLER_BONUSES = {
        SellerType.VERIFIED_DEALER: 10,
        SellerType.ESTABLISHED_DEALER: 7,
        SellerType.PRIVATE_TRUSTED: 5,
        SellerType.PRIVATE_NEW: 0,
        SellerType.UNKNOWN: 0,
    }
    
    # Platform fees (percentage)
    PLATFORM_FEES = {
        "whatsapp": 0.0,
        "chrono24": 6.5,
        "ebay": 12.9,
        "private": 0.0,
    }
    
    def __init__(self):
        """Initialize the deal scorer"""
        logger.info("DealScorer initialized")
    
    def calculate_base_score(self, market_price: int, listing_price: int) -> Tuple[int, float]:
        """
        Calculate base score from price difference.
        
        Returns:
            Tuple of (base_score, discount_percentage)
        """
        if market_price <= 0:
            raise ValueError("Market price must be positive")
        
        discount_pct = ((market_price - listing_price) / market_price) * 100
        base_score = int(((market_price - listing_price) / market_price) * self.SCORE_MULTIPLIER)
        
        return base_score, discount_pct
    
    def calculate_condition_bonus(self, factors: DealFactors) -> int:
        """Calculate bonus points for condition"""
        bonus = self.CONDITION_BONUSES.get(factors.condition, 0)
        
        # Additional bonus for excellent condition with documentation
        if factors.condition in [ConditionGrade.NIB, ConditionGrade.UNWORN]:
            if factors.has_papers:
                bonus += 2
            if factors.has_warranty:
                bonus += 3
        
        return min(bonus, 25)  # Cap at 25
    
    def calculate_inclusions_bonus(self, factors: DealFactors) -> int:
        """Calculate bonus for inclusions (box, papers, etc.)"""
        bonus = 0
        
        if factors.is_full_set:
            bonus += 15
        else:
            if factors.has_box:
                bonus += 5
            if factors.has_papers:
                bonus += 8
            if factors.has_warranty:
                bonus += 5
        
        return min(bonus, 15)
    
    def calculate_seller_bonus(self, factors: DealFactors) -> int:
        """Calculate bonus for seller reputation"""
        bonus = self.SELLER_BONUSES.get(factors.seller_type, 0)
        
        # Boost for high transaction count
        if factors.seller_transaction_count >= 100:
            bonus += 2
        elif factors.seller_transaction_count >= 50:
            bonus += 1
        
        # Boost for high rating
        if factors.seller_rating and factors.seller_rating >= 4.8:
            bonus += 2
        elif factors.seller_rating and factors.seller_rating >= 4.5:
            bonus += 1
        
        return min(bonus, 10)
    
    def calculate_urgency_bonus(self, factors: DealFactors) -> int:
        """Calculate bonus for urgency signals"""
        bonus = 0
        
        if factors.quick_sale_indicated:
            bonus += 3
        if factors.price_reduced:
            bonus += 2
        if factors.motivated_seller:
            bonus += 2
        
        return min(bonus, 5)
    
    def calculate_market_adjustment(self, factors: DealFactors) -> int:
        """Calculate market trend adjustment"""
        if factors.market_trend == MarketTrend.RISING:
            # Rising prices = better deal (harder to find good deals)
            return 20
        elif factors.market_trend == MarketTrend.FALLING:
            # Falling prices = not as special
            return -20
        else:
            return 0
    
    def calculate_risk_penalty(self, factors: DealFactors) -> int:
        """Calculate penalty for risk factors"""
        penalty = 0
        
        # Calculate discount to check if too good to be true
        discount_pct = ((factors.market_price - factors.listing_price) / factors.market_price) * 100
        
        if discount_pct > 40:
            penalty += 30  # Too cheap is suspicious
        
        if factors.vague_photos:
            penalty += 10
        
        if factors.new_seller_suspicious:
            penalty += 15
        
        if factors.payment_red_flags:
            penalty += 20
        
        if factors.contradictory_info:
            penalty += 15
        
        return min(penalty, 50)
    
    def assess_risk(self, factors: DealFactors, discount_pct: float) -> RiskAssessment:
        """
        Assess risk level and identify red flags.
        
        Risk levels:
        - LOW: Verified dealer, clear photos, reasonable price
        - MEDIUM: Private seller, good price but limited info
        - HIGH: Too cheap, suspicious seller, vague details
        - CRITICAL: Likely scam or stolen watch
        """
        red_flags = []
        concerns = []
        recommendations = []
        risk_score = 0
        
        # Price analysis
        if discount_pct > 40:
            red_flags.append(f"Price is {discount_pct:.0f}% below market - too good to be true")
            risk_score += 35
        elif discount_pct > 30:
            concerns.append(f"Significant {discount_pct:.0f}% discount - verify authenticity")
            risk_score += 20
        
        # Seller analysis
        if factors.seller_type == SellerType.UNKNOWN:
            concerns.append("Unknown seller - no reputation data")
            risk_score += 15
        elif factors.seller_type == SellerType.PRIVATE_NEW:
            if factors.seller_transaction_count == 0:
                red_flags.append("Brand new seller with no transaction history")
                risk_score += 25
            else:
                concerns.append("New seller - proceed with caution")
                risk_score += 10
        
        # Photo quality
        if factors.vague_photos:
            red_flags.append("Poor or vague photos - potential stock images")
            risk_score += 20
        
        # Payment red flags
        if factors.payment_red_flags:
            red_flags.append("Suspicious payment methods (wire only, crypto)")
            risk_score += 30
        
        # Information consistency
        if factors.contradictory_info:
            red_flags.append("Contradictory or inconsistent information")
            risk_score += 25
        
        # Positive factors
        if factors.seller_type == SellerType.VERIFIED_DEALER:
            risk_score = max(0, risk_score - 20)
            recommendations.append("Verified dealer - transaction should be safe")
        
        if factors.has_papers and factors.has_box:
            risk_score = max(0, risk_score - 10)
            recommendations.append("Full documentation present - verify serial numbers")
        
        # Determine risk level
        if risk_score >= 60:
            level = RiskLevel.CRITICAL
            recommendations.append("DO NOT PROCEED - High probability of fraud")
        elif risk_score >= 40:
            level = RiskLevel.HIGH
            recommendations.append("Exercise extreme caution - thorough verification required")
        elif risk_score >= 20:
            level = RiskLevel.MEDIUM
            recommendations.append("Standard due diligence recommended")
        else:
            level = RiskLevel.LOW
            recommendations.append("Proceed with normal authentication checks")
        
        return RiskAssessment(
            level=level,
            score=min(risk_score, 100),
            red_flags=red_flags,
            concerns=concerns,
            recommendations=recommendations
        )
    
    def classify_tier(self, score: int) -> DealTier:
        """Classify deal into tier based on score"""
        if score >= self.TIER_THRESHOLDS[DealTier.URGENT]:
            return DealTier.URGENT
        elif score >= self.TIER_THRESHOLDS[DealTier.PUSH]:
            return DealTier.PUSH
        elif score >= self.TIER_THRESHOLDS[DealTier.NORMAL]:
            return DealTier.NORMAL
        elif score >= self.TIER_THRESHOLDS[DealTier.SKIP]:
            return DealTier.SKIP
        else:
            return DealTier.OVERPRICED
    
    def generate_explanation(
        self,
        factors: DealFactors,
        breakdown: ScoringBreakdown,
        tier: DealTier,
        risk: RiskAssessment
    ) -> str:
        """Generate human-readable explanation of the score"""
        
        # Base explanation
        discount_text = f"{breakdown.discount_percentage:.1f}% {'below' if breakdown.discount_percentage > 0 else 'above'} market"
        explanation = f"{tier.value} DEAL: {discount_text} (${factors.listing_price:,} vs ${factors.market_price:,} market). "
        
        # Add positive factors
        positive_factors = []
        if breakdown.condition_bonus > 0:
            positive_factors.append(f"{factors.condition.value} condition (+{breakdown.condition_bonus})")
        if breakdown.inclusions_bonus > 0:
            if factors.is_full_set:
                positive_factors.append(f"full set (+{breakdown.inclusions_bonus})")
            else:
                positive_factors.append(f"with documentation (+{breakdown.inclusions_bonus})")
        if breakdown.seller_bonus > 0:
            positive_factors.append(f"{factors.seller_type.value.lower().replace('_', ' ')} (+{breakdown.seller_bonus})")
        if breakdown.urgency_bonus > 0:
            positive_factors.append(f"urgent sale (+{breakdown.urgency_bonus})")
        
        if positive_factors:
            explanation += " ".join(positive_factors) + ". "
        
        # Market context
        if factors.market_trend != MarketTrend.UNKNOWN:
            trend_text = "trending up" if factors.market_trend == MarketTrend.RISING else "trending down" if factors.market_trend == MarketTrend.FALLING else "stable"
            explanation += f"Market {trend_text}. "
        
        # Confidence
        if factors.comparable_count > 30:
            explanation += f"High confidence ({factors.comparable_count} recent comps). "
        elif factors.comparable_count > 10:
            explanation += f"Moderate confidence ({factors.comparable_count} comps). "
        
        # Risk warning
        if risk.level in [RiskLevel.HIGH, RiskLevel.CRITICAL]:
            explanation += f"⚠️ {risk.level.value} RISK: {', '.join(risk.red_flags[:2])}. "
        
        # Action recommendation
        if tier == DealTier.URGENT and risk.level == RiskLevel.LOW:
            explanation += "Act fast!"
        elif tier == DealTier.URGENT and risk.level != RiskLevel.LOW:
            explanation += "Verify authenticity before acting!"
        elif tier == DealTier.OVERPRICED:
            explanation += "Avoid - overpriced."
        
        return explanation.strip()
    
    def calculate_arbitrage(
        self,
        buy_platform: str,
        sell_platform: str,
        buy_price: int,
        sell_price: int
    ) -> ArbitrageOpportunity:
        """
        Calculate arbitrage opportunity between platforms.
        
        Considers:
        - Platform fees
        - Payment processing (3.5% + $0.49 for PayPal)
        - Shipping/Insurance (~$100)
        """
        source_fee_pct = self.PLATFORM_FEES.get(buy_platform.lower(), 0)
        target_fee_pct = self.PLATFORM_FEES.get(sell_platform.lower(), 6.5)
        
        # Calculate costs
        source_fees = buy_price * (source_fee_pct / 100)
        target_fees = sell_price * (target_fee_pct / 100)
        paypal_fee = (sell_price * 0.035) + 0.49 if sell_platform.lower() != "whatsapp" else 0
        shipping_cost = 100.0  # Insured shipping estimate
        insurance_cost = sell_price * 0.01  # 1% of value
        
        total_costs = buy_price + source_fees + target_fees + paypal_fee + shipping_cost + insurance_cost
        gross_profit = sell_price - buy_price
        net_profit = sell_price - int(total_costs)
        roi_percentage = (net_profit / buy_price * 100) if buy_price > 0 else 0
        
        # Viable if net profit > $500 and ROI > 5%
        is_viable = net_profit >= 500 and roi_percentage >= 5
        
        return ArbitrageOpportunity(
            source_platform=buy_platform,
            target_platform=sell_platform,
            buy_price=buy_price,
            sell_price=sell_price,
            source_fees=source_fees,
            target_fees=target_fees,
            shipping_cost=shipping_cost,
            insurance_cost=insurance_cost,
            total_costs=total_costs,
            gross_profit=gross_profit,
            net_profit=net_profit,
            roi_percentage=round(roi_percentage, 2),
            is_viable=is_viable
        )
    
    def score_deal(
        self,
        factors: DealFactors,
        calculate_arbitrage_for: Optional[Dict[str, int]] = None
    ) -> DealScore:
        """
        Score a deal with complete analysis.
        
        Args:
            factors: Deal factors for scoring
            calculate_arbitrage_for: Optional dict of {platform: price} for arbitrage calc
            
        Returns:
            Complete deal score with breakdown, explanation, and risk
        """
        # Calculate base score
        base_score, discount_pct = self.calculate_base_score(
            factors.market_price,
            factors.listing_price
        )
        
        # Calculate adjustments
        condition_bonus = self.calculate_condition_bonus(factors)
        inclusions_bonus = self.calculate_inclusions_bonus(factors)
        seller_bonus = self.calculate_seller_bonus(factors)
        urgency_bonus = self.calculate_urgency_bonus(factors)
        market_adjustment = self.calculate_market_adjustment(factors)
        rarity_bonus = factors.rarity_score
        risk_penalty = self.calculate_risk_penalty(factors)
        
        # Calculate final score
        final_score = base_score + condition_bonus + inclusions_bonus + seller_bonus
        final_score += urgency_bonus + market_adjustment + rarity_bonus - risk_penalty
        final_score = max(self.MIN_SCORE, min(self.MAX_SCORE, final_score))
        
        # Create breakdown
        breakdown = ScoringBreakdown(
            base_score=base_score,
            condition_bonus=condition_bonus,
            inclusions_bonus=inclusions_bonus,
            seller_bonus=seller_bonus,
            urgency_bonus=urgency_bonus,
            market_trend_adjustment=market_adjustment,
            rarity_bonus=rarity_bonus,
            risk_penalty=risk_penalty,
            final_score=final_score,
            discount_percentage=round(discount_pct, 2)
        )
        
        # Classify tier
        tier = self.classify_tier(final_score)
        
        # Assess risk
        risk = self.assess_risk(factors, discount_pct)
        
        # Generate explanation
        explanation = self.generate_explanation(factors, breakdown, tier, risk)
        
        # Calculate confidence
        confidence = min(100, 50 + (factors.comparable_count * 2))
        if factors.market_trend == MarketTrend.UNKNOWN:
            confidence = max(30, confidence - 20)
        
        # Calculate arbitrage if requested
        arbitrage = None
        if calculate_arbitrage_for:
            # Find best arbitrage opportunity
            best_arb = None
            best_profit = 0
            
            for platform, sell_price in calculate_arbitrage_for.items():
                arb = self.calculate_arbitrage(
                    "current_platform",  # Source
                    platform,
                    factors.listing_price,
                    sell_price
                )
                if arb.is_viable and arb.net_profit > best_profit:
                    best_arb = arb
                    best_profit = arb.net_profit
            
            arbitrage = best_arb
        
        return DealScore(
            score=final_score,
            tier=tier,
            breakdown=breakdown,
            explanation=explanation,
            risk_assessment=risk,
            arbitrage=arbitrage,
            confidence=confidence
        )


# Convenience function for quick scoring
def score_watch_deal(
    market_price: int,
    listing_price: int,
    condition: str = "UNKNOWN",
    has_box: bool = False,
    has_papers: bool = False,
    seller_type: str = "UNKNOWN",
    **kwargs
) -> DealScore:
    """
    Quick scoring function with minimal parameters.
    
    Example:
        score = score_watch_deal(
            market_price=21500,
            listing_price=16800,
            condition="NIB",
            has_box=True,
            has_papers=True,
            seller_type="VERIFIED_DEALER"
        )
    """
    scorer = DealScorer()
    
    factors = DealFactors(
        market_price=market_price,
        listing_price=listing_price,
        condition=ConditionGrade(condition.upper()),
        has_box=has_box,
        has_papers=has_papers,
        is_full_set=(has_box and has_papers),
        seller_type=SellerType(seller_type.upper()),
        **kwargs
    )
    
    return scorer.score_deal(factors)
