"""
Integration tests for the GET /calculations/stats endpoint.

These drive the real route through FastAPI against the test database, so they
cover the things the unit tests cannot: routing, authentication, ownership
scoping and the response schema. The aggregation rules themselves are covered in
tests/unit/test_calculation_stats.py.
"""

import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import get_current_active_user
from app.database import get_db
from app.main import app
from app.models.calculation import Calculation
from app.models.user import User
from tests.conftest import create_fake_user

STATS_URL = "/calculations/stats"


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


@pytest.fixture
def anonymous_client(db_session) -> TestClient:
    """A client with no authentication override, to test the auth guard."""
    app.dependency_overrides[get_db] = lambda: db_session
    yield TestClient(app)
    app.dependency_overrides.clear()


def add_calculation(db_session, owner: User, calculation_type: str, inputs: list) -> Calculation:
    """Save a calculation directly, bypassing the create endpoint."""
    calculation = Calculation.create(calculation_type, owner.id, inputs)
    calculation.result = calculation.get_result()
    db_session.add(calculation)
    db_session.commit()
    return calculation


def get_stats(client: TestClient) -> dict:
    """Fetch the summary, asserting the request succeeded."""
    response = client.get(STATS_URL)
    assert response.status_code == 200, response.text
    return response.json()


# ---------------------------------------------------------------------------
# Routing and authentication
# ---------------------------------------------------------------------------
def test_stats_requires_authentication(anonymous_client):
    """Without a token the summary is refused, not served empty."""
    assert anonymous_client.get(STATS_URL).status_code == 401


def test_stats_path_is_not_read_as_a_calculation_id(client):
    """
    "stats" must match the literal route, not /calculations/{calc_id}.

    Declaring the routes the other way round would answer 400 "Invalid
    calculation id format" here, so this guards the ordering.
    """
    response = client.get(STATS_URL)

    assert response.status_code == 200
    assert "total_calculations" in response.json()


def test_stats_response_matches_the_schema(client):
    """Every documented field is present in the response."""
    stats = get_stats(client)

    assert set(stats) == {
        "total_calculations",
        "average_operands",
        "counts_by_type",
        "most_used_type",
        "last_calculation_at",
    }


# ---------------------------------------------------------------------------
# Reported values
# ---------------------------------------------------------------------------
def test_stats_for_a_user_with_no_calculations(client):
    """A new account gets a zeroed summary rather than a 404."""
    stats = get_stats(client)

    assert stats["total_calculations"] == 0
    assert stats["average_operands"] == 0.0
    assert stats["most_used_type"] is None
    assert stats["last_calculation_at"] is None
    assert stats["counts_by_type"] == {
        "addition": 0,
        "subtraction": 0,
        "multiplication": 0,
        "division": 0,
    }


def test_stats_count_calculations_made_through_the_api(client):
    """Calculations created over the endpoint show up in the summary."""
    for inputs in ([1, 2], [3, 4], [5, 6]):
        assert client.post(
            "/calculations", json={"type": "addition", "inputs": inputs}
        ).status_code == 201

    stats = get_stats(client)
    assert stats["total_calculations"] == 3
    assert stats["counts_by_type"]["addition"] == 3
    assert stats["most_used_type"] == "addition"


def test_stats_average_operands_is_rounded(client, db_session, user):
    """Seven operands over three calculations round to 2.33."""
    add_calculation(db_session, user, "addition", [1, 2])
    add_calculation(db_session, user, "addition", [1, 2])
    add_calculation(db_session, user, "addition", [1, 2, 3])

    assert get_stats(client)["average_operands"] == 2.33


def test_stats_break_down_mixed_types(client, db_session, user):
    """Each type is tallied under its own name."""
    add_calculation(db_session, user, "addition", [1, 2])
    add_calculation(db_session, user, "division", [8, 2])
    add_calculation(db_session, user, "division", [9, 3])

    stats = get_stats(client)
    assert stats["counts_by_type"] == {
        "addition": 1,
        "subtraction": 0,
        "multiplication": 0,
        "division": 2,
    }
    assert stats["most_used_type"] == "division"


def test_stats_report_the_last_calculation_time(client, db_session, user):
    """The timestamp of the newest stored calculation is reported."""
    add_calculation(db_session, user, "addition", [1, 2])
    newest = add_calculation(db_session, user, "multiplication", [2, 3])

    assert get_stats(client)["last_calculation_at"] == newest.created_at.isoformat()


# ---------------------------------------------------------------------------
# Ownership and freshness
# ---------------------------------------------------------------------------
def test_stats_ignore_other_users_calculations(client, db_session, user):
    """The summary is scoped to the authenticated user's own history."""
    stranger = User.register(db_session, create_fake_user())
    db_session.commit()
    add_calculation(db_session, stranger, "subtraction", [9, 1, 1])
    add_calculation(db_session, user, "addition", [1, 2])

    stats = get_stats(client)
    assert stats["total_calculations"] == 1
    assert stats["counts_by_type"]["subtraction"] == 0


def test_stats_follow_a_deletion(client, db_session, user):
    """Deleting a calculation removes it from the summary."""
    doomed = add_calculation(db_session, user, "addition", [1, 2])
    add_calculation(db_session, user, "division", [8, 2])

    assert client.delete(f"/calculations/{doomed.id}").status_code == 204

    stats = get_stats(client)
    assert stats["total_calculations"] == 1
    assert stats["counts_by_type"]["addition"] == 0
    assert stats["most_used_type"] == "division"


def test_stats_follow_an_update(client, db_session, user):
    """Editing the inputs changes the average number of operands."""
    calculation = add_calculation(db_session, user, "addition", [1, 2])
    assert get_stats(client)["average_operands"] == 2.0

    assert client.put(
        f"/calculations/{calculation.id}", json={"inputs": [1, 2, 3, 4]}
    ).status_code == 200

    assert get_stats(client)["average_operands"] == 4.0
