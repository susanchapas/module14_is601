# app/auth/jwt.py
from datetime import datetime, timedelta, timezone
from typing import Optional, Union
from jose import jwt
from passlib.context import CryptContext
from fastapi import HTTPException, status
from uuid import UUID
import secrets

from app.core.config import get_settings
from app.schemas.token import TokenType

settings = get_settings()

# Password hashing
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=settings.BCRYPT_ROUNDS
)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """Hash a password using bcrypt."""
    return pwd_context.hash(password)

def create_token(
    user_id: Union[str, UUID],
    token_type: TokenType,
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    Create a JWT token (access or refresh).
    """
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        if token_type == TokenType.ACCESS:
            expire = datetime.now(timezone.utc) + timedelta(
                minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
            )
        else:
            expire = datetime.now(timezone.utc) + timedelta(
                days=settings.REFRESH_TOKEN_EXPIRE_DAYS
            )

    if isinstance(user_id, UUID):
        user_id = str(user_id)

    to_encode = {
        "sub": user_id,
        "type": token_type.value,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "jti": secrets.token_hex(16)
    }

    secret = (
        settings.JWT_SECRET_KEY 
        if token_type == TokenType.ACCESS 
        else settings.JWT_REFRESH_SECRET_KEY
    )

    try:
        return jwt.encode(to_encode, secret, algorithm=settings.ALGORITHM)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not create token: {str(e)}"
        )
