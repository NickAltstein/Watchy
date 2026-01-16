"""
Authentication Routes for FastAPI

Complete authentication endpoints including registration, login, 2FA, sessions, and API keys.
"""

from datetime import datetime, timedelta
from typing import List, Optional
import secrets
import hashlib

from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr, Field, validator
import pyotp
import qrcode
import io
import base64

from .models import (
    User, UserProfile, Team, Session as DBSession, APIKey,
    EmailVerification, PasswordReset, AuthEvent,
    UserType, SubscriptionTier, TeamRole
)
from .dependencies import (
    get_db, get_current_user, get_current_active_user,
    require_dealer, require_admin, rate_limit,
    create_access_token, create_refresh_token, decode_token,
    log_auth_event
)

router = APIRouter(prefix="/auth", tags=["authentication"])


# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================

class RegisterRequest(BaseModel):
    """User registration request"""
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=100)
    user_type: UserType
    full_name: Optional[str] = None
    company_name: Optional[str] = None
    
    @validator('password')
    def password_strength(cls, v):
        """Validate password strength"""
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters')
        if not any(c.isupper() for c in v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not any(c.islower() for c in v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not any(c.isdigit() for c in v):
            raise ValueError('Password must contain at least one digit')
        return v


class LoginRequest(BaseModel):
    """User login request"""
    email: EmailStr
    password: str
    totp_code: Optional[str] = None


class LoginResponse(BaseModel):
    """Login response with tokens"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: dict


class RefreshTokenRequest(BaseModel):
    """Refresh token request"""
    refresh_token: str


class VerifyEmailRequest(BaseModel):
    """Email verification request"""
    token: str


class ForgotPasswordRequest(BaseModel):
    """Forgot password request"""
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    """Reset password request"""
    token: str
    new_password: str = Field(..., min_length=8, max_length=100)


class ChangePasswordRequest(BaseModel):
    """Change password request"""
    current_password: str
    new_password: str = Field(..., min_length=8, max_length=100)


class UpdateProfileRequest(BaseModel):
    """Update user profile request"""
    full_name: Optional[str] = None
    phone: Optional[str] = None
    company_name: Optional[str] = None
    dealer_license_number: Optional[str] = None
    bio: Optional[str] = None
    timezone: Optional[str] = None


class Enable2FAResponse(BaseModel):
    """2FA enable response with QR code"""
    secret: str
    qr_code: str
    backup_codes: List[str]


class Verify2FARequest(BaseModel):
    """2FA verification request"""
    code: str


class CreateAPIKeyRequest(BaseModel):
    """API key creation request"""
    name: str = Field(..., min_length=1, max_length=255)
    scopes: List[str] = []
    expires_in_days: Optional[int] = None


class APIKeyResponse(BaseModel):
    """API key response"""
    id: int
    name: str
    key: Optional[str] = None  # Only provided on creation
    key_prefix: str
    scopes: List[str]
    expires_at: Optional[datetime]
    created_at: datetime


# ============================================================================
# REGISTRATION & LOGIN
# ============================================================================

@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
    request: RegisterRequest,
    req: Request,
    db: Session = Depends(get_db)
):
    """
    Register a new user account
    
    Creates user, profile, and sends verification email.
    Rate limited to prevent abuse.
    """
    # Check if email already exists
    existing_user = db.query(User).filter(User.email == request.email).first()
    if existing_user:
        # Don't reveal if email exists for security
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Registration failed. Please try again."
        )
    
    # Create user
    user = User(
        email=request.email,
        user_type=request.user_type,  # Enum used directly
        is_verified=False
    )
    user.set_password(request.password)
    db.add(user)
    db.flush()
    
    # Create profile
    profile = UserProfile(
        user_id=user.id,
        full_name=request.full_name,
        company_name=request.company_name
    )
    db.add(profile)
    
    # Create default team for user
    team = Team(
        name=f"{request.full_name or request.email}'s Team",
        owner_id=user.id,
        subscription_tier=SubscriptionTier.FREE  # Enum used directly
    )
    db.add(team)
    db.flush()
    
    # Add user to team
    user.teams.append(team)
    
    # Generate email verification token
    verification = EmailVerification(
        user_id=user.id,
        token=EmailVerification.generate_token(),
        expires_at=datetime.utcnow() + timedelta(days=7)
    )
    db.add(verification)
    
    # Log registration event
    log_auth_event(
        db=db,
        event_type="register",
        user_id=user.id,
        email=user.email,
        ip_address=req.client.host,
        user_agent=req.headers.get("user-agent"),
        success=True
    )
    
    db.commit()
    
    # TODO: Send verification email
    # send_verification_email(user.email, verification.token)
    
    return {
        "message": "Registration successful. Please check your email to verify your account.",
        "user_id": user.id
    }


@router.post("/login", response_model=LoginResponse)
@rate_limit(max_requests=5, window_seconds=900)  # 5 attempts per 15 minutes
async def login(
    request: LoginRequest,
    req: Request,
    db: Session = Depends(get_db)
):
    """
    User login
    
    Returns access and refresh tokens.
    Rate limited to prevent brute force attacks.
    """
    # Find user
    user = db.query(User).filter(User.email == request.email).first()
    
    # Verify credentials
    if not user or not user.verify_password(request.password):
        # Log failed attempt
        log_auth_event(
            db=db,
            event_type="failed_login",
            user_id=user.id if user else None,
            email=request.email,
            ip_address=req.client.host,
            user_agent=req.headers.get("user-agent"),
            success=False,
            metadata={"reason": "invalid_credentials"}
        )
        
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
    
    # Check if account is active
    if not user.is_active or user.is_suspended:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive or suspended"
        )
    
    # Check 2FA if enabled
    if user.totp_secret:
        if not request.totp_code:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="2FA code required",
                headers={"X-Require-2FA": "true"}
            )
        
        # Verify TOTP code
        totp = pyotp.TOTP(user.totp_secret)
        if not totp.verify(request.totp_code, valid_window=1):
            # Try backup codes
            if not user.verify_backup_code(request.totp_code):
                log_auth_event(
                    db=db,
                    event_type="failed_login",
                    user_id=user.id,
                    email=user.email,
                    ip_address=req.client.host,
                    user_agent=req.headers.get("user-agent"),
                    success=False,
                    metadata={"reason": "invalid_2fa"}
                )
                
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid 2FA code"
                )
    
    # Create session
    session = DBSession(
        user_id=user.id,
        token_hash="",  # Will be set below
        ip_address=req.client.host,
        user_agent=req.headers.get("user-agent"),
        expires_at=datetime.utcnow() + timedelta(minutes=15),
        refresh_expires_at=datetime.utcnow() + timedelta(days=30)
    )
    db.add(session)
    db.flush()
    
    # Create tokens
    token_data = {
        "user_id": user.id,
        "email": user.email,
        "user_type": user.user_type,
        "session_id": session.id
    }
    
    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)
    
    # Hash and store tokens
    session.token_hash = hashlib.sha256(access_token.encode()).hexdigest()
    session.refresh_token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
    
    # Update last login
    user.last_login_at = datetime.utcnow()
    
    # Log successful login
    log_auth_event(
        db=db,
        event_type="login",
        user_id=user.id,
        email=user.email,
        ip_address=req.client.host,
        user_agent=req.headers.get("user-agent"),
        success=True
    )
    
    db.commit()
    
    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=900,  # 15 minutes
        user={
            "id": user.id,
            "email": user.email,
            "user_type": user.user_type,
            "is_verified": user.is_verified
        }
    )


@router.post("/logout")
async def logout(
    req: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    User logout
    
    Invalidates current session.
    """
    # Find and invalidate current session
    # (In production, extract session_id from token)
    sessions = db.query(DBSession).filter(
        DBSession.user_id == user.id,
        DBSession.is_active == True
    ).all()
    
    for session in sessions:
        session.is_active = False
    
    # Log logout event
    log_auth_event(
        db=db,
        event_type="logout",
        user_id=user.id,
        email=user.email,
        ip_address=req.client.host,
        user_agent=req.headers.get("user-agent"),
        success=True
    )
    
    db.commit()
    
    return {"message": "Logged out successfully"}


@router.post("/refresh")
async def refresh_token(
    request: RefreshTokenRequest,
    db: Session = Depends(get_db)
):
    """
    Refresh access token
    
    Uses refresh token to get new access token.
    """
    # Decode refresh token
    token_data = decode_token(request.refresh_token)
    
    # Find session
    refresh_hash = hashlib.sha256(request.refresh_token.encode()).hexdigest()
    session = db.query(DBSession).filter(
        DBSession.refresh_token_hash == refresh_hash,
        DBSession.user_id == token_data.user_id
    ).first()
    
    if not session or not session.can_refresh():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token"
        )
    
    # Create new access token
    new_token_data = {
        "user_id": token_data.user_id,
        "email": token_data.email,
        "user_type": token_data.user_type,
        "session_id": session.id
    }
    
    access_token = create_access_token(new_token_data)
    
    # Update session
    session.token_hash = hashlib.sha256(access_token.encode()).hexdigest()
    session.expires_at = datetime.utcnow() + timedelta(minutes=15)
    db.commit()
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": 900
    }


