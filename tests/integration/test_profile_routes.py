"""
Integration tests for the /users/me routes against the test database.

tests/integration/test_profile.py covers the User model's own persistence. These
drive the HTTP routes the profile page calls, so they cover the parts the model
tests cannot: routing, the auth guard, request validation, the committed result
and the rollback when a change is refused.
"""

import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import get_current_active_user
from app.database import get_db
from app.main import app
from app.models.user import User
from app.schemas.user import UserResponse
from tests.conftest import create_fake_user

PROFILE_URL = "/users/me"
PASSWORD_URL = "/users/me/password"

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


@pytest.fixture
def client(db_session, user) -> TestClient:
    """A client authenticated as `user` and sharing the test's session."""
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_active_user] = lambda: UserResponse.model_validate(user)
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def anonymous_client(db_session) -> TestClient:
    """A client with no authentication override, to test the auth guard."""
    app.dependency_overrides[get_db] = lambda: db_session
    yield TestClient(app)
    app.dependency_overrides.clear()


def reload(db_session, user: User) -> User:
    """Re-read the user from the database, bypassing the identity map."""
    db_session.expire_all()
    return db_session.query(User).filter(User.id == user.id).one()


def password_payload(current=CURRENT_PASSWORD, new=NEW_PASSWORD, confirm=None) -> dict:
    """Build a change-password body, confirming the new password by default."""
    return {
        "current_password": current,
        "new_password": new,
        "confirm_new_password": new if confirm is None else confirm,
    }


# ---------------------------------------------------------------------------
# GET /users/me
# ---------------------------------------------------------------------------
def test_read_profile_returns_the_stored_record(client, user):
    """The route reads the row from the database, not from the token."""
    response = client.get(PROFILE_URL)

    assert response.status_code == 200
    body = response.json()
    assert body["username"] == user.username
    assert body["email"] == user.email
    assert body["first_name"] == user.first_name
    assert body["last_name"] == user.last_name


def test_read_profile_never_returns_the_password(client):
    """The response schema keeps the stored hash out of the body."""
    body = client.get(PROFILE_URL).json()

    assert "password" not in body


def test_read_profile_requires_authentication(anonymous_client):
    """An unauthenticated request is refused."""
    assert anonymous_client.get(PROFILE_URL).status_code == 401


# ---------------------------------------------------------------------------
# PUT /users/me
# ---------------------------------------------------------------------------
def test_update_profile_commits_the_change(client, db_session, user):
    """A successful update is committed and visible on a fresh read."""
    response = client.put(
        PROFILE_URL, json={"username": "route_updated", "email": "route.updated@example.com"}
    )

    assert response.status_code == 200
    assert response.json()["username"] == "route_updated"

    stored = reload(db_session, user)
    assert stored.username == "route_updated"
    assert stored.email == "route.updated@example.com"


def test_update_profile_only_writes_the_fields_it_was_sent(client, db_session, user):
    """Omitted fields keep their stored values."""
    original_email = user.email

    response = client.put(PROFILE_URL, json={"first_name": "Ada"})

    assert response.status_code == 200
    stored = reload(db_session, user)
    assert stored.first_name == "Ada"
    assert stored.email == original_email


def test_update_profile_leaves_the_password_working(client, db_session, user):
    """Editing the profile does not disturb the credentials."""
    client.put(PROFILE_URL, json={"first_name": "Unchanged"})

    assert reload(db_session, user).verify_password(CURRENT_PASSWORD) is True


def test_update_profile_rejects_a_username_taken_by_another_user(client, db_session, user):
    """A duplicate username is a 400 and nothing is written."""
    other = User.register(db_session, create_fake_user())
    db_session.commit()
    original_username = user.username

    response = client.put(PROFILE_URL, json={"username": other.username})

    assert response.status_code == 400
    assert "already exists" in response.json()["detail"]
    assert reload(db_session, user).username == original_username


def test_update_profile_rejects_a_malformed_email(client, db_session, user):
    """A bad email fails schema validation before it reaches the database."""
    original_email = user.email

    response = client.put(PROFILE_URL, json={"email": "not-an-email"})

    assert response.status_code == 422
    assert reload(db_session, user).email == original_email


def test_update_profile_requires_authentication(anonymous_client, db_session, user):
    """An unauthenticated update is refused and stores nothing."""
    original_username = user.username

    response = anonymous_client.put(PROFILE_URL, json={"username": "anonymous_edit"})

    assert response.status_code == 401
    assert reload(db_session, user).username == original_username


# ---------------------------------------------------------------------------
# POST /users/me/password
# ---------------------------------------------------------------------------
def test_change_password_commits_the_new_hash(client, db_session, user):
    """The new password is stored and the old one stops working."""
    response = client.post(PASSWORD_URL, json=password_payload())

    assert response.status_code == 200
    assert response.json() == {"message": "Password updated successfully"}

    stored = reload(db_session, user)
    assert stored.verify_password(NEW_PASSWORD) is True
    assert stored.verify_password(CURRENT_PASSWORD) is False


def test_change_password_never_stores_plain_text(client, db_session, user):
    """The plain-text password does not reach the stored column."""
    client.post(PASSWORD_URL, json=password_payload())

    assert reload(db_session, user).password != NEW_PASSWORD


def test_change_password_allows_authenticating_with_the_new_password(client, db_session, user):
    """The committed hash works through the full authenticate() path."""
    client.post(PASSWORD_URL, json=password_payload())

    assert User.authenticate(db_session, user.username, NEW_PASSWORD) is not None
    assert User.authenticate(db_session, user.username, CURRENT_PASSWORD) is None


def test_change_password_rejects_a_wrong_current_password(client, db_session, user):
    """The wrong current password is a 400 and the stored hash is untouched."""
    original_hash = user.password

    response = client.post(PASSWORD_URL, json=password_payload(current="WrongPass123!"))

    assert response.status_code == 400
    assert "Current password is incorrect" in response.json()["detail"]

    stored = reload(db_session, user)
    assert stored.password == original_hash
    assert stored.verify_password(CURRENT_PASSWORD) is True


@pytest.mark.parametrize(
    "payload, expected_fragment",
    [
        (password_payload(confirm="Mismatch456!"), "do not match"),
        (password_payload(new=CURRENT_PASSWORD), "must be different"),
        (password_payload(new="NoSpecial1234"), "special character"),
        (password_payload(new="nouppercase1!"), "uppercase letter"),
    ],
    ids=["confirmation_mismatch", "same_as_current", "no_special", "no_uppercase"],
)
def test_change_password_rejects_an_invalid_body(
    client, db_session, user, payload, expected_fragment
):
    """Schema-level failures are reported and leave the password alone."""
    original_hash = user.password

    response = client.post(PASSWORD_URL, json=payload)

    assert response.status_code == 422
    assert expected_fragment in response.text
    assert reload(db_session, user).password == original_hash


def test_change_password_requires_authentication(anonymous_client, db_session, user):
    """An unauthenticated change is refused and stores nothing."""
    original_hash = user.password

    response = anonymous_client.post(PASSWORD_URL, json=password_payload())

    assert response.status_code == 401
    assert reload(db_session, user).password == original_hash


def test_change_password_does_not_affect_other_users(client, db_session):
    """The change is scoped to the authenticated user's row."""
    other_data = create_fake_user()
    other_data["password"] = CURRENT_PASSWORD
    other = User.register(db_session, other_data)
    db_session.commit()

    client.post(PASSWORD_URL, json=password_payload())

    assert reload(db_session, other).verify_password(CURRENT_PASSWORD) is True
