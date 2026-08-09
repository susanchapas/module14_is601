"""
Playwright end-to-end tests for the profile page.

The headline test walks the whole journey a user takes: log in, open the profile
page, change the username and email, change the password, and log back in with
the new credentials. The rest cover the error paths a user can actually hit.
"""

from uuid import uuid4

import pytest
import requests
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e

NAV_TIMEOUT = 15_000

PASSWORD = "SecurePass123!"
NEW_PASSWORD = "FreshPass456!"


# ---------------------------------------------------------------------------
# Helpers and fixtures
# ---------------------------------------------------------------------------
def _make_user_payload() -> dict:
    """Build a registration payload with a unique username/email."""
    suffix = uuid4().hex[:12]
    return {
        "first_name": "Profile",
        "last_name": "Tester",
        "email": f"profile.{suffix}@example.com",
        "username": f"profile_{suffix}",
        "password": PASSWORD,
        "confirm_password": PASSWORD,
    }


def _register_user(base_url: str) -> dict:
    """Register a user over the API; the register form is covered elsewhere."""
    payload = _make_user_payload()
    response = requests.post(f"{base_url}/auth/register", json=payload)
    assert response.status_code == 201, f"Registration failed: {response.text}"
    return payload


def _ui_login(page: Page, base_url: str, username: str, password: str) -> None:
    """Log in through the login form and wait for the dashboard to load."""
    page.goto(f"{base_url}/login")
    page.fill("#username", username)
    page.fill("#password", password)
    page.click("#loginForm button[type='submit']")
    page.wait_for_url("**/dashboard", timeout=NAV_TIMEOUT)
    expect(page.locator("#calculationForm")).to_be_visible()


def _open_profile(page: Page, base_url: str) -> None:
    """Navigate to the profile page and wait for it to load the user's data."""
    page.goto(f"{base_url}/profile")
    expect(page.locator("#profileCard")).to_be_visible(timeout=NAV_TIMEOUT)


def _change_password(page: Page, current: str, new: str, confirm: str | None = None) -> None:
    """Fill in and submit the change-password form."""
    page.fill("#current_password", current)
    page.fill("#new_password", new)
    page.fill("#confirm_new_password", confirm if confirm is not None else new)
    page.click("#passwordForm button[type='submit']")


@pytest.fixture
def user(base_url: str) -> dict:
    """A freshly registered user."""
    return _register_user(base_url)


@pytest.fixture
def logged_in_page(page: Page, base_url: str, user: dict) -> Page:
    """A browser page logged in through the UI and sitting on the dashboard."""
    _ui_login(page, base_url, user["username"], user["password"])
    return page


@pytest.fixture(autouse=True)
def accept_dialogs(page: Page):
    """Auto-accept the confirm() dialog used by the logout button."""
    page.on("dialog", lambda dialog: dialog.accept())


