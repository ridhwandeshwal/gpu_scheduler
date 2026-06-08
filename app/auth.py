"""Authentication utilities: password hashing, session tokens, and user resolution."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request, status
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import User, UserSession

# ── Password hashing (bcrypt) ────────────────────────────

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Hash a plaintext password with bcrypt."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    return pwd_context.verify(plain_password, hashed_password)


# ── Session tokens ────────────────────────────────────────


def generate_session_token() -> tuple[str, str]:
    """Generate a session token and its SHA-256 hash.

    Returns:
        (raw_token, hashed_token) — only the hash is stored in the database.
        The raw token is returned to the client exactly once.
    """
    raw_token = secrets.token_urlsafe(48)
    hashed_token = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    return raw_token, hashed_token


def hash_session_token(raw_token: str) -> str:
    """Hash a raw session token with SHA-256 for lookup."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


# ── FastAPI dependency: current user ──────────────────────


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    """Extract and validate the Bearer token, returning the authenticated user.

    Raises:
        HTTPException 401 if the token is missing, invalid, expired, or revoked.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
        )

    raw_token = auth_header.removeprefix("Bearer ").strip()
    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Empty session token",
        )

    token_hash = hash_session_token(raw_token)

    result = await db.execute(
        select(UserSession).where(UserSession.session_token_hash == token_hash)
    )
    session = result.scalars().first()

    if session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session token",
        )

    now = datetime.now(timezone.utc)

    if session.revoked_at is not None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has been revoked",
        )

    if session.expires_at < now:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has expired",
        )

    # Update last_seen_at
    session.last_seen_at = now
    await db.flush()

    # Fetch the user
    result = await db.execute(select(User).where(User.id == session.user_id))
    user = result.scalars().first()

    if user is None or user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is inactive or not found",
        )

    return user
