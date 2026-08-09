"""
Integration tests for profile updates and password changes against the database.

These check that the User model's profile methods actually persist — that a
committed change survives a fresh query, that uniqueness is enforced by both the
model and the database, and that a rejected change leaves the row untouched.
"""

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.user import User
from tests.conftest import create_fake_user, managed_db_session

CURRENT_PASSWORD = "OldPass123!"
NEW_PASSWORD = "NewPass456!"


@pytest.fixture
def user(db_session) -> User:
    """A committed user whose password is known to the test."""
    data = create_fake_user()
    data["password"] = CURRENT_PASSWORD
    user = User.register(db_session, data)
    db_session.commit()
    db_session.refresh(user)
    return user


def reload(db_session, user: User) -> User:
    """Re-read the user from the database, bypassing the identity map."""
    db_session.expire_all()
    return db_session.query(User).filter(User.id == user.id).one()


# ---------------------------------------------------------------------------
# Profile updates
# ---------------------------------------------------------------------------
def test_update_profile_persists_username_and_email(db_session, user):
    """A committed profile update is visible on a fresh read."""
    user.update_profile(db_session, username="updated_name", email="updated@example.com")
    db_session.commit()

    stored = reload(db_session, user)
    assert stored.username == "updated_name"
    assert stored.email == "updated@example.com"


def test_update_profile_persists_names(db_session, user):
    """First and last name are stored too."""
    user.update_profile(db_session, first_name="Ada", last_name="Lovelace")
    db_session.commit()

    stored = reload(db_session, user)
    assert stored.first_name == "Ada"
    assert stored.last_name == "Lovelace"


def test_update_profile_leaves_omitted_fields_alone(db_session, user):
    """A partial update only writes the fields it was given."""
    original_email = user.email
    original_last_name = user.last_name

    user.update_profile(db_session, username="only_the_username")
    db_session.commit()

    stored = reload(db_session, user)
    assert stored.username == "only_the_username"
    assert stored.email == original_email
    assert stored.last_name == original_last_name


def test_update_profile_bumps_updated_at(db_session, user):
    """The stored updated_at moves forward when the profile changes."""
    original_updated_at = user.updated_at

    user.update_profile(db_session, first_name="Timestamped")
    db_session.commit()

    assert reload(db_session, user).updated_at > original_updated_at


def test_update_profile_does_not_touch_the_password(db_session, user):
    """Editing the profile leaves the credentials working."""
    user.update_profile(db_session, username="still_me")
    db_session.commit()

    assert reload(db_session, user).verify_password(CURRENT_PASSWORD) is True


def test_update_profile_keeping_the_same_username_is_allowed(db_session, user):
    """Re-submitting the form unchanged must not trip the uniqueness check."""
    user.update_profile(db_session, username=user.username, email=user.email)
    db_session.commit()

    assert reload(db_session, user).username == user.username


@pytest.mark.parametrize("field", ["username", "email"])
def test_update_profile_rejects_a_value_taken_by_another_user(db_session, user, field):
    """A username or email already in use by someone else is refused."""
    other = User.register(db_session, create_fake_user())
    db_session.commit()

    original = getattr(user, field)
    with pytest.raises(ValueError, match="already exists"):
        user.update_profile(db_session, **{field: getattr(other, field)})

    db_session.rollback()
    assert getattr(reload(db_session, user), field) == original


def test_update_profile_uniqueness_is_enforced_by_the_database(db_session, user):
    """Even bypassing the model check, the unique constraint holds."""
    other = User.register(db_session, create_fake_user())
    db_session.commit()

    user.username = other.username
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_update_profile_is_visible_to_a_separate_session(db_session, user):
    """The change is committed, not just cached in the writing session."""
    user.update_profile(db_session, first_name="Committed")
    db_session.commit()

    with managed_db_session() as session:
        assert session.query(User).filter(User.id == user.id).one().first_name == "Committed"


# ---------------------------------------------------------------------------
# Password changes
# ---------------------------------------------------------------------------
def test_change_password_persists_the_new_hash(db_session, user):
    """After committing, the stored hash verifies the new password."""
    user.change_password(CURRENT_PASSWORD, NEW_PASSWORD)
    db_session.commit()

    stored = reload(db_session, user)
    assert stored.verify_password(NEW_PASSWORD) is True
    assert stored.verify_password(CURRENT_PASSWORD) is False


def test_change_password_never_stores_plain_text(db_session, user):
    """The plain-text password does not reach the database column."""
    user.change_password(CURRENT_PASSWORD, NEW_PASSWORD)
    db_session.commit()

    assert reload(db_session, user).password != NEW_PASSWORD


def test_change_password_allows_authenticating_with_the_new_password(db_session, user):
    """The full authenticate() path works with the new credentials."""
    user.change_password(CURRENT_PASSWORD, NEW_PASSWORD)
    db_session.commit()

    assert User.authenticate(db_session, user.username, NEW_PASSWORD) is not None
    assert User.authenticate(db_session, user.username, CURRENT_PASSWORD) is None


def test_change_password_with_a_wrong_current_password_stores_nothing(db_session, user):
    """A rejected change leaves the stored hash exactly as it was."""
    original_hash = user.password

    with pytest.raises(ValueError, match="Current password is incorrect"):
        user.change_password("NotMyPassword123!", NEW_PASSWORD)
    db_session.commit()

    stored = reload(db_session, user)
    assert stored.password == original_hash
    assert stored.verify_password(CURRENT_PASSWORD) is True


def test_change_password_does_not_affect_other_users(db_session, user):
    """One user's password change is scoped to that user's row."""
    other_data = create_fake_user()
    other_data["password"] = CURRENT_PASSWORD
    other = User.register(db_session, other_data)
    db_session.commit()

    user.change_password(CURRENT_PASSWORD, NEW_PASSWORD)
    db_session.commit()

    assert reload(db_session, other).verify_password(CURRENT_PASSWORD) is True
