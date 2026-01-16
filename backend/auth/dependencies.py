"""
Authentication Dependencies for FastAPI

Reusable dependency functions for authentication, authorization, and rate limiting.
"""

from datetime import datetime, timedelta
from typing import Optional, Callable
from functools import wraps
import hashlib
import logging

from fastapi import Depends, HTTPException, status, Header, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
import redis
from pydantic import BaseModel

from .models import User, APIKey, Session as DBSession, AuthEvent, UserType, SubscriptionTier

# JWT Configuration
SECRET_KEY = "your-secret-key-change-in-production"  # Load from environment
ALGORITHM = "HS256"  # Using HS256 for HMAC-based tokens (use RS256 in production with RSA keys)
ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_DAYS = 30

# Redis for rate limiting (configure from environment)
redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

# HTTP Bearer token scheme
security = HTTPBearer()


class TokenData(BaseModel):
    """JWT token payload data"""
    user_id: int
    email: str
    user_type: str
    session_id: int


# Database setup - created once at module level
SQLALCHEMY_DATABASE_URL = "sqlite:///./watchy_auth.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Session:
    """
    Database session dependency
    
    Yields a database session and ensures cleanup
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Create JWT access token
    
    Args:
        data: Token payload
        expires_delta: Optional custom expiration time
        
    Returns:
        Encoded JWT token
    """
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire, "type": "access"})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def create_refresh_token(data: dict) -> str:
    """
    Create JWT refresh token
    
    Args:
        data: Token payload
        
    Returns:
        Encoded JWT refresh token
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def decode_token(token: str) -> TokenData:
    """
    Decode and validate JWT token
    
    Args:
        token: JWT token string
        
    Returns:
        TokenData object with user information
        
    Raises:
        HTTPException: If token is invalid or expired
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: int = payload.get("user_id")
        email: str = payload.get("email")
        user_type: str = payload.get("user_type")
        session_id: int = payload.get("session_id")
        
        if user_id is None or email is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        return TokenData(
            user_id=user_id,
            email=email,
            user_type=user_type,
            session_id=session_id
        )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    """
    Get current authenticated user from JWT token
    
    Validates JWT token, checks session validity, and returns user object.
    
    Args:
        credentials: HTTP Bearer token credentials
        db: Database session
        
    Returns:
        User object
        
    Raises:
        HTTPException: 401 if authentication fails
    """
    token = credentials.credentials
    token_data = decode_token(token)
    
    # Load user from database
    user = db.query(User).filter(User.id == token_data.user_id).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Check if user is active
    if not user.is_active or user.is_suspended:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Validate session
    session = db.query(DBSession).filter(
        DBSession.id == token_data.session_id,
        DBSession.user_id == user.id
    ).first()
    
    if not session or not session.is_valid():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired or invalid",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Update last activity
    session.last_activity_at = datetime.utcnow()
    db.commit()
    
    return user


async def get_current_active_user(
    user: User = Depends(get_current_user)
) -> User:
    """
    Get current active and verified user
    
    Requires email verification and checks account status.
    
    Args:
        user: Current user from get_current_user
        
    Returns:
        User object
        
    Raises:
        HTTPException: 403 if user not verified or inactive
    """
    if not user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email verification required. Please check your email.",
        )
    
    if user.is_suspended:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account suspended. Contact support for assistance.",
        )
    
    return user


async def require_dealer(
    user: User = Depends(get_current_active_user)
) -> User:
    """
    Require user to be a dealer or admin
    
    Args:
        user: Current active user
        
    Returns:
        User object
        
    Raises:
        HTTPException: 403 if user is not dealer or admin
    """
    if user.user_type not in [UserType.DEALER.value, UserType.ADMIN.value]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This endpoint requires dealer or admin access",
        )
    
    return user


async def require_admin(
    user: User = Depends(get_current_active_user)
) -> User:
    """
    Require user to be an admin
    
    Args:
        user: Current active user
        
    Returns:
        User object
        
    Raises:
        HTTPException: 403 if user is not admin
    """
    if user.user_type != UserType.ADMIN.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This endpoint requires admin access",
        )
    
    return user


