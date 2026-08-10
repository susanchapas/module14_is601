from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.datetime_utils import utcnow
from app.database import get_db
from app.models.user import User
from app.schemas.user import UserResponse

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token")

def get_current_user(
    token: str = Depends(oauth2_scheme)
) -> UserResponse:
    """
    Dependency to get the current user from the JWT token without a database lookup.

    User.verify_token yields only the subject UUID, so every field other than the
    id is a placeholder. Endpoints that need real profile data must depend on
    get_current_user_record instead.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    user_id = User.verify_token(token)
    if user_id is None:
        raise credentials_exception

    now = utcnow()
    return UserResponse(
        id=user_id,
        username="unknown",
        email="unknown@example.com",
        first_name="Unknown",
        last_name="User",
        is_active=True,
        is_verified=False,
        created_at=now,
        updated_at=now,
    )

def get_current_active_user(
    current_user: UserResponse = Depends(get_current_user)
) -> UserResponse:
    """
    Dependency to ensure that the current user is active.
    """
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )
    return current_user

def get_current_user_record(
    current_user: UserResponse = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> User:
    """
    Dependency to load the current user's database record.

    get_current_user builds its UserResponse from the token alone, so the only
    field it can be trusted for is the id. Endpoints that read or write stored
    profile data need the real row instead.
    """
    user = db.query(User).filter(User.id == current_user.id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    return user
