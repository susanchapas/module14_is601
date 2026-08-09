"""
Unit tests for the profile-update and password-change logic.

These exercise the pure logic only: the schema validators and the User methods
that do not need a database session. Persistence is covered in
tests/integration/test_profile.py, and the browser flow in
tests/e2e/test_profile_e2e.py.
"""

import pytest
from pydantic import ValidationError

from app.models.user import User
from app.schemas.user import PasswordUpdate, UserUpdate, validate_password_strength

CURRENT_PASSWORD = "OldPass123!"
NEW_PASSWORD = "NewPass456!"


def make_user(password: str = CURRENT_PASSWORD) -> User:
    """Build an unsaved User whose password is already hashed."""
    return User(
        first_name="Test",
        last_name="User",
        email="test.user@example.com",
        username="testuser",
        password=User.hash_password(password),
    )


# ---------------------------------------------------------------------------
# Password strength rules
# ---------------------------------------------------------------------------
def test_validate_password_strength_accepts_strong_password():
    """A password meeting every rule is returned unchanged."""
    assert validate_password_strength("StrongPass1!") == "StrongPass1!"


@pytest.mark.parametrize(
    "password, expected_message",
    [
        ("Sh0rt!", "at least 8 characters"),
        ("lowercase1!", "uppercase letter"),
        ("UPPERCASE1!", "lowercase letter"),
        ("NoDigitsHere!", "at least one digit"),
        ("NoSpecial123", "special character"),
    ],
    ids=["too_short", "no_uppercase", "no_lowercase", "no_digit", "no_special"],
)
def test_validate_password_strength_rejects_weak_password(password, expected_message):
    """Each strength rule is enforced with its own message."""
    with pytest.raises(ValueError, match=expected_message):
        validate_password_strength(password)


# ---------------------------------------------------------------------------
# PasswordUpdate schema
# ---------------------------------------------------------------------------
def test_password_update_accepts_valid_change():
    """A well-formed change request validates."""
    payload = PasswordUpdate(
        current_password=CURRENT_PASSWORD,
        new_password=NEW_PASSWORD,
        confirm_new_password=NEW_PASSWORD,
    )
    assert payload.new_password == NEW_PASSWORD


@pytest.mark.parametrize(
    "new_password, confirm_new_password, expected_message",
    [
        (NEW_PASSWORD, "Mismatch123!", "confirmation do not match"),
        (CURRENT_PASSWORD, CURRENT_PASSWORD, "must be different"),
        ("NoSpecial123", "NoSpecial123", "special character"),
    ],
    ids=["confirmation_mismatch", "same_as_current", "weak_new_password"],
)
def test_password_update_rejects_invalid_change(
    new_password, confirm_new_password, expected_message
):
    """Mismatched, unchanged or weak new passwords are rejected."""
    with pytest.raises(ValidationError, match=expected_message):
        PasswordUpdate(
            current_password=CURRENT_PASSWORD,
            new_password=new_password,
            confirm_new_password=confirm_new_password,
        )


# ---------------------------------------------------------------------------
# UserUpdate schema
# ---------------------------------------------------------------------------
def test_user_update_allows_partial_update():
    """Omitted fields stay None so the endpoint can leave them untouched."""
    payload = UserUpdate(username="newname")
    assert payload.username == "newname"
    assert payload.email is None
    assert payload.model_dump(exclude_none=True) == {"username": "newname"}


def test_user_update_rejects_empty_payload():
    """An update with nothing in it is a client error, not a silent no-op."""
    with pytest.raises(ValidationError, match="At least one field"):
        UserUpdate()


@pytest.mark.parametrize(
    "field, value",
    [
        ("username", "ab"),
        ("email", "not-an-email"),
        ("first_name", ""),
    ],
    ids=["username_too_short", "malformed_email", "empty_first_name"],
)
def test_user_update_rejects_invalid_field(field, value):
    """Field-level constraints still apply to the optional fields."""
    with pytest.raises(ValidationError):
        UserUpdate(**{field: value})


# ---------------------------------------------------------------------------
# User.change_password
# ---------------------------------------------------------------------------
def test_change_password_stores_a_hash_not_the_plain_text():
    """The new password is hashed before it is stored."""
    user = make_user()

    user.change_password(CURRENT_PASSWORD, NEW_PASSWORD)

    assert user.password != NEW_PASSWORD
    assert user.verify_password(NEW_PASSWORD) is True


def test_change_password_invalidates_the_old_password():
    """The previous password stops working once it is replaced."""
    user = make_user()

    user.change_password(CURRENT_PASSWORD, NEW_PASSWORD)

    assert user.verify_password(CURRENT_PASSWORD) is False


def test_change_password_refreshes_updated_at():
    """A password change bumps updated_at."""
    user = make_user()
    user.updated_at = None

    user.change_password(CURRENT_PASSWORD, NEW_PASSWORD)

    assert user.updated_at is not None


def test_change_password_rejects_wrong_current_password():
    """Without the correct current password nothing changes."""
    user = make_user()
    original_hash = user.password

    with pytest.raises(ValueError, match="Current password is incorrect"):
        user.change_password("WrongPass123!", NEW_PASSWORD)

    assert user.password == original_hash


def test_change_password_rejects_reusing_the_current_password():
    """Setting the same password again is refused."""
    user = make_user()

    with pytest.raises(ValueError, match="must be different"):
        user.change_password(CURRENT_PASSWORD, CURRENT_PASSWORD)


def test_change_password_produces_a_different_hash_each_time():
    """Hashing is salted, so the same password never yields the same hash."""
    first = make_user()
    second = make_user()

    assert first.password != second.password


# ---------------------------------------------------------------------------
# User.update_profile (paths that need no database)
# ---------------------------------------------------------------------------
def test_update_profile_with_no_fields_is_a_no_op():
    """An update of only None values changes nothing and touches no database."""
    user = make_user()

    result = user.update_profile(None, username=None, email=None)

    assert result is user
    assert user.username == "testuser"


def test_update_profile_rejects_unknown_fields():
    """Fields outside the editable set are refused, so is_active cannot be set."""
    user = make_user()

    with pytest.raises(ValueError, match="is_active"):
        user.update_profile(None, is_active=False)


def test_update_profile_applies_names_without_a_uniqueness_check():
    """First and last name are not unique, so no database query is needed."""
    user = make_user()

    user.update_profile(None, first_name="Renamed", last_name="Person")

    assert user.first_name == "Renamed"
    assert user.last_name == "Person"
