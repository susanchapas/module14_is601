"""
Integration tests for the /calculations routes against the test database.

tests/integration/test_calculation.py covers the Calculation model's own
arithmetic. These drive the HTTP routes, where the stored row and the response
schema have to agree.
"""

import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import get_current_active_user
from app.database import get_db
from app.main import app
from app.models.calculation import Calculation
from app.models.user import User
from tests.conftest import create_fake_user

CALCULATIONS_URL = "/calculations"


@pytest.fixture
def user(db_session) -> User:
    """A committed user with no calculations yet."""
    user = User.register(db_session, create_fake_user())
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def client(db_session, user) -> TestClient:
    """A client authenticated as `user` and sharing the test's session."""
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_active_user] = lambda: user
    yield TestClient(app)
    app.dependency_overrides.clear()


def add_calculation(db_session, owner: User, inputs: list, result) -> Calculation:
    """Save a calculation directly, so the stored result can be chosen."""
    calculation = Calculation.create("addition", owner.id, inputs)
    calculation.result = result
    db_session.add(calculation)
    db_session.commit()
    db_session.refresh(calculation)
    return calculation


def test_empty_patch_leaves_updated_at_unchanged(client, db_session, user):
    """
    A PATCH with no fields is documented as a no-op, so it must not touch the row.

    The handler used to stamp updated_at and commit even with nothing to apply.
    """
    calculation = add_calculation(db_session, user, [1, 2], 3.0)
    original_updated_at = calculation.updated_at

    response = client.patch(f"{CALCULATIONS_URL}/{calculation.id}", json={})
    assert response.status_code == 200, response.text

    db_session.refresh(calculation)
    assert calculation.updated_at == original_updated_at


def test_listing_tolerates_a_null_result(client, db_session, user):
    """
    The result column is nullable, so the response schema must accept null.

    A required float made any uncomputed row fail serialization, turning the
    whole listing into a 500.
    """
    add_calculation(db_session, user, [1, 2], None)

    response = client.get(CALCULATIONS_URL)
    assert response.status_code == 200, response.text

    results = [item["result"] for item in response.json()]
    assert results == [None]