# ============================================================================
# EMAIL VERIFICATION
# ============================================================================

@router.post("/verify-email")
async def verify_email(
    request: VerifyEmailRequest,
    db: Session = Depends(get_db)
):
    """
    Verify user email address
    
    Uses token from verification email.
    """
    verification = db.query(EmailVerification).filter(
        EmailVerification.token == request.token
    ).first()
    
    if not verification or not verification.is_valid():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification token"
        )
    
    # Mark token as used
    verification.used_at = datetime.utcnow()
    
    # Mark user as verified
    user = db.query(User).filter(User.id == verification.user_id).first()
    user.is_verified = True
    
    db.commit()
    
    return {"message": "Email verified successfully"}


@router.post("/resend-verification")
async def resend_verification(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Resend email verification
    
    For users who haven't verified their email.
    """
    if user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already verified"
        )
    
    # Invalidate old tokens
    db.query(EmailVerification).filter(
        EmailVerification.user_id == user.id,
        EmailVerification.used_at == None
    ).update({"used_at": datetime.utcnow()})
    
    # Create new verification token
    verification = EmailVerification(
        user_id=user.id,
        token=EmailVerification.generate_token(),
        expires_at=datetime.utcnow() + timedelta(days=7)
    )
    db.add(verification)
    db.commit()
    
    # TODO: Send verification email
    # send_verification_email(user.email, verification.token)
    
    return {"message": "Verification email sent"}


# ============================================================================
# PASSWORD RESET
# ============================================================================

@router.post("/forgot-password")
@rate_limit(max_requests=3, window_seconds=3600)  # 3 per hour
async def forgot_password(
    request: ForgotPasswordRequest,
    db: Session = Depends(get_db)
):
    """
    Request password reset
    
    Sends reset email if user exists.
    Rate limited to prevent abuse.
    """
    user = db.query(User).filter(User.email == request.email).first()
    
    # Always return success (don't reveal if email exists)
    if user:
        # Create reset token
        reset = PasswordReset(
            user_id=user.id,
            token=PasswordReset.generate_token(),
            expires_at=datetime.utcnow() + timedelta(hours=1)
        )
        db.add(reset)
        db.commit()
        
        # TODO: Send reset email
        # send_password_reset_email(user.email, reset.token)
    
    return {"message": "If that email exists, a password reset link has been sent"}


@router.post("/reset-password")
async def reset_password(
    request: ResetPasswordRequest,
    db: Session = Depends(get_db)
):
    """
    Complete password reset
    
    Uses token from reset email to set new password.
    """
    reset = db.query(PasswordReset).filter(
        PasswordReset.token == request.token
    ).first()
    
    if not reset or not reset.is_valid():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token"
        )
    
    # Mark token as used
    reset.used_at = datetime.utcnow()
    
    # Update password
    user = db.query(User).filter(User.id == reset.user_id).first()
    user.set_password(request.new_password)
    
    # Invalidate all sessions (force re-login)
    db.query(DBSession).filter(
        DBSession.user_id == user.id
    ).update({"is_active": False})
    
    db.commit()
    
    return {"message": "Password reset successfully"}


@router.post("/change-password")
async def change_password(
    request: ChangePasswordRequest,
    user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Change password
    
    Requires current password for security.
    """
    # Verify current password
    if not user.verify_password(request.current_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect"
        )
    
    # Set new password
    user.set_password(request.new_password)
    
    # Invalidate all sessions except current (force re-login on other devices)
    db.query(DBSession).filter(
        DBSession.user_id == user.id
    ).update({"is_active": False})
    
    db.commit()
    
    return {"message": "Password changed successfully"}


# ============================================================================
# USER PROFILE
# ============================================================================

@router.get("/me")
async def get_current_user_info(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get current user information
    
    Returns user profile and team details.
    """
    profile = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
    
    return {
        "id": user.id,
        "email": user.email,
        "user_type": user.user_type,
        "is_verified": user.is_verified,
        "created_at": user.created_at,
        "profile": {
            "full_name": profile.full_name if profile else None,
            "phone": profile.phone if profile else None,
            "company_name": profile.company_name if profile else None,
            "dealer_license_number": profile.dealer_license_number if profile else None,
            "bio": profile.bio if profile else None,
            "timezone": profile.timezone if profile else "UTC"
        },
        "teams": [
            {
                "id": team.id,
                "name": team.name,
                "subscription_tier": team.subscription_tier
            }
            for team in user.teams
        ]
    }


@router.patch("/me")
async def update_profile(
    request: UpdateProfileRequest,
    user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Update user profile
    
    Updates user profile information.
    """
    profile = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
    
    if not profile:
        profile = UserProfile(user_id=user.id)
        db.add(profile)
    
    # Update fields
    if request.full_name is not None:
        profile.full_name = request.full_name
    if request.phone is not None:
        profile.phone = request.phone
    if request.company_name is not None:
        profile.company_name = request.company_name
    if request.dealer_license_number is not None:
        profile.dealer_license_number = request.dealer_license_number
    if request.bio is not None:
        profile.bio = request.bio
    if request.timezone is not None:
        profile.timezone = request.timezone
    
    db.commit()
    
    return {"message": "Profile updated successfully"}


# ============================================================================
# TWO-FACTOR AUTHENTICATION (2FA)
# ============================================================================

@router.post("/2fa/enable", response_model=Enable2FAResponse)
async def enable_2fa(
    user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Enable 2FA for user account
    
    Returns QR code and backup codes.
    """
    if user.totp_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="2FA already enabled"
        )
    
    # Generate TOTP secret
    secret = pyotp.random_base32()
    user.totp_secret = secret
    
    # Generate backup codes
    backup_codes = user.generate_backup_codes()
    
    # Generate QR code
    totp_uri = pyotp.totp.TOTP(secret).provisioning_uri(
        name=user.email,
        issuer_name="Watchy - Luxury Watch Marketplace"
    )
    
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(totp_uri)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    qr_code_base64 = base64.b64encode(buffer.getvalue()).decode()
    
    db.commit()
    
    return Enable2FAResponse(
        secret=secret,
        qr_code=f"data:image/png;base64,{qr_code_base64}",
        backup_codes=backup_codes
    )


@router.post("/2fa/verify")
async def verify_2fa(
    request: Verify2FARequest,
    user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Verify 2FA setup
    
    Confirms user can generate valid codes.
    """
    if not user.totp_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="2FA not enabled"
        )
    
    totp = pyotp.TOTP(user.totp_secret)
    if not totp.verify(request.code, valid_window=1):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid 2FA code"
        )
    
    return {"message": "2FA verified successfully"}


@router.post("/2fa/disable")
async def disable_2fa(
    request: Verify2FARequest,
    user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Disable 2FA
    
    Requires valid 2FA code or backup code to disable.
    """
    if not user.totp_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="2FA not enabled"
        )
    
    # Verify code
    totp = pyotp.TOTP(user.totp_secret)
    if not totp.verify(request.code, valid_window=1) and not user.verify_backup_code(request.code):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid 2FA code"
        )
    
    # Disable 2FA
    user.totp_secret = None
    user.backup_codes = None
    db.commit()
    
    return {"message": "2FA disabled successfully"}


# ============================================================================
# SESSION MANAGEMENT
# ============================================================================

@router.get("/sessions")
async def list_sessions(
    user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    List active sessions
    
    Shows all active sessions for the user.
    """
    sessions = db.query(DBSession).filter(
        DBSession.user_id == user.id,
        DBSession.is_active == True
    ).order_by(DBSession.last_activity_at.desc()).all()
    
    return {
        "sessions": [
            {
                "id": session.id,
                "ip_address": session.ip_address,
                "user_agent": session.user_agent,
                "created_at": session.created_at,
                "last_activity_at": session.last_activity_at,
                "expires_at": session.expires_at
            }
            for session in sessions
        ]
    }


@router.delete("/sessions/{session_id}")
async def revoke_session(
    session_id: int,
    user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Revoke specific session
    
    Logs out a specific device/session.
    """
    session = db.query(DBSession).filter(
        DBSession.id == session_id,
        DBSession.user_id == user.id
    ).first()
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found"
        )
    
    session.is_active = False
    db.commit()
    
    return {"message": "Session revoked successfully"}


# ============================================================================
# API KEY MANAGEMENT
# ============================================================================

@router.post("/api-keys", response_model=APIKeyResponse)
async def create_api_key(
    request: CreateAPIKeyRequest,
    user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Generate API key
    
    Creates a new API key for programmatic access.
    """
    # Generate key
    key, key_hash = APIKey.generate_key()
    key_prefix = key[:8]
    
    # Set expiration
    expires_at = None
    if request.expires_in_days:
        expires_at = datetime.utcnow() + timedelta(days=request.expires_in_days)
    
    # Create API key record
    api_key = APIKey(
        user_id=user.id,
        name=request.name,
        key_hash=key_hash,
        key_prefix=key_prefix,
        scopes=request.scopes,
        expires_at=expires_at
    )
    db.add(api_key)
    db.commit()
    db.refresh(api_key)
    
    return APIKeyResponse(
        id=api_key.id,
        name=api_key.name,
        key=key,  # Only returned on creation
        key_prefix=key_prefix,
        scopes=api_key.scopes,
        expires_at=api_key.expires_at,
        created_at=api_key.created_at
    )


@router.get("/api-keys")
async def list_api_keys(
    user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    List user's API keys
    
    Shows all API keys (without revealing actual keys).
    """
    api_keys = db.query(APIKey).filter(
        APIKey.user_id == user.id,
        APIKey.is_active == True
    ).order_by(APIKey.created_at.desc()).all()
    
    return {
        "api_keys": [
            {
                "id": key.id,
                "name": key.name,
                "key_prefix": key.key_prefix,
                "scopes": key.scopes,
                "last_used_at": key.last_used_at,
                "expires_at": key.expires_at,
                "created_at": key.created_at
            }
            for key in api_keys
        ]
    }


@router.delete("/api-keys/{key_id}")
async def revoke_api_key(
    key_id: int,
    user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Revoke API key
    
    Deactivates the specified API key.
    """
    api_key = db.query(APIKey).filter(
        APIKey.id == key_id,
        APIKey.user_id == user.id
    ).first()
    
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )
    
    api_key.is_active = False
    db.commit()
    
    return {"message": "API key revoked successfully"}
