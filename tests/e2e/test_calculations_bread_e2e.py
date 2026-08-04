"""
Playwright end-to-end tests for the calculations BREAD user interface.

These tests drive a real browser against the running FastAPI server and cover the
full Browse / Read / Edit / Add / Delete flow through the HTML pages, plus the
negative paths: invalid input, client-side validation, unauthorized access and
server-side error responses.

The API-level contract for the same endpoints is covered in
tests/e2e/test_fastapi_calculator.py; here the assertions are about what a user
actually sees in the browser.
"""

from uuid import uuid4

import pytest
import requests
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e

# Playwright's default assertion timeout is 5s; the UI redirects after a ~1s
# delay on several actions, so give the slower navigations some headroom.
NAV_TIMEOUT = 15_000

PASSWORD = "SecurePass123!"


# ---------------------------------------------------------------------------
# Helpers and fixtures
# ---------------------------------------------------------------------------
def _make_user_payload() -> dict:
    """Build a registration payload with a unique username/email."""
    suffix = uuid4().hex[:12]
    return {
        "first_name": "Bread",
        "last_name": "Tester",
        "email": f"bread.{suffix}@example.com",
        "username": f"bread_{suffix}",
        "password": PASSWORD,
        "confirm_password": PASSWORD,
    }


def _register_user(base_url: str) -> dict:
    """
    Register a user through the API.

    The registration form itself is exercised by test_register_and_login_via_ui;
    every other test only needs an account to exist, so creating it over HTTP
    keeps those tests focused on the behaviour under test.
    """
    payload = _make_user_payload()
    response = requests.post(f"{base_url}/auth/register", json=payload)
    assert response.status_code == 201, f"Registration failed: {response.text}"
    return payload


def _api_login(base_url: str, user: dict) -> str:
    """Log in over the API and return the access token."""
    response = requests.post(
        f"{base_url}/auth/login",
        json={"username": user["username"], "password": user["password"]},
    )
    assert response.status_code == 200, f"Login failed: {response.text}"
    return response.json()["access_token"]


