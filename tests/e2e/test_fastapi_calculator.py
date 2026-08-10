from datetime import datetime, timezone
from uuid import uuid4

import pytest
import requests

# Import the Calculation model for direct model tests.
from app.models.calculation import Calculation


# ---------------------------------------------------------------------------
# Helper Fixtures and Functions
# ---------------------------------------------------------------------------
# Note: the `base_url` fixture is provided by tests/conftest.py.
def _parse_datetime(dt_str: str) -> datetime:
    """Helper function to parse datetime strings from API responses."""
    if dt_str.endswith('Z'):
        dt_str = dt_str.replace('Z', '+00:00')
    return datetime.fromisoformat(dt_str)

def register_and_login(base_url: str, user_data: dict) -> dict:
    """
    Registers a new user and logs in, returning the token response data.
    """
    reg_url = f"{base_url}/auth/register"
    login_url = f"{base_url}/auth/login"
    
    reg_response = requests.post(reg_url, json=user_data)
    assert reg_response.status_code == 201, f"User registration failed: {reg_response.text}"
    
    login_payload = {
        "username": user_data["username"],
        "password": user_data["password"]
    }
    login_response = requests.post(login_url, json=login_payload)
    assert login_response.status_code == 200, f"Login failed: {login_response.text}"
    return login_response.json()

def make_auth_headers(base_url: str) -> dict:
    """
    Register a throwaway user and return Authorization headers for it.
    """
    suffix = uuid4()
    user_data = {
        "first_name": "Calc",
        "last_name": "User",
        "email": f"calc.user{suffix}@example.com",
        "username": f"calc_user_{suffix}",
        "password": "SecurePass123!",
        "confirm_password": "SecurePass123!"
    }
    token_data = register_and_login(base_url, user_data)
    return {"Authorization": f"Bearer {token_data['access_token']}"}

@pytest.fixture
def auth_headers(base_url: str) -> dict:
    """Authorization headers for a freshly registered user."""
    return make_auth_headers(base_url)

@pytest.fixture
def sample_calculation(base_url: str, auth_headers: dict) -> dict:
    """A multiplication calculation (3 * 4 = 12) owned by the authenticated user."""
    response = requests.post(
        f"{base_url}/calculations",
        json={"type": "multiplication", "inputs": [3, 4]},
        headers=auth_headers
    )
    assert response.status_code == 201, f"Setup calculation failed: {response.text}"
    return response.json()

# ---------------------------------------------------------------------------
# Health and Auth Endpoint Tests
# ---------------------------------------------------------------------------
def test_health_endpoint(base_url: str):
    url = f"{base_url}/health"
    response = requests.get(url)
    assert response.status_code == 200, f"Expected status code 200 but got {response.status_code}. Response: {response.text}"
    assert response.json() == {"status": "ok"}, "Unexpected response from /health."

def test_user_registration(base_url: str):
    url = f"{base_url}/auth/register"
    payload = {
        "first_name": "Alice",
        "last_name": "Smith",
        "email": "alice.smith@example.com",
        "username": "alicesmith",
        "password": "SecurePass123!",
        "confirm_password": "SecurePass123!"
    }
    response = requests.post(url, json=payload)
    assert response.status_code == 201, f"Expected 201 but got {response.status_code}. Response: {response.text}"
    data = response.json()
    for key in ["id", "username", "email", "first_name", "last_name", "is_active", "is_verified"]:
        assert key in data, f"Field '{key}' missing in registration response."
    assert data["username"] == "alicesmith"
    assert data["email"] == "alice.smith@example.com"
    assert data["first_name"] == "Alice"
    assert data["last_name"] == "Smith"
    assert data["is_active"] is True
    assert data["is_verified"] is False

