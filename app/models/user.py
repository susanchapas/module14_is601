# app/models/user.py
"""
User Model Module

This module defines the User model for the application, handling:
- User authentication
- Password hashing
- Token generation and validation
- User registration

The User model is designed to follow security best practices:
- Secure password hashing
- JWT-based authentication
- Account status tracking
- Timezone-aware timestamps
"""

import uuid
from datetime import timedelta
from sqlalchemy import Column, String, Boolean, DateTime, or_
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship
from app.core.config import get_settings
from app.core.datetime_utils import utcnow
from app.database import Base
from app.models.calculation import Calculation

settings = get_settings()

class User(Base):
    """
    User model with authentication and token management capabilities.
    
    This model represents a user in the system and provides methods for:
    - User registration and validation
    - Password hashing and verification
    - JWT token generation
    - Authentication
    
    It follows the Active Record pattern, where the model encapsulates
    both data and behavior related to users.
    """
    
    __tablename__ = "users"
    
    # Primary key and identifying fields
    id = Column(PG_UUID(as_uuid=True), 
                primary_key=True, 
                default=uuid.uuid4,  # Auto-generate UUIDs
                unique=True, 
                index=True)          # Index for faster lookups
    
    username = Column(String(50), 
                      unique=True,    # Prevent duplicate usernames 
                      nullable=False, 
                      index=True)     # Index for faster lookups and login
    
    email = Column(String, 
                   unique=True,       # Prevent duplicate emails
                   nullable=False, 
                   index=True)        # Index for faster lookups and login
    
    password = Column(String, 
                      nullable=False) # Stored as hashed, not plaintext
    
    # Personal information
    first_name = Column(String(50), nullable=False)
    last_name = Column(String(50), nullable=False)
    
    # Status flags for account management
    is_active = Column(Boolean, 
                       default=True)  # For disabling accounts without deletion
    
    is_verified = Column(Boolean, 
                         default=False) # For email verification status
    
    # Timestamps - All timezone-aware
    created_at = Column(DateTime(timezone=True), 
                        default=utcnow, 
                        nullable=False)
    
    updated_at = Column(DateTime(timezone=True), 
                        default=utcnow, 
                        onupdate=utcnow,  # Auto-update on record changes
                        nullable=False)
    
    last_login = Column(DateTime(timezone=True), 
                        nullable=True)  # Track login activity
    
    # Relationships - one-to-many with Calculation model
    calculations = relationship("Calculation", 
                               back_populates="user", 
                               cascade="all, delete-orphan")  # Delete user's calculations when user is deleted
    
    def __init__(self, *args, **kwargs):
        """Initialize a new user, handling password hashing if provided."""
        if "hashed_password" in kwargs:
            kwargs["password"] = kwargs.pop("hashed_password")
        super().__init__(*args, **kwargs)

    def __str__(self):
        """String representation of the user."""
        return f"<User(name={self.first_name} {self.last_name}, email={self.email})>"

    def update(self, **kwargs):
        """
        Update user attributes and ensure updated_at is refreshed.
        
        Args:
            **kwargs: Attributes to update
            
        Returns:
            User: The updated user instance
        """
        for key, value in kwargs.items():
            setattr(self, key, value)
        self.updated_at = utcnow()
        return self

    @property
    def hashed_password(self):
        """Return the stored hashed password."""
        return self.password

    def verify_password(self, plain_password: str) -> bool:
        """
        Verify a plain-text password against this user's stored hashed password.
        
        Args:
            plain_password: The plain-text password to verify
            
        Returns:
            bool: True if password matches, False otherwise
        """
        from app.auth.jwt import verify_password
        return verify_password(plain_password, self.password)

    @classmethod
    def hash_password(cls, password: str) -> str:
        """
        Hash a plain-text password using the application's password hashing utility.
        
        Args:
            password: The plain-text password to hash
            
        Returns:
            str: The hashed password
        """
        from app.auth.jwt import get_password_hash
        return get_password_hash(password)

    def update_profile(self, db, **fields):
        """
        Update this user's profile fields, keeping username and email unique.

        Fields passed as None are ignored, so a partial update only touches what
        the caller actually supplied.

        Args:
            db: SQLAlchemy database session
            **fields: Any of username, email, first_name, last_name

        Returns:
            User: This user instance, updated

        Raises:
            ValueError: If an unknown field is supplied, or if the new username
                or email is already taken by another user
        """
        allowed = {"username", "email", "first_name", "last_name"}
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"Cannot update field(s): {', '.join(sorted(unknown))}")

        updates = {key: value for key, value in fields.items() if value is not None}
        if not updates:
            return self

        conflicts = [
            getattr(type(self), key) == value
            for key, value in updates.items()
            if key in ("username", "email")
        ]
        if conflicts:
            taken = db.query(type(self)).filter(
                or_(*conflicts), type(self).id != self.id
            ).first()
            if taken:
                raise ValueError("Username or email already exists")

        return self.update(**updates)

    def change_password(self, current_password: str, new_password: str):
        """
        Replace this user's password after verifying the current one.

        The new password is stored hashed, never in plain text.

        Args:
            current_password: The user's existing plain-text password
            new_password: The plain-text password to store

        Returns:
            User: This user instance, with the new password hash

        Raises:
            ValueError: If the current password is wrong, or the new password is
                the same as the current one
        """
        if not self.verify_password(current_password):
            raise ValueError("Current password is incorrect")
        if current_password == new_password:
            raise ValueError("New password must be different from current password")

        return self.update(password=self.hash_password(new_password))

    @classmethod
    def register(cls, db, user_data: dict):
        """
        Register a new user.

        Args:
            db: SQLAlchemy database session
            user_data: Dictionary containing user registration data
            
        Returns:
            User: The newly created user instance
            
        Raises:
            ValueError: If password is invalid or username/email already exists
        """
        password = user_data.get("password")
        if not password or len(password) < 6:
            raise ValueError("Password must be at least 6 characters long")
        
        # Check for duplicate email or username
        existing_user = db.query(cls).filter(
            or_(cls.email == user_data["email"], cls.username == user_data["username"])
        ).first()
        if existing_user:
            raise ValueError("Username or email already exists")
        
        # Create new user instance
        hashed_password = cls.hash_password(password)
        user = cls(
            first_name=user_data["first_name"],
            last_name=user_data["last_name"],
            email=user_data["email"],
            username=user_data["username"],
            password=hashed_password,
            is_active=True,
            is_verified=False
        )
        db.add(user)
        return user

    @classmethod
    def authenticate(cls, db, username_or_email: str, password: str):
        """
        Authenticate a user by username/email and password.
        
        Args:
            db: SQLAlchemy database session
            username_or_email: Username or email to authenticate
            password: Password to verify
            
        The updated last_login is committed here so that every caller persists
        it, whatever route it came from.

        Returns:
            dict: Authentication result with tokens and user data, or None if authentication fails
        """
        user = db.query(cls).filter(
            or_(cls.username == username_or_email, cls.email == username_or_email)
        ).first()

        if not user or not user.verify_password(password):
            return None

        # Update the last_login timestamp
        user.last_login = utcnow()
        db.commit()

        return {
            **cls.issue_access_token(user),
            "refresh_token": cls.create_refresh_token({"sub": str(user.id)}),
            "user": user
        }

    @classmethod
    def issue_access_token(cls, user) -> dict:
        """
        Mint an access token for a user and report when it expires.

        Shared by /auth/login and /auth/refresh so that both report the same
        lifetime, derived from ACCESS_TOKEN_EXPIRE_MINUTES.
        """
        return {
            "access_token": cls.create_access_token({"sub": str(user.id)}),
            "token_type": "bearer",
            "expires_at": utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        }

    @classmethod
    def create_access_token(cls, data: dict) -> str:
        """
        Create a JWT access token.
        
        Args:
            data: Token payload data
            
        Returns:
            str: JWT access token
        """
        from app.auth.jwt import create_token
        from app.schemas.token import TokenType
        return create_token(data["sub"], TokenType.ACCESS)

    @classmethod
    def create_refresh_token(cls, data: dict) -> str:
        """
        Create a JWT refresh token.
        
        Args:
            data: Token payload data
            
        Returns:
            str: JWT refresh token
        """
        from app.auth.jwt import create_token
        from app.schemas.token import TokenType
        return create_token(data["sub"], TokenType.REFRESH)

    @classmethod
    def verify_token(cls, token: str, token_type=None):
        """
        Verify a JWT token and return the user identifier.

        Access and refresh tokens are signed with different secrets, so the
        expected type also selects which secret the signature is checked
        against. A refresh token therefore cannot be used as an access token,
        or the reverse.

        Args:
            token: JWT token to verify
            token_type: Expected TokenType, defaulting to an access token

        Returns:
            UUID: User ID if token is valid, None otherwise
        """
        from app.core.config import settings
        from app.schemas.token import TokenType
        from jose import jwt, JWTError

        token_type = token_type or TokenType.ACCESS
        secret = (
            settings.JWT_SECRET_KEY
            if token_type == TokenType.ACCESS
            else settings.JWT_REFRESH_SECRET_KEY
        )
        try:
            payload = jwt.decode(token, secret, algorithms=[settings.ALGORITHM])
            if payload.get("type", token_type.value) != token_type.value:
                return None
            sub = payload.get("sub")
            if sub is None:
                return None
            try:
                return uuid.UUID(sub)
            except (ValueError, TypeError):
                return None
        except JWTError:
            return None