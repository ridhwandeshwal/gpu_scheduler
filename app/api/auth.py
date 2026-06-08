"""Authentication API endpoints: register, login, logout."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import (
    generate_session_token,
    get_current_user,
    hash_password,
    hash_session_token,
    verify_password,
)
from app.config import get_settings
from app.database import get_db
from app.models import User, UserSession
from app.schemas import AuthResponse, LoginRequest, MessageResponse, RegisterRequest

router = APIRouter()
settings = get_settings()


@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account",
)
async def register(
    body: RegisterRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    """Create a new user and return a session token."""

    # Check username uniqueness
    existing = await db.execute(
        select(User).where(User.username == body.username)
    )
    if existing.scalars().first() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username already taken",
        )

    # Check email uniqueness
    existing = await db.execute(
        select(User).where(User.email == body.email)
    )
    if existing.scalars().first() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    # Create user
    user = User(
        username=body.username,
        email=body.email,
        full_name=body.full_name,
        password_hash=hash_password(body.password),
        role="user",
        status="active",
    )
    db.add(user)
    await db.flush()  # Populate user.id

    # Create session
    raw_token, token_hash = generate_session_token()
    now = datetime.now(timezone.utc)
    session = UserSession(
        user_id=user.id,
        session_token_hash=token_hash,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("User-Agent"),
        expires_at=now + timedelta(hours=settings.session_expiry_hours),
        last_seen_at=now,
    )
    db.add(session)
    await db.flush()

    return AuthResponse(
        user_id=user.id,
        username=user.username,
        email=user.email,
        role=user.role,
        session_token=raw_token,
    )


@router.post(
    "/login",
    response_model=AuthResponse,
    summary="Authenticate and receive a session token",
)
async def login(
    body: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    """Verify credentials and return a new session token."""

    result = await db.execute(
        select(User).where(User.username == body.username)
    )
    user = result.scalars().first()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    if user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is not active",
        )

    if not verify_password(body.password, user.password_hash):
        # Increment failed login attempts
        user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
        await db.flush()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    # Reset failed attempts on success
    now = datetime.now(timezone.utc)
    user.failed_login_attempts = 0
    user.last_login_at = now
    await db.flush()

    # Create new session
    raw_token, token_hash = generate_session_token()
    session = UserSession(
        user_id=user.id,
        session_token_hash=token_hash,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("User-Agent"),
        expires_at=now + timedelta(hours=settings.session_expiry_hours),
        last_seen_at=now,
    )
    db.add(session)
    await db.flush()

    return AuthResponse(
        user_id=user.id,
        username=user.username,
        email=user.email,
        role=user.role,
        session_token=raw_token,
    )


@router.post(
    "/logout",
    response_model=MessageResponse,
    summary="Revoke the current session",
)
async def logout(
    request: Request,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> MessageResponse:
    """Revoke the session token used in this request."""

    auth_header = request.headers.get("Authorization", "")
    raw_token = auth_header.removeprefix("Bearer ").strip()
    token_hash = hash_session_token(raw_token)

    result = await db.execute(
        select(UserSession).where(UserSession.session_token_hash == token_hash)
    )
    session = result.scalars().first()

    if session is not None:
        session.revoked_at = datetime.now(timezone.utc)
        await db.flush()

    return MessageResponse(message="Logged out successfully")