def test_user_login(base_url: str):
    reg_url = f"{base_url}/auth/register"
    login_url = f"{base_url}/auth/login"
    
    test_user = {
        "first_name": "Bob",
        "last_name": "Jones",
        "email": "bob.jones@example.com",
        "username": "bobjones",
        "password": "SecurePass123!",
        "confirm_password": "SecurePass123!"
    }
    
    # Register user
    reg_response = requests.post(reg_url, json=test_user)
    assert reg_response.status_code == 201, f"User registration failed: {reg_response.text}"
    
    # Login user
    login_payload = {
        "username": test_user["username"],
        "password": test_user["password"]
    }
    login_response = requests.post(login_url, json=login_payload)
    assert login_response.status_code == 200, f"Login failed: {login_response.text}"
    
    login_data = login_response.json()
    required_fields = {
        "access_token": str,
        "refresh_token": str,
        "token_type": str,
        "expires_at": str,  # ISO datetime string
        "user_id": str,     # UUID string
        "username": str,
        "email": str,
        "first_name": str,
        "last_name": str,
        "is_active": bool,
        "is_verified": bool
    }
    
    for field, expected_type in required_fields.items():
        assert field in login_data, f"Missing field: {field}"
        assert isinstance(login_data[field], expected_type), f"Field {field} has wrong type. Expected {expected_type}, got {type(login_data[field])}"
    
    assert login_data["token_type"].lower() == "bearer", "Token type should be 'bearer'"
    assert len(login_data["access_token"]) > 0, "Access token should not be empty"
    assert len(login_data["refresh_token"]) > 0, "Refresh token should not be empty"
    assert login_data["username"] == test_user["username"]
    assert login_data["email"] == test_user["email"]
    assert login_data["first_name"] == test_user["first_name"]
    assert login_data["last_name"] == test_user["last_name"]
    assert login_data["is_active"] is True
    
    expires_at = _parse_datetime(login_data["expires_at"])
    current_time = datetime.now(timezone.utc)
    assert expires_at.tzinfo is not None, "expires_at should be timezone-aware"
    assert current_time.tzinfo is not None, "current_time should be timezone-aware"
    assert expires_at > current_time, "Token expiration should be in the future"

# ---------------------------------------------------------------------------
# Calculations Endpoints Integration Tests
# ---------------------------------------------------------------------------
# Note: All calculation creation requests now use the /calculations endpoint (not /calculations/add)
def test_create_calculation_addition(base_url: str):
    user_data = {
        "first_name": "Calc",
        "last_name": "Adder",
        "email": f"calc.adder{uuid4()}@example.com",
        "username": f"calc_adder_{uuid4()}",
        "password": "SecurePass123!",
        "confirm_password": "SecurePass123!"
    }
    token_data = register_and_login(base_url, user_data)
    access_token = token_data["access_token"]
    headers = {"Authorization": f"Bearer {access_token}"}
    url = f"{base_url}/calculations"
    payload = {
        "type": "addition",
        "inputs": [10.5, 3, 2],
        "user_id": "ignored"
    }
    response = requests.post(url, json=payload, headers=headers)
    assert response.status_code == 201, f"Addition calculation creation failed: {response.text}"
    data = response.json()
    assert "result" in data and data["result"] == 15.5, f"Expected result 15.5, got {data.get('result')}"

def test_create_calculation_subtraction(base_url: str):
    user_data = {
        "first_name": "Calc",
        "last_name": "Subtractor",
        "email": f"calc.sub{uuid4()}@example.com",
        "username": f"calc_sub_{uuid4()}",
        "password": "SecurePass123!",
        "confirm_password": "SecurePass123!"
    }
    token_data = register_and_login(base_url, user_data)
    access_token = token_data["access_token"]
    headers = {"Authorization": f"Bearer {access_token}"}
    url = f"{base_url}/calculations"
    payload = {
        "type": "subtraction",
        "inputs": [10, 3, 2],
        "user_id": "ignored"
    }
    response = requests.post(url, json=payload, headers=headers)
    assert response.status_code == 201, f"Subtraction calculation creation failed: {response.text}"
    data = response.json()
    # Expected result: 10 - 3 - 2 = 5
    assert "result" in data and data["result"] == 5, f"Expected result 5, got {data.get('result')}"

def test_create_calculation_multiplication(base_url: str):
    user_data = {
        "first_name": "Calc",
        "last_name": "Multiplier",
        "email": f"calc.mult{uuid4()}@example.com",
        "username": f"calc_mult_{uuid4()}",
        "password": "SecurePass123!",
        "confirm_password": "SecurePass123!"
    }
    token_data = register_and_login(base_url, user_data)
    access_token = token_data["access_token"]
    headers = {"Authorization": f"Bearer {access_token}"}
    url = f"{base_url}/calculations"
    payload = {
        "type": "multiplication",
        "inputs": [2, 3, 4],
        "user_id": "ignored"
    }
    response = requests.post(url, json=payload, headers=headers)
    assert response.status_code == 201, f"Multiplication calculation creation failed: {response.text}"
    data = response.json()
    # Expected result: 2 * 3 * 4 = 24
    assert "result" in data and data["result"] == 24, f"Expected result 24, got {data.get('result')}"

def test_create_calculation_division(base_url: str):
    user_data = {
        "first_name": "Calc",
        "last_name": "Divider",
        "email": f"calc.div{uuid4()}@example.com",
        "username": f"calc_div_{uuid4()}",
        "password": "SecurePass123!",
        "confirm_password": "SecurePass123!"
    }
    token_data = register_and_login(base_url, user_data)
    access_token = token_data["access_token"]
    headers = {"Authorization": f"Bearer {access_token}"}
    url = f"{base_url}/calculations"
    payload = {
        "type": "division",
        "inputs": [100, 2, 5],
        "user_id": "ignored"
    }
    response = requests.post(url, json=payload, headers=headers)
    assert response.status_code == 201, f"Division calculation creation failed: {response.text}"
    data = response.json()
    # Expected result: 100 / 2 / 5 = 10
    assert "result" in data and data["result"] == 10, f"Expected result 10, got {data.get('result')}"

def test_list_get_update_delete_calculation(base_url: str):
    user_data = {
        "first_name": "Calc",
        "last_name": "CRUD",
        "email": f"calc.crud{uuid4()}@example.com",
        "username": f"calc_crud_{uuid4()}",
        "password": "SecurePass123!",
        "confirm_password": "SecurePass123!"
    }
    token_data = register_and_login(base_url, user_data)
    access_token = token_data["access_token"]
    headers = {"Authorization": f"Bearer {access_token}"}
    
    # Create a calculation (e.g., multiplication)
    create_url = f"{base_url}/calculations"
    payload = {
        "type": "multiplication",
        "inputs": [3, 4],
        "user_id": "ignored"
    }
    create_response = requests.post(create_url, json=payload, headers=headers)
    assert create_response.status_code == 201, f"Calculation creation failed: {create_response.text}"
    calc = create_response.json()
    calc_id = calc["id"]
    
    # List calculations
    list_url = f"{base_url}/calculations"
    list_response = requests.get(list_url, headers=headers)
    assert list_response.status_code == 200, f"List calculations failed: {list_response.text}"
    calc_list = list_response.json()
    assert any(c["id"] == calc_id for c in calc_list), "Created calculation not found in list"
    
    # Get calculation by ID
    get_url = f"{base_url}/calculations/{calc_id}"
    get_response = requests.get(get_url, headers=headers)
    assert get_response.status_code == 200, f"Get calculation failed: {get_response.text}"
    get_calc = get_response.json()
    assert get_calc["id"] == calc_id, "Mismatch in calculation id"
    
    # Update calculation: change inputs (e.g., from [3,4] to [5,6])
    update_url = f"{base_url}/calculations/{calc_id}"
    update_payload = {"inputs": [5, 6]}
    update_response = requests.put(update_url, json=update_payload, headers=headers)
    assert update_response.status_code == 200, f"Update calculation failed: {update_response.text}"
    updated_calc = update_response.json()
    # For multiplication, expected result = 5 * 6 = 30
    expected_result = 30
    assert updated_calc["result"] == expected_result, f"Expected updated result {expected_result}, got {updated_calc['result']}"
    
    # Delete calculation
    delete_url = f"{base_url}/calculations/{calc_id}"
    delete_response = requests.delete(delete_url, headers=headers)
    assert delete_response.status_code == 204, f"Delete calculation failed: {delete_response.text}"
    
    # Verify deletion: GET should return 404
    get_response_after_delete = requests.get(get_url, headers=headers)
    assert get_response_after_delete.status_code == 404, "Expected 404 after deletion"

def test_update_persists_to_database(
    base_url: str, auth_headers: dict, sample_calculation: dict
):
    """An edit is persisted, not just echoed back in the response."""
    url = f"{base_url}/calculations/{sample_calculation['id']}"
    update_response = requests.put(url, json={"inputs": [8, 9]}, headers=auth_headers)
    assert update_response.status_code == 200, f"Update failed: {update_response.text}"
    assert update_response.json()["result"] == 72

    refetched = requests.get(url, headers=auth_headers).json()
    assert refetched["inputs"] == [8, 9], "Updated inputs were not persisted"
    assert refetched["result"] == 72, "Updated result was not persisted"

