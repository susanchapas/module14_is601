"""
Integration tests for the /auth login routes against the test database.

tests/integration/test_user_auth.py covers User.authenticate on its own. These
drive the two HTTP login routes, which is where the reported token lifetime and
the persistence of last_login are decided.
"""

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.datetime_utils import utcnow
from app.database import get_db
from app.main import app
from app.models.user import User
from tests.conftest import create_fake_user, managed_db_session

LOGIN_URL = "/auth/login"
TOKEN_URL = "/auth/token"
REFRESH_URL = "/auth/refresh"

PASSWORD = "SecurePass123!"


@pytest.fixture
def user(db_session) -> User:
    """A committed user whose password is known to the test."""
    data = create_fake_user()
    data["password"] = PASSWORD
    user = User.register(db_session, data)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def client(db_session) -> TestClient:
    """An unauthenticated client sharing the test's session."""
    app.dependency_overrides[get_db] = lambda: db_session
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_login_reports_the_configured_token_lifetime(client, user):
    """
    The reported expiry must follow ACCESS_TOKEN_EXPIRE_MINUTES.

    A stale fallback used to overwrite it with a hardcoded 15 minutes, so
    clients logged out at half the real token life.
    """
    before = utcnow()
    response = client.post(LOGIN_URL, json={"username": user.username, "password": PASSWORD})
    assert response.status_code == 200, response.text

    expires_at = datetime.fromisoformat(response.json()["expires_at"].replace("Z", "+00:00"))
    assert expires_at.tzinfo is not None
    lifetime_minutes = (expires_at - before).total_seconds() / 60

    configured = get_settings().ACCESS_TOKEN_EXPIRE_MINUTES
    assert configured <= lifetime_minutes < configured + 1


def test_token_route_persists_last_login(client, user):
    """
    /auth/token must commit the last_login it writes.

    The update was only flushed, so closing the request's session rolled it
    back and the column stayed null after a successful login.
    """
    assert user.last_login is None

    response = client.post(
        TOKEN_URL,
        data={"username": user.username, "password": PASSWORD},
    )
    assert response.status_code == 200, response.text

    with managed_db_session() as session:
        stored = session.query(User).filter(User.id == user.id).first()
        assert stored.last_login is not None


def test_refresh_returns_a_usable_access_token(client, user):
    """The refresh token issued at login must buy a new access token."""
    login = client.post(LOGIN_URL, json={"username": user.username, "password": PASSWORD})
    assert login.status_code == 200, login.text
    refresh_token = login.json()["refresh_token"]

    before = utcnow()
    response = client.post(REFRESH_URL, json={"refresh_token": refresh_token})
    assert response.status_code == 200, response.text

    body = response.json()
    assert body["token_type"] == "bearer"

    expires_at = datetime.fromisoformat(body["expires_at"].replace("Z", "+00:00"))
    configured = get_settings().ACCESS_TOKEN_EXPIRE_MINUTES
    assert configured <= (expires_at - before).total_seconds() / 60 < configured + 1

    me = client.get("/users/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200, me.text
    assert me.json()["username"] == user.username


def test_refresh_rejects_an_access_token(client, user):
    """
    Access and refresh tokens are signed with different secrets, so an access
    token must not be accepted where a refresh token is expected.
    """
    login = client.post(LOGIN_URL, json={"username": user.username, "password": PASSWORD})
    access_token = login.json()["access_token"]

    response = client.post(REFRESH_URL, json={"refresh_token": access_token})

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid refresh token"


def test_refresh_rejects_a_malformed_token(client):
    response = client.post(REFRESH_URL, json={"refresh_token": "not-a-jwt"})

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid refresh token"


def test_refresh_rejects_a_token_for_a_deleted_user(client, db_session, user):
    """A refresh token outlives the account it names; the row is the authority."""
    login = client.post(LOGIN_URL, json={"username": user.username, "password": PASSWORD})
    refresh_token = login.json()["refresh_token"]

    db_session.delete(user)
    db_session.commit()

    response = client.post(REFRESH_URL, json={"refresh_token": refresh_token})

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid refresh token"