def _create_calculation(base_url: str, token: str, calc_type: str, inputs: list) -> dict:
    """Seed a calculation over the API and return the created record."""
    response = requests.post(
        f"{base_url}/calculations",
        json={"type": calc_type, "inputs": inputs},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201, f"Calculation creation failed: {response.text}"
    return response.json()


def _ui_login(page: Page, base_url: str, user: dict) -> None:
    """Log in through the login form and wait for the dashboard to load."""
    page.goto(f"{base_url}/login")
    page.fill("#username", user["username"])
    page.fill("#password", user["password"])
    page.click("#loginForm button[type='submit']")
    page.wait_for_url("**/dashboard", timeout=NAV_TIMEOUT)
    expect(page.locator("#calculationForm")).to_be_visible()


def _add_calculation_via_ui(page: Page, calc_type: str, inputs: str) -> None:
    """Fill in and submit the dashboard's new-calculation form."""
    page.select_option("#calcType", calc_type)
    page.fill("#calcInputs", inputs)
    page.click("#calculationForm button[type='submit']")


@pytest.fixture
def user(base_url: str) -> dict:
    """A freshly registered user."""
    return _register_user(base_url)


@pytest.fixture
def token(base_url: str, user: dict) -> str:
    """An access token for the registered user."""
    return _api_login(base_url, user)


@pytest.fixture
def logged_in_page(page: Page, base_url: str, user: dict) -> Page:
    """A browser page that has logged in through the UI and is on the dashboard."""
    _ui_login(page, base_url, user)
    return page


@pytest.fixture(autouse=True)
def accept_dialogs(page: Page):
    """
    Auto-accept the confirm() dialogs used by the delete and logout buttons.

    Playwright dismisses dialogs by default, which would cancel every delete.
    """
    page.on("dialog", lambda dialog: dialog.accept())


# ---------------------------------------------------------------------------
# Positive scenarios
# ---------------------------------------------------------------------------
def test_register_and_login_via_ui(page: Page, base_url: str):
    """A new user can register and then log in through the web forms."""
    new_user = _make_user_payload()

    page.goto(f"{base_url}/register")
    page.fill("#username", new_user["username"])
    page.fill("#email", new_user["email"])
    page.fill("#first_name", new_user["first_name"])
    page.fill("#last_name", new_user["last_name"])
    page.fill("#password", new_user["password"])
    page.fill("#confirm_password", new_user["confirm_password"])
    page.click("#registrationForm button[type='submit']")

    expect(page.locator("#successAlert")).to_be_visible(timeout=NAV_TIMEOUT)

    # The register page redirects to /login on its own; follow it rather than
    # navigating manually, so the two navigations cannot race.
    page.wait_for_url("**/login", timeout=NAV_TIMEOUT)
    page.fill("#username", new_user["username"])
    page.fill("#password", new_user["password"])
    page.click("#loginForm button[type='submit']")

    page.wait_for_url("**/dashboard", timeout=NAV_TIMEOUT)
    expect(page.locator("#layoutUserWelcome")).to_contain_text(new_user["username"])


def test_add_calculation_shows_result(logged_in_page: Page):
    """Add: submitting the form creates a calculation and reports the result."""
    page = logged_in_page
    _add_calculation_via_ui(page, "addition", "10.5, 3, 2")

    expect(page.locator("#successAlert")).to_be_visible(timeout=NAV_TIMEOUT)
    expect(page.locator("#successMessage")).to_contain_text("15.5")

    # The new calculation is rendered into the history table.
    row = page.locator("#calculationsTable tr").first
    expect(row).to_contain_text("addition")
    expect(row).to_contain_text("15.5")


@pytest.mark.parametrize(
    "calc_type, inputs, expected",
    [
        ("addition", "1, 2, 3", "6"),
        ("subtraction", "10, 3, 2", "5"),
        ("multiplication", "2, 3, 4", "24"),
        ("division", "100, 2, 5", "10"),
    ],
)
def test_add_each_operation_type(logged_in_page: Page, calc_type, inputs, expected):
    """Add: every supported operation type computes the expected result."""
    page = logged_in_page
    _add_calculation_via_ui(page, calc_type, inputs)

    expect(page.locator("#successMessage")).to_contain_text(expected, timeout=NAV_TIMEOUT)
    expect(page.locator("#calculationsTable tr").first).to_contain_text(calc_type)


def test_browse_lists_only_current_users_calculations(
    page: Page, base_url: str, user: dict, token: str
):
    """Browse: the dashboard lists the user's calculations and nobody else's."""
    _create_calculation(base_url, token, "addition", [1, 2])
    _create_calculation(base_url, token, "multiplication", [3, 4])

    # A second user's calculation must not leak into this user's dashboard.
    other_user = _register_user(base_url)
    other_token = _api_login(base_url, other_user)
    _create_calculation(base_url, other_token, "subtraction", [99, 1])

    _ui_login(page, base_url, user)

    rows = page.locator("#calculationsTable tr")
    expect(rows).to_have_count(2, timeout=NAV_TIMEOUT)
    table = page.locator("#calculationsTable")
    expect(table).to_contain_text("addition")
    expect(table).to_contain_text("multiplication")
    expect(table).not_to_contain_text("subtraction")


def test_browse_shows_empty_state(logged_in_page: Page):
    """Browse: a user with no calculations sees the empty state."""
    expect(logged_in_page.locator("#calculationsTable")).to_contain_text(
        "No calculations found", timeout=NAV_TIMEOUT
    )


def test_read_calculation_detail_page(page: Page, base_url: str, user: dict, token: str):
    """Read: the detail page shows the calculation's type, inputs and result."""
    calc = _create_calculation(base_url, token, "division", [100, 2, 5])
    _ui_login(page, base_url, user)

    page.goto(f"{base_url}/dashboard/view/{calc['id']}")

    expect(page.locator("#calculationCard")).to_be_visible(timeout=NAV_TIMEOUT)
    details = page.locator("#calcDetails")
    expect(details).to_contain_text("division")
    expect(details).to_contain_text("10")
    expect(details).to_contain_text(calc["id"])
    expect(page.locator("#calculationVisual")).to_contain_text("÷")


def test_read_navigates_from_dashboard_view_link(
    page: Page, base_url: str, user: dict, token: str
):
    """Read: the dashboard's View link opens the matching detail page."""
    calc = _create_calculation(base_url, token, "addition", [7, 8])
    _ui_login(page, base_url, user)

    page.locator("#calculationsTable a", has_text="View").first.click()

    page.wait_for_url(f"**/dashboard/view/{calc['id']}", timeout=NAV_TIMEOUT)
    expect(page.locator("#calcDetails")).to_contain_text("15")


def test_edit_calculation_updates_result(page: Page, base_url: str, user: dict, token: str):
    """Edit: saving new inputs recomputes the result and redirects to the detail page."""
    calc = _create_calculation(base_url, token, "multiplication", [3, 4])
    _ui_login(page, base_url, user)

    page.goto(f"{base_url}/dashboard/edit/{calc['id']}")
    expect(page.locator("#editCard")).to_be_visible(timeout=NAV_TIMEOUT)

    # The form is pre-filled with the existing values, and type is read-only.
    expect(page.locator("#calcType")).to_have_value("multiplication")
    expect(page.locator("#calcInputs")).to_have_value("3, 4")
    expect(page.locator("#calcType")).to_have_attribute("readonly", "")

    page.fill("#calcInputs", "5, 6")
    expect(page.locator("#previewResult")).to_contain_text("30")

    page.click("#editCalculationForm button[type='submit']")

    page.wait_for_url(f"**/dashboard/view/{calc['id']}", timeout=NAV_TIMEOUT)
    expect(page.locator("#calcDetails")).to_contain_text("30", timeout=NAV_TIMEOUT)


def test_delete_calculation_from_dashboard(
    page: Page, base_url: str, user: dict, token: str
):
    """Delete: removing a calculation from the dashboard clears it from the table."""
    _create_calculation(base_url, token, "addition", [1, 2])
    _ui_login(page, base_url, user)

    expect(page.locator("#calculationsTable tr")).to_have_count(1, timeout=NAV_TIMEOUT)
    page.locator(".delete-calc").first.click()

    expect(page.locator("#calculationsTable")).to_contain_text(
        "No calculations found", timeout=NAV_TIMEOUT
    )


def test_delete_calculation_from_detail_page(
    page: Page, base_url: str, user: dict, token: str
):
    """Delete: the detail page's Delete button removes the record and returns home."""
    calc = _create_calculation(base_url, token, "addition", [4, 5])
    _ui_login(page, base_url, user)

    page.goto(f"{base_url}/dashboard/view/{calc['id']}")
    expect(page.locator("#calculationCard")).to_be_visible(timeout=NAV_TIMEOUT)
    page.click("#deleteBtn")

    page.wait_for_url("**/dashboard", timeout=NAV_TIMEOUT)
    expect(page.locator("#calculationsTable")).to_contain_text(
        "No calculations found", timeout=NAV_TIMEOUT
    )

    # And it is really gone from the API, not just the page.
    response = requests.get(
        f"{base_url}/calculations/{calc['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Negative scenarios: client-side validation
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "inputs, expected_message",
    [
        ("5", "at least two"),
        ("", "at least two"),
        ("abc, def", "numbers only"),
        ("5, abc", "numbers only"),
    ],
)
def test_add_rejects_invalid_input(logged_in_page: Page, inputs, expected_message):
    """Add: invalid input is caught in the browser and never reaches the API."""
    page = logged_in_page
    _add_calculation_via_ui(page, "addition", inputs)

    expect(page.locator("#errorAlert")).to_be_visible(timeout=NAV_TIMEOUT)
    expect(page.locator("#errorMessage")).to_contain_text(expected_message)

    # Nothing was created.
    expect(page.locator("#calculationsTable")).to_contain_text("No calculations found")


def test_add_rejects_division_by_zero(logged_in_page: Page):
    """Add: dividing by zero is blocked with a readable message."""
    page = logged_in_page
    _add_calculation_via_ui(page, "division", "10, 0")

    expect(page.locator("#errorAlert")).to_be_visible(timeout=NAV_TIMEOUT)
    expect(page.locator("#errorMessage")).to_contain_text("Cannot divide by zero")
    expect(page.locator("#errorMessage")).not_to_contain_text("[object Object]")
    expect(page.locator("#calculationsTable")).to_contain_text("No calculations found")


@pytest.mark.parametrize(
    "inputs, expected_message",
    [
        ("7", "at least two"),
        ("7, xyz", "numbers only"),
    ],
)
def test_edit_rejects_invalid_input(
    page: Page, base_url: str, user: dict, token: str, inputs, expected_message
):
    """Edit: invalid input is rejected and the stored calculation is untouched."""
    calc = _create_calculation(base_url, token, "addition", [1, 2])
    _ui_login(page, base_url, user)

    page.goto(f"{base_url}/dashboard/edit/{calc['id']}")
    expect(page.locator("#editCard")).to_be_visible(timeout=NAV_TIMEOUT)

    page.fill("#calcInputs", inputs)
    page.click("#editCalculationForm button[type='submit']")

    expect(page.locator("#errorAlert")).to_be_visible(timeout=NAV_TIMEOUT)
    expect(page.locator("#errorMessage")).to_contain_text(expected_message)

    # The stored record still has its original result.
    response = requests.get(
        f"{base_url}/calculations/{calc['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.json()["result"] == 3


def test_edit_rejects_division_by_zero(page: Page, base_url: str, user: dict, token: str):
    """Edit: a divide-by-zero update is blocked before it is sent."""
    calc = _create_calculation(base_url, token, "division", [100, 2])
    _ui_login(page, base_url, user)

    page.goto(f"{base_url}/dashboard/edit/{calc['id']}")
    expect(page.locator("#editCard")).to_be_visible(timeout=NAV_TIMEOUT)

    page.fill("#calcInputs", "100, 0")
    expect(page.locator("#previewResult")).to_contain_text("Cannot divide by zero")

    page.click("#editCalculationForm button[type='submit']")
    expect(page.locator("#errorMessage")).to_contain_text(
        "Cannot divide by zero", timeout=NAV_TIMEOUT
    )

    response = requests.get(
        f"{base_url}/calculations/{calc['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.json()["result"] == 50


# ---------------------------------------------------------------------------
# Negative scenarios: unauthorized access and error responses
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "path",
    [
        "/dashboard",
        "/dashboard/view/123e4567-e89b-12d3-a456-426614174000",
        "/dashboard/edit/123e4567-e89b-12d3-a456-426614174000",
    ],
)
def test_unauthenticated_pages_redirect_to_login(page: Page, base_url: str, path):
    """Unauthorized: protected pages bounce an anonymous visitor to the login page."""
    page.goto(f"{base_url}{path}")
    page.wait_for_url("**/login", timeout=NAV_TIMEOUT)
    expect(page.locator("#loginForm")).to_be_visible()


def test_expired_token_redirects_to_login(page: Page, base_url: str, user: dict):
    """Unauthorized: a rejected token clears the session and returns to login."""
    _ui_login(page, base_url, user)

    # Replace the good token with a bogus one; the next API call gets a 401.
    page.evaluate("localStorage.setItem('access_token', 'not-a-real-token')")
    page.goto(f"{base_url}/dashboard")

    page.wait_for_url("**/login", timeout=NAV_TIMEOUT)
    assert page.evaluate("localStorage.getItem('access_token')") is None


def test_view_missing_calculation_shows_not_found(page: Page, base_url: str, user: dict):
    """Error response: a 404 from the API renders the not-found card."""
    _ui_login(page, base_url, user)

    page.goto(f"{base_url}/dashboard/view/{uuid4()}")

    expect(page.locator("#errorState")).to_be_visible(timeout=NAV_TIMEOUT)
    expect(page.locator("#errorState")).to_contain_text("Calculation Not Found")
    expect(page.locator("#calculationCard")).to_be_hidden()


def test_edit_missing_calculation_shows_not_found(page: Page, base_url: str, user: dict):
    """Error response: editing a non-existent calculation shows the not-found card."""
    _ui_login(page, base_url, user)

    page.goto(f"{base_url}/dashboard/edit/{uuid4()}")

    expect(page.locator("#errorState")).to_be_visible(timeout=NAV_TIMEOUT)
    expect(page.locator("#editCard")).to_be_hidden()


def test_cannot_view_another_users_calculation(page: Page, base_url: str, user: dict):
    """Unauthorized: one user cannot open another user's calculation."""
    other_user = _register_user(base_url)
    other_token = _api_login(base_url, other_user)
    foreign_calc = _create_calculation(base_url, other_token, "addition", [1, 2])

    _ui_login(page, base_url, user)
    page.goto(f"{base_url}/dashboard/view/{foreign_calc['id']}")

    expect(page.locator("#errorState")).to_be_visible(timeout=NAV_TIMEOUT)
    expect(page.locator("#calculationCard")).to_be_hidden()


def test_login_with_wrong_password_shows_error(page: Page, base_url: str, user: dict):
    """Unauthorized: bad credentials surface an error and stay on the login page."""
    page.goto(f"{base_url}/login")
    page.fill("#username", user["username"])
    page.fill("#password", "WrongPassword123!")
    page.click("#loginForm button[type='submit']")

    expect(page.locator("#errorAlert")).to_be_visible(timeout=NAV_TIMEOUT)
    expect(page.locator("#errorMessage")).to_contain_text("Invalid username or password")
    assert "/login" in page.url


def test_logout_clears_session(logged_in_page: Page, base_url: str):
    """Logging out clears stored credentials and protected pages are locked again."""
    page = logged_in_page
    page.click("#layoutLogoutBtn")

    page.wait_for_url("**/login", timeout=NAV_TIMEOUT)
    assert page.evaluate("localStorage.getItem('access_token')") is None

    page.goto(f"{base_url}/dashboard")
    page.wait_for_url("**/login", timeout=NAV_TIMEOUT)