def test_delete_only_removes_the_target_calculation(base_url: str, auth_headers: dict):
    """Delete removes exactly one calculation and leaves the others intact."""
    created = []
    for calc_type, inputs in [
        ("addition", [1, 2]),
        ("multiplication", [3, 4]),
        ("subtraction", [10, 4]),
    ]:
        response = requests.post(
            f"{base_url}/calculations",
            json={"type": calc_type, "inputs": inputs},
            headers=auth_headers
        )
        assert response.status_code == 201, f"Setup failed: {response.text}"
        created.append(response.json())

    target = created[1]
    delete_response = requests.delete(
        f"{base_url}/calculations/{target['id']}", headers=auth_headers
    )
    assert delete_response.status_code == 204

    remaining = requests.get(f"{base_url}/calculations", headers=auth_headers).json()
    assert len(remaining) == 2, f"Expected 2 calculations left, got {len(remaining)}"

    by_id = {c["id"]: c for c in remaining}
    assert target["id"] not in by_id, "Deleted calculation is still present"
    assert by_id[created[0]["id"]]["result"] == 3, "Untouched calculation was modified"
    assert by_id[created[2]["id"]]["result"] == 6, "Untouched calculation was modified"

def test_patch_calculation(base_url: str, auth_headers: dict, sample_calculation: dict):
    """PATCH applies a partial update and recomputes the result."""
    url = f"{base_url}/calculations/{sample_calculation['id']}"
    response = requests.patch(url, json={"inputs": [6, 7]}, headers=auth_headers)
    assert response.status_code == 200, f"PATCH failed: {response.text}"
    assert response.json()["result"] == 42

def test_patch_calculation_without_inputs_is_noop(
    base_url: str, auth_headers: dict, sample_calculation: dict
):
    """PATCH with an empty body leaves the calculation unchanged."""
    url = f"{base_url}/calculations/{sample_calculation['id']}"
    response = requests.patch(url, json={}, headers=auth_headers)
    assert response.status_code == 200, f"PATCH failed: {response.text}"
    assert response.json()["result"] == sample_calculation["result"]

# ---------------------------------------------------------------------------
# Negative Scenarios: Unauthorized Access
# ---------------------------------------------------------------------------
def test_calculation_endpoints_require_authentication(base_url: str):
    """Every calculations endpoint rejects an unauthenticated request."""
    calc_id = uuid4()
    unauthenticated_requests = [
        ("browse", requests.get, f"{base_url}/calculations", None),
        ("add", requests.post, f"{base_url}/calculations", {"type": "addition", "inputs": [1, 2]}),
        ("read", requests.get, f"{base_url}/calculations/{calc_id}", None),
        ("edit", requests.put, f"{base_url}/calculations/{calc_id}", {"inputs": [1, 2]}),
        ("patch", requests.patch, f"{base_url}/calculations/{calc_id}", {"inputs": [1, 2]}),
        ("delete", requests.delete, f"{base_url}/calculations/{calc_id}", None),
    ]
    for name, method, url, payload in unauthenticated_requests:
        response = method(url, json=payload) if payload else method(url)
        assert response.status_code == 401, (
            f"{name} should require authentication, got {response.status_code}"
        )

def test_calculation_endpoints_reject_invalid_token(base_url: str):
    """A malformed bearer token is rejected."""
    headers = {"Authorization": "Bearer not-a-real-token"}
    response = requests.get(f"{base_url}/calculations", headers=headers)
    assert response.status_code == 401, f"Expected 401, got {response.status_code}"

def test_cannot_access_another_users_calculation(base_url: str, sample_calculation: dict):
    """A calculation owned by one user is invisible to another user."""
    other_headers = make_auth_headers(base_url)
    url = f"{base_url}/calculations/{sample_calculation['id']}"

    assert requests.get(url, headers=other_headers).status_code == 404
    assert requests.put(url, json={"inputs": [1, 2]}, headers=other_headers).status_code == 404
    assert requests.patch(url, json={"inputs": [1, 2]}, headers=other_headers).status_code == 404
    assert requests.delete(url, headers=other_headers).status_code == 404

def test_browse_only_returns_own_calculations(base_url: str, sample_calculation: dict):
    """Browse is scoped to the authenticated user."""
    other_headers = make_auth_headers(base_url)
    response = requests.get(f"{base_url}/calculations", headers=other_headers)
    assert response.status_code == 200
    assert response.json() == [], "A new user should not see another user's calculations"

# ---------------------------------------------------------------------------
# Negative Scenarios: Invalid Input and Error Responses
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("payload, description", [
    ({"type": "modulo", "inputs": [1, 2]}, "unsupported operation type"),
    ({"type": "addition", "inputs": [5]}, "fewer than two inputs"),
    ({"type": "addition", "inputs": []}, "no inputs"),
    ({"type": "addition", "inputs": "not-a-list"}, "inputs not a list"),
    ({"type": "addition", "inputs": ["a", "b"]}, "non-numeric inputs"),
    ({"type": "division", "inputs": [10, 0]}, "division by zero"),
    ({"inputs": [1, 2]}, "missing type"),
    ({"type": "addition"}, "missing inputs"),
])
def test_create_calculation_rejects_invalid_payload(
    base_url: str, auth_headers: dict, payload: dict, description: str
):
    """Invalid create payloads are rejected with a validation error."""
    response = requests.post(f"{base_url}/calculations", json=payload, headers=auth_headers)
    assert response.status_code == 422, (
        f"Expected 422 for {description}, got {response.status_code}: {response.text}"
    )