# ---------------------------------------------------------------------------
# The full journey
# ---------------------------------------------------------------------------
def test_login_profile_password_change_then_relogin(page: Page, base_url: str, user: dict):
    """
    Full flow: login -> profile -> edit details -> change password -> re-login.

    This is the scenario the feature exists for, so it is asserted end to end
    rather than split across smaller tests.
    """
    _ui_login(page, base_url, user["username"], user["password"])

    # Reach the profile page the way a user does, through the header link.
    page.click("#layoutProfileLink")
    page.wait_for_url("**/profile", timeout=NAV_TIMEOUT)
    expect(page.locator("#profileCard")).to_be_visible(timeout=NAV_TIMEOUT)

    # The form arrives pre-filled with the stored account details.
    expect(page.locator("#username")).to_have_value(user["username"])
    expect(page.locator("#email")).to_have_value(user["email"])

    # 1) Update the username and email.
    new_username = f"{user['username']}_v2"
    new_email = f"v2.{user['email']}"
    page.fill("#username", new_username)
    page.fill("#email", new_email)
    page.click("#profileForm button[type='submit']")

    expect(page.locator("#successAlert")).to_be_visible(timeout=NAV_TIMEOUT)
    expect(page.locator("#successMessage")).to_contain_text("Profile updated")
    expect(page.locator("#layoutUserWelcome")).to_contain_text(new_username)

    # 2) Change the password; the page logs the user out afterwards.
    _change_password(page, PASSWORD, NEW_PASSWORD)
    expect(page.locator("#successMessage")).to_contain_text(
        "Password updated", timeout=NAV_TIMEOUT
    )

    page.wait_for_url("**/login", timeout=NAV_TIMEOUT)
    assert page.evaluate("localStorage.getItem('access_token')") is None

    # 3) The old password no longer works.
    page.fill("#username", new_username)
    page.fill("#password", PASSWORD)
    page.click("#loginForm button[type='submit']")
    expect(page.locator("#errorMessage")).to_contain_text(
        "Invalid username or password", timeout=NAV_TIMEOUT
    )

    # 4) The new username and new password do.
    _ui_login(page, base_url, new_username, NEW_PASSWORD)
    expect(page.locator("#layoutUserWelcome")).to_contain_text(new_username)

    # 5) And the edits really persisted, not just in the browser.
    _open_profile(page, base_url)
    expect(page.locator("#username")).to_have_value(new_username)
    expect(page.locator("#email")).to_have_value(new_email)


def test_login_with_new_email_after_change(page: Page, base_url: str, user: dict):
    """The updated email works as a login identifier."""
    _ui_login(page, base_url, user["username"], user["password"])
    _open_profile(page, base_url)

    new_email = f"renamed.{user['email']}"
    page.fill("#email", new_email)
    page.click("#profileForm button[type='submit']")
    expect(page.locator("#successAlert")).to_be_visible(timeout=NAV_TIMEOUT)

    page.click("#layoutLogoutBtn")
    page.wait_for_url("**/login", timeout=NAV_TIMEOUT)

    _ui_login(page, base_url, new_email, PASSWORD)
    expect(page.locator("#layoutUserWelcome")).to_contain_text(user["username"])


def test_profile_page_shows_stored_details(logged_in_page: Page, base_url: str, user: dict):
    """The profile form loads every stored field from the API."""
    page = logged_in_page
    _open_profile(page, base_url)

    expect(page.locator("#username")).to_have_value(user["username"])
    expect(page.locator("#email")).to_have_value(user["email"])
    expect(page.locator("#first_name")).to_have_value(user["first_name"])
    expect(page.locator("#last_name")).to_have_value(user["last_name"])


def test_update_names_only(logged_in_page: Page, base_url: str, user: dict):
    """Changing only the names leaves the login identifiers alone."""
    page = logged_in_page
    _open_profile(page, base_url)

    page.fill("#first_name", "Grace")
    page.fill("#last_name", "Hopper")
    page.click("#profileForm button[type='submit']")

    expect(page.locator("#successAlert")).to_be_visible(timeout=NAV_TIMEOUT)

    page.reload()
    expect(page.locator("#first_name")).to_have_value("Grace", timeout=NAV_TIMEOUT)
    expect(page.locator("#last_name")).to_have_value("Hopper")
    expect(page.locator("#username")).to_have_value(user["username"])


# ---------------------------------------------------------------------------
# Negative scenarios
# ---------------------------------------------------------------------------
def test_profile_requires_authentication(page: Page, base_url: str):
    """An anonymous visitor is bounced to the login page."""
    page.goto(f"{base_url}/profile")
    page.wait_for_url("**/login", timeout=NAV_TIMEOUT)
    expect(page.locator("#loginForm")).to_be_visible()


def test_update_rejects_a_username_taken_by_another_user(
    page: Page, base_url: str, user: dict
):
    """A duplicate username is reported and nothing is saved."""
    other = _register_user(base_url)

    _ui_login(page, base_url, user["username"], user["password"])
    _open_profile(page, base_url)

    page.fill("#username", other["username"])
    page.click("#profileForm button[type='submit']")

    expect(page.locator("#errorAlert")).to_be_visible(timeout=NAV_TIMEOUT)
    expect(page.locator("#errorMessage")).to_contain_text("already exists")

    page.reload()
    expect(page.locator("#username")).to_have_value(user["username"], timeout=NAV_TIMEOUT)


