"""
Tests for the authentication dependencies.

These exercise the real code path: a token minted by User.create_access_token is
decoded by User.verify_token, which returns only the subject UUID. Every other
field on the resulting UserResponse is a placeholder by design, so the tests
assert exactly that.
"""

import pytest
from uuid import uuid4
from fastapi import HTTPException, status
from jose import jwt

from app.auth.dependencies import get_current_user, get_current_active_user
from app.core.config import get_settings
from app.models.user import User
from app.schemas.user import UserResponse

settings = get_settings()


def make_response(**overrides) -> UserResponse:
    """Build a UserResponse for testing get_current_active_user directly."""
    from app.core.datetime_utils import utcnow

    now = utcnow()
    data = {
        "id": uuid4(),
        "username": "testuser",
        "email": "test@example.com",
        "first_name": "Test",
        "last_name": "User",
        "is_active": True,
        "is_verified": True,
        "created_at": now,
        "updated_at": now,
    }
    data.update(overrides)
    return UserResponse(**data)


def test_get_current_user_returns_token_subject():
    user_id = uuid4()
    token = User.create_access_token({"sub": str(user_id)})

    user_response = get_current_user(token=token)

    assert isinstance(user_response, UserResponse)
    assert user_response.id == user_id


def test_get_current_user_fields_other_than_id_are_placeholders():
    """The token carries no profile data, so the rest of the response is filler."""
    token = User.create_access_token({"sub": str(uuid4())})

    user_response = get_current_user(token=token)

    assert user_response.username == "unknown"
    assert user_response.email == "unknown@example.com"
    assert user_response.is_active is True


def test_get_current_user_rejects_malformed_token():
    with pytest.raises(HTTPException) as exc_info:
        get_current_user(token="not-a-jwt")

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert exc_info.value.detail == "Could not validate credentials"


def test_get_current_user_rejects_token_signed_with_wrong_secret():
    token = jwt.encode(
        {"sub": str(uuid4())}, "the-wrong-secret", algorithm=settings.ALGORITHM
    )

    with pytest.raises(HTTPException) as exc_info:
        get_current_user(token=token)

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED


def test_get_current_user_rejects_token_without_subject():
    token = jwt.encode(
        {"type": "access"}, settings.JWT_SECRET_KEY, algorithm=settings.ALGORITHM
    )

    with pytest.raises(HTTPException) as exc_info:
        get_current_user(token=token)

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED


def test_get_current_user_rejects_non_uuid_subject():
    token = jwt.encode(
        {"sub": "not-a-uuid"}, settings.JWT_SECRET_KEY, algorithm=settings.ALGORITHM
    )

    with pytest.raises(HTTPException) as exc_info:
        get_current_user(token=token)

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED


def test_get_current_active_user_passes_through_active_user():
    current_user = make_response(is_active=True)

    assert get_current_active_user(current_user=current_user) is current_user


def test_get_current_active_user_rejects_inactive_user():
    current_user = make_response(is_active=False)

    with pytest.raises(HTTPException) as exc_info:
        get_current_active_user(current_user=current_user)

    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
    assert exc_info.value.detail == "Inactive user"
