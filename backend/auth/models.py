"""
Authentication Models for Luxury Watch Marketplace

Provides complete user authentication, multi-tenancy, and subscription management models.
Supports Collectors, Dealers, and Admins with team workspaces and API key access.
"""

from datetime import datetime, timedelta
from typing import Optional, List
from enum import Enum
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Table, JSON, Text
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.sql import func
from passlib.context import CryptContext
import secrets
import hashlib

Base = declarative_base()

# Password hashing context with bcrypt (cost factor 12)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)


class UserType(str, Enum):
    """User types supported by the platform"""
    COLLECTOR = "collector"  # Buyer
    DEALER = "dealer"        # Seller
    ADMIN = "admin"          # Platform admin


class SubscriptionTier(str, Enum):
    """Subscription tiers with pricing"""
    FREE = "free"                    # $0/mo
    PRO = "pro"                      # $49/mo
    DEALER = "dealer"                # $299/mo
    ENTERPRISE = "enterprise"        # $999/mo


class TeamRole(str, Enum):
    """Roles within a team/workspace"""
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"


# Association table for team members (many-to-many)
team_members = Table(
    'team_members',
    Base.metadata,
    Column('team_id', Integer, ForeignKey('teams.id', ondelete='CASCADE'), primary_key=True),
    Column('user_id', Integer, ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
    Column('role', String(20), nullable=False, default=TeamRole.MEMBER.value),
    Column('joined_at', DateTime, server_default=func.now(), nullable=False)
)


class User(Base):
    """
    User account model
    
    Supports three user types: Collector, Dealer, Admin
    Email verification required, 2FA optional
    """
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    user_type = Column(String(20), nullable=False, default=UserType.COLLECTOR.value)
    is_verified = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    is_suspended = Column(Boolean, default=False, nullable=False)
    totp_secret = Column(String(32), nullable=True)  # For 2FA
    backup_codes = Column(JSON, nullable=True)  # Hashed backup codes for 2FA
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
    last_login_at = Column(DateTime, nullable=True)
    
    # Relationships
    profile = relationship("UserProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    owned_teams = relationship("Team", back_populates="owner", foreign_keys="Team.owner_id")
    teams = relationship("Team", secondary=team_members, back_populates="members")
    api_keys = relationship("APIKey", back_populates="user", cascade="all, delete-orphan")
    sessions = relationship("Session", back_populates="user", cascade="all, delete-orphan")
    
    def set_password(self, password: str):
        """Hash and set password using bcrypt with cost factor 12"""
        self.password_hash = pwd_context.hash(password)
    
    def verify_password(self, password: str) -> bool:
        """Verify password against stored hash"""
        return pwd_context.verify(password, self.password_hash)
    
    def generate_backup_codes(self, count: int = 10) -> List[str]:
        """Generate backup codes for 2FA recovery"""
        codes = [secrets.token_hex(4) for _ in range(count)]
        # Store hashed versions
        self.backup_codes = [pwd_context.hash(code) for code in codes]
        return codes
    
    def verify_backup_code(self, code: str) -> bool:
        """Verify and consume a backup code"""
        if not self.backup_codes:
            return False
        
        for i, hashed_code in enumerate(self.backup_codes):
            if pwd_context.verify(code, hashed_code):
                # Remove used code
                self.backup_codes.pop(i)
                return True
        return False


class UserProfile(Base):
    """
    User profile information
    
    Extended user data including dealer-specific fields
    """
    __tablename__ = 'user_profiles'
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, unique=True)
    full_name = Column(String(255), nullable=True)
    phone = Column(String(50), nullable=True)
    company_name = Column(String(255), nullable=True)
    dealer_license_number = Column(String(100), nullable=True)
    bio = Column(Text, nullable=True)
    avatar_url = Column(String(500), nullable=True)
    timezone = Column(String(50), default='UTC', nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relationship
    user = relationship("User", back_populates="profile")


class Team(Base):
    """
    Team/Workspace for multi-user dealerships
    
    Supports subscription management and Stripe integration
    """
    __tablename__ = 'teams'
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    owner_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    subscription_tier = Column(String(20), nullable=False, default=SubscriptionTier.FREE.value)
    stripe_customer_id = Column(String(255), nullable=True, unique=True, index=True)
    stripe_subscription_id = Column(String(255), nullable=True, unique=True, index=True)
    subscription_status = Column(String(50), nullable=True)  # active, past_due, canceled, etc.
    trial_ends_at = Column(DateTime, nullable=True)
    subscription_ends_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relationships
    owner = relationship("User", back_populates="owned_teams", foreign_keys=[owner_id])
    members = relationship("User", secondary=team_members, back_populates="teams")
    
    def has_active_subscription(self) -> bool:
        """Check if team has an active subscription"""
        if self.subscription_tier == SubscriptionTier.FREE.value:
            return True
        return self.subscription_status == 'active'
    
    def can_access_tier(self, required_tier: str) -> bool:
        """Check if team subscription meets required tier"""
        tier_hierarchy = {
            SubscriptionTier.FREE.value: 0,
            SubscriptionTier.PRO.value: 1,
            SubscriptionTier.DEALER.value: 2,
            SubscriptionTier.ENTERPRISE.value: 3
        }
        current_level = tier_hierarchy.get(self.subscription_tier, 0)
        required_level = tier_hierarchy.get(required_tier, 0)
        return current_level >= required_level


class APIKey(Base):
    """
    API keys for programmatic access
    
    Supports scoped permissions and expiration
    """
    __tablename__ = 'api_keys'
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    name = Column(String(255), nullable=False)
    key_hash = Column(String(255), nullable=False, unique=True, index=True)
    key_prefix = Column(String(10), nullable=False)  # First 8 chars for identification
    scopes = Column(JSON, nullable=False, default=list)  # List of permission scopes
    last_used_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    
    # Relationship
    user = relationship("User", back_populates="api_keys")
    
    @staticmethod
    def generate_key() -> tuple[str, str]:
        """
        Generate a new API key
        
        Returns:
            tuple: (key, key_hash) where key is the actual key to give to user
        """
        # Generate 32-byte random key
        key = f"wt_{secrets.token_urlsafe(32)}"
        key_hash = hashlib.sha256(key.encode()).hexdigest()
        return key, key_hash
    
    @staticmethod
    def hash_key(key: str) -> str:
        """Hash an API key for storage"""
        return hashlib.sha256(key.encode()).hexdigest()
    
    def is_valid(self) -> bool:
        """Check if API key is valid"""
        if not self.is_active:
            return False
        if self.expires_at and datetime.utcnow() > self.expires_at:
            return False
        return True


class Session(Base):
    """
    User session tracking
    
    Tracks active sessions for security and session management
    """
    __tablename__ = 'sessions'
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    token_hash = Column(String(255), nullable=False, unique=True, index=True)
    refresh_token_hash = Column(String(255), nullable=True, unique=True, index=True)
    ip_address = Column(String(45), nullable=True)  # IPv6 max length
    user_agent = Column(String(500), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    refresh_expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    last_activity_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relationship
    user = relationship("User", back_populates="sessions")
    
    def is_valid(self) -> bool:
        """Check if session is valid"""
        if not self.is_active:
            return False
        if datetime.utcnow() > self.expires_at:
            return False
        return True
    
    def can_refresh(self) -> bool:
        """Check if session can be refreshed"""
        if not self.is_active:
            return False
        if not self.refresh_expires_at:
            return False
        if datetime.utcnow() > self.refresh_expires_at:
            return False
        return True


class EmailVerification(Base):
    """
    Email verification tokens
    
    Time-limited tokens for email verification
    """
    __tablename__ = 'email_verifications'
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    token = Column(String(255), nullable=False, unique=True, index=True)
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    
    @staticmethod
    def generate_token() -> str:
        """Generate a secure verification token"""
        return secrets.token_urlsafe(32)
    
    def is_valid(self) -> bool:
        """Check if token is valid"""
        if self.used_at is not None:
            return False
        if datetime.utcnow() > self.expires_at:
            return False
        return True


class PasswordReset(Base):
    """
    Password reset tokens
    
    Time-limited tokens for password reset flow
    """
    __tablename__ = 'password_resets'
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    token = Column(String(255), nullable=False, unique=True, index=True)
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    
    @staticmethod
    def generate_token() -> str:
        """Generate a secure reset token"""
        return secrets.token_urlsafe(32)
    
    def is_valid(self) -> bool:
        """Check if token is valid"""
        if self.used_at is not None:
            return False
        if datetime.utcnow() > self.expires_at:
            return False
        return True


class AuthEvent(Base):
    """
    Authentication event logging
    
    Tracks all authentication-related events for security auditing
    """
    __tablename__ = 'auth_events'
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    event_type = Column(String(50), nullable=False, index=True)  # login, logout, failed_login, etc.
    email = Column(String(255), nullable=True, index=True)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)
    success = Column(Boolean, nullable=False)
    event_metadata = Column(JSON, nullable=True)  # Additional context - renamed to avoid conflict
    created_at = Column(DateTime, server_default=func.now(), nullable=False, index=True)