def require_subscription(required_tier: str):
    """
    Dependency factory for subscription tier requirements
    
    Args:
        required_tier: Minimum subscription tier required
        
    Returns:
        Dependency function
        
    Raises:
        HTTPException: 402 Payment Required if subscription insufficient
    """
    async def subscription_checker(
        user: User = Depends(get_current_active_user),
        db: Session = Depends(get_db)
    ) -> User:
        # Get user's team (assuming user is in at least one team)
        if not user.teams:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=f"Subscription required. Upgrade to {required_tier} tier.",
                headers={"X-Upgrade-URL": "/billing/upgrade"}
            )
        
        # Check primary team subscription
        team = user.teams[0]  # Or implement logic to get active team
        
        if not team.can_access_tier(required_tier):
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=f"Subscription tier '{required_tier}' required. Current tier: '{team.subscription_tier}'",
                headers={"X-Upgrade-URL": "/billing/upgrade"}
            )
        
        if not team.has_active_subscription():
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="Subscription expired. Please update your payment method.",
                headers={"X-Upgrade-URL": "/billing/manage"}
            )
        
        return user
    
    return subscription_checker


async def get_api_key_user(
    x_api_key: str = Header(...),
    db: Session = Depends(get_db)
) -> User:
    """
    Alternative authentication using API key
    
    For programmatic access without JWT tokens.
    
    Args:
        x_api_key: API key from X-API-Key header
        db: Database session
        
    Returns:
        User object
        
    Raises:
        HTTPException: 401 if API key invalid
    """
    # Hash the provided key
    key_hash = APIKey.hash_key(x_api_key)
    
    # Find API key in database
    api_key = db.query(APIKey).filter(
        APIKey.key_hash == key_hash
    ).first()
    
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
    
    # Validate API key
    if not api_key.is_valid():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key expired or inactive",
        )
    
    # Update last used timestamp
    api_key.last_used_at = datetime.utcnow()
    db.commit()
    
    # Load and return user
    user = db.query(User).filter(User.id == api_key.user_id).first()
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account inactive",
        )
    
    return user


def rate_limit(max_requests: int, window_seconds: int):
    """
    Rate limiting decorator using Redis
    
    Args:
        max_requests: Maximum requests allowed in window
        window_seconds: Time window in seconds
        
    Returns:
        Decorator function
        
    Raises:
        HTTPException: 429 Too Many Requests if limit exceeded
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, request: Request = None, user: User = None, **kwargs):
            # Determine rate limit key (prefer user_id, fallback to IP)
            if user:
                key = f"ratelimit:user:{user.id}:{func.__name__}"
            elif request:
                client_ip = request.client.host
                key = f"ratelimit:ip:{client_ip}:{func.__name__}"
            else:
                # No rate limiting if we can't identify the requester
                return await func(*args, **kwargs)
            
            try:
                # Get current count
                current = redis_client.get(key)
                
                if current is None:
                    # First request in window
                    redis_client.setex(key, window_seconds, 1)
                else:
                    current_count = int(current)
                    if current_count >= max_requests:
                        # Get TTL for Retry-After header
                        ttl = redis_client.ttl(key)
                        raise HTTPException(
                            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                            detail=f"Rate limit exceeded. Max {max_requests} requests per {window_seconds} seconds.",
                            headers={"Retry-After": str(ttl)}
                        )
                    
                    # Increment counter
                    redis_client.incr(key)
            
            except redis.RedisError as e:
                # If Redis fails, allow the request (fail open) but log the error
                import logging
                logging.warning(f"Rate limiting failed due to Redis error: {e}")
                pass
            
            return await func(*args, **kwargs)
        
        return wrapper
    
    return decorator


def log_auth_event(
    db: Session,
    event_type: str,
    user_id: Optional[int],
    email: Optional[str],
    ip_address: Optional[str],
    user_agent: Optional[str],
    success: bool,
    metadata: Optional[dict] = None
):
    """
    Log authentication event for audit trail
    
    Args:
        db: Database session
        event_type: Type of event (login, logout, failed_login, etc.)
        user_id: User ID if available
        email: User email
        ip_address: Client IP address
        user_agent: Client user agent
        success: Whether event was successful
        metadata: Additional context data
    """
    event = AuthEvent(
        user_id=user_id,
        event_type=event_type,
        email=email,
        ip_address=ip_address,
        user_agent=user_agent,
        success=success,
        event_metadata=metadata  # Updated column name
    )
    db.add(event)
    db.commit()