def test_read_invalid_uuid_returns_400(base_url: str, auth_headers: dict):
    """A malformed calculation id is a client error, not a server error."""
    response = requests.get(f"{base_url}/calculations/not-a-uuid", headers=auth_headers)
    assert response.status_code == 400, f"Expected 400, got {response.status_code}"
    assert "Invalid calculation id format" in response.json()["detail"]

def test_delete_invalid_uuid_returns_400(base_url: str, auth_headers: dict):
    """Deleting with a malformed id returns 400."""
    response = requests.delete(f"{base_url}/calculations/not-a-uuid", headers=auth_headers)
    assert response.status_code == 400, f"Expected 400, got {response.status_code}"

def test_missing_calculation_returns_404(base_url: str, auth_headers: dict):
    """Operating on a non-existent calculation returns 404."""
    url = f"{base_url}/calculations/{uuid4()}"
    assert requests.get(url, headers=auth_headers).status_code == 404
    assert requests.put(url, json={"inputs": [1, 2]}, headers=auth_headers).status_code == 404
    assert requests.patch(url, json={"inputs": [1, 2]}, headers=auth_headers).status_code == 404
    assert requests.delete(url, headers=auth_headers).status_code == 404

def test_update_rejects_single_input(base_url: str, auth_headers: dict, sample_calculation: dict):
    """An update with fewer than two inputs is rejected."""
    url = f"{base_url}/calculations/{sample_calculation['id']}"
    response = requests.put(url, json={"inputs": [5]}, headers=auth_headers)
    assert response.status_code == 422, f"Expected 422, got {response.status_code}"

def test_update_division_by_zero_returns_400(base_url: str, auth_headers: dict):
    """
    Updating a division calculation so that it divides by zero is a client error.

    The recomputation happens in the model rather than in schema validation, so
    the endpoint has to translate that failure into a 400 instead of a 500.
    """
    create_response = requests.post(
        f"{base_url}/calculations",
        json={"type": "division", "inputs": [100, 2]},
        headers=auth_headers
    )
    assert create_response.status_code == 201
    calc_id = create_response.json()["id"]
    url = f"{base_url}/calculations/{calc_id}"

    for method in (requests.put, requests.patch):
        response = method(url, json={"inputs": [10, 0]}, headers=auth_headers)
        assert response.status_code == 400, (
            f"Expected 400 from {method.__name__.upper()}, got {response.status_code}: {response.text}"
        )
        assert "divide by zero" in response.json()["detail"].lower()

    # The stored calculation is untouched by the rejected updates.
    unchanged = requests.get(url, headers=auth_headers).json()
    assert unchanged["result"] == 50
    assert unchanged["inputs"] == [100, 2]

# ---------------------------------------------------------------------------
# Direct Model Tests for Calculation Operations
# ---------------------------------------------------------------------------
def test_model_addition():
    dummy_user_id = uuid4()
    calc = Calculation.create("addition", dummy_user_id, [1, 2, 3])
    result = calc.get_result()
    assert result == 6, f"Addition result incorrect: expected 6, got {result}"

def test_model_subtraction():
    dummy_user_id = uuid4()
    calc = Calculation.create("subtraction", dummy_user_id, [10, 3, 2])
    result = calc.get_result()
    assert result == 5, f"Subtraction result incorrect: expected 5, got {result}"

def test_model_multiplication():
    dummy_user_id = uuid4()
    calc = Calculation.create("multiplication", dummy_user_id, [2, 3, 4])
    result = calc.get_result()
    assert result == 24, f"Multiplication result incorrect: expected 24, got {result}"

def test_model_division():
    dummy_user_id = uuid4()
    calc = Calculation.create("division", dummy_user_id, [100, 2, 5])
    result = calc.get_result()
    assert result == 10, f"Division result incorrect: expected 10, got {result}"
    
    # Test division by zero error
    with pytest.raises(ValueError):
        calc_zero = Calculation.create("division", dummy_user_id, [100, 0])
        calc_zero.get_result()