def test_update_rejects_a_malformed_email(logged_in_page: Page, base_url: str, user: dict):
    """A bad email address is refused by the API and reported readably."""
    page = logged_in_page
    _open_profile(page, base_url)

    # type="email" would block submission, so bypass the browser's own check.
    page.eval_on_selector("#email", "el => el.type = 'text'")
    page.fill("#email", "not-an-email")
    page.click("#profileForm button[type='submit']")

    expect(page.locator("#errorAlert")).to_be_visible(timeout=NAV_TIMEOUT)
    expect(page.locator("#errorMessage")).not_to_contain_text("[object Object]")

    page.reload()
    expect(page.locator("#email")).to_have_value(user["email"], timeout=NAV_TIMEOUT)


def test_password_change_rejects_wrong_current_password(
    page: Page, base_url: str, user: dict
):
    """The wrong current password is refused and the old one still works."""
    _ui_login(page, base_url, user["username"], user["password"])
    _open_profile(page, base_url)

    _change_password(page, "WrongPass123!", NEW_PASSWORD)

    expect(page.locator("#errorAlert")).to_be_visible(timeout=NAV_TIMEOUT)
    expect(page.locator("#errorMessage")).to_contain_text("Current password is incorrect")

    # Still logged in, and the original password is unchanged.
    assert "/profile" in page.url
    page.click("#layoutLogoutBtn")
    page.wait_for_url("**/login", timeout=NAV_TIMEOUT)
    _ui_login(page, base_url, user["username"], PASSWORD)


def test_password_change_rejects_mismatched_confirmation(
    logged_in_page: Page, base_url: str
):
    """A confirmation that does not match is caught in the browser."""
    page = logged_in_page
    _open_profile(page, base_url)

    _change_password(page, PASSWORD, NEW_PASSWORD, confirm="Different456!")

    expect(page.locator("#errorAlert")).to_be_visible(timeout=NAV_TIMEOUT)
    expect(page.locator("#errorMessage")).to_contain_text("do not match")
    assert "/profile" in page.url


@pytest.mark.parametrize(
    "weak_password, expected_message",
    [
        ("nouppercase1!", "uppercase letter"),
        ("NoSpecial1234", "special character"),
        ("NoDigitsHere!", "at least one digit"),
    ],
)
def test_password_change_rejects_a_weak_new_password(
    logged_in_page: Page, base_url: str, weak_password, expected_message
):
    """The strength rules from registration also apply to a password change."""
    page = logged_in_page
    _open_profile(page, base_url)

    _change_password(page, PASSWORD, weak_password)

    expect(page.locator("#errorAlert")).to_be_visible(timeout=NAV_TIMEOUT)
    expect(page.locator("#errorMessage")).to_contain_text(expected_message)
    expect(page.locator("#errorMessage")).not_to_contain_text("[object Object]")
    assert "/profile" in page.url


def test_password_change_rejects_reusing_the_current_password(
    logged_in_page: Page, base_url: str
):
    """Re-submitting the same password is refused."""
    page = logged_in_page
    _open_profile(page, base_url)

    _change_password(page, PASSWORD, PASSWORD)

    expect(page.locator("#errorAlert")).to_be_visible(timeout=NAV_TIMEOUT)
    expect(page.locator("#errorMessage")).to_contain_text("must be different")


def test_expired_token_on_profile_redirects_to_login(page: Page, base_url: str, user: dict):
    """A rejected token clears the session and returns to the login page."""
    _ui_login(page, base_url, user["username"], user["password"])

    page.evaluate("localStorage.setItem('access_token', 'not-a-real-token')")
    page.goto(f"{base_url}/profile")

    page.wait_for_url("**/login", timeout=NAV_TIMEOUT)
    assert page.evaluate("localStorage.getItem('access_token')") is None
