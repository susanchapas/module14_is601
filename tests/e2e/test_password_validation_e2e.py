"""
Playwright end-to-end tests for the shared password and email validation.

The validators used to live inside register.html; they now sit in
static/js/script.js so the profile page can reuse them. These tests drive both
pages in a real browser to check the two things that move: the live colour
feedback as the user types, and the checks that run before the form is ever
submitted.

The password-change happy path itself is covered in tests/e2e/test_profile_e2e.py.
"""

from uuid import uuid4

import pytest
import requests
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e

NAV_TIMEOUT = 15_000

PASSWORD = "SecurePass123!"
NEW_PASSWORD = "FreshPass456!"

GREEN = "border-green-500"
RED = "border-red-500"


# ---------------------------------------------------------------------------
# Helpers and fixtures
# ---------------------------------------------------------------------------
def _make_user_payload() -> dict:
    """Build a registration payload with a unique username/email."""
    suffix = uuid4().hex[:12]
    return {
        "first_name": "Validation",
        "last_name": "Tester",
        "email": f"validation.{suffix}@example.com",
        "username": f"validation_{suffix}",
        "password": PASSWORD,
        "confirm_password": PASSWORD,
    }


def _classes(page: Page, selector: str) -> list:
    """Return the current class list of an element."""
    return page.eval_on_selector(selector, "el => [...el.classList]")


def _type(page: Page, selector: str, value: str) -> None:
    """Set a value the way a user does, so the 'input' listeners fire."""
    page.fill(selector, value)


@pytest.fixture
def user(base_url: str) -> dict:
    """A freshly registered user."""
    payload = _make_user_payload()
    response = requests.post(f"{base_url}/auth/register", json=payload)
    assert response.status_code == 201, f"Registration failed: {response.text}"
    return payload


@pytest.fixture
def profile_page(page: Page, base_url: str, user: dict) -> Page:
    """A browser page logged in and sitting on the profile page."""
    page.goto(f"{base_url}/login")
    page.fill("#username", user["username"])
    page.fill("#password", user["password"])
    page.click("#loginForm button[type='submit']")
    page.wait_for_url("**/dashboard", timeout=NAV_TIMEOUT)

    page.goto(f"{base_url}/profile")
    expect(page.locator("#passwordCard")).to_be_visible(timeout=NAV_TIMEOUT)
    return page


@pytest.fixture
def register_page(page: Page, base_url: str) -> Page:
    """A browser page on the registration form."""
    page.goto(f"{base_url}/register")
    expect(page.locator("#registrationForm")).to_be_visible(timeout=NAV_TIMEOUT)
    return page


# ---------------------------------------------------------------------------
# Profile page: live feedback while typing
# ---------------------------------------------------------------------------
def test_new_password_field_turns_green_for_a_strong_password(profile_page: Page):
    """A password meeting every rule is marked valid as it is typed."""
    _type(profile_page, "#new_password", NEW_PASSWORD)

    assert GREEN in _classes(profile_page, "#new_password")
    assert RED not in _classes(profile_page, "#new_password")


@pytest.mark.parametrize(
    "weak_password",
    ["short1!", "nouppercase1!", "NOLOWERCASE1!", "NoDigitsHere!", "NoSpecial1234"],
    ids=["too_short", "no_uppercase", "no_lowercase", "no_digit", "no_special"],
)
def test_new_password_field_turns_red_for_a_weak_password(profile_page: Page, weak_password):
    """Every strength rule is reflected in the browser as the user types."""
    _type(profile_page, "#new_password", weak_password)

    assert RED in _classes(profile_page, "#new_password")
    assert GREEN not in _classes(profile_page, "#new_password")


def test_new_password_field_clears_its_colour_when_emptied(profile_page: Page):
    """Clearing the field removes the feedback rather than leaving it red."""
    _type(profile_page, "#new_password", NEW_PASSWORD)
    _type(profile_page, "#new_password", "")

    classes = _classes(profile_page, "#new_password")
    assert GREEN not in classes
    assert RED not in classes


def test_password_colour_updates_from_red_to_green_while_typing(profile_page: Page):
    """The feedback follows the field instead of sticking on the first verdict."""
    _type(profile_page, "#new_password", "weak")
    assert RED in _classes(profile_page, "#new_password")

    _type(profile_page, "#new_password", NEW_PASSWORD)
    assert GREEN in _classes(profile_page, "#new_password")
    assert RED not in _classes(profile_page, "#new_password")


def test_confirmation_field_turns_green_when_it_matches(profile_page: Page):
    """A matching confirmation is marked valid."""
    _type(profile_page, "#new_password", NEW_PASSWORD)
    _type(profile_page, "#confirm_new_password", NEW_PASSWORD)

    assert GREEN in _classes(profile_page, "#confirm_new_password")


def test_confirmation_field_turns_red_when_it_differs(profile_page: Page):
    """A confirmation that drifts from the new password is marked invalid."""
    _type(profile_page, "#new_password", NEW_PASSWORD)
    _type(profile_page, "#confirm_new_password", "Different456!")

    assert RED in _classes(profile_page, "#confirm_new_password")
    assert GREEN not in _classes(profile_page, "#confirm_new_password")


def test_confirmation_field_clears_its_colour_when_emptied(profile_page: Page):
    """An empty confirmation carries no verdict."""
    _type(profile_page, "#new_password", NEW_PASSWORD)
    _type(profile_page, "#confirm_new_password", NEW_PASSWORD)
    _type(profile_page, "#confirm_new_password", "")

    classes = _classes(profile_page, "#confirm_new_password")
    assert GREEN not in classes
    assert RED not in classes


# ---------------------------------------------------------------------------
# Profile page: checks that run before the request is sent
# ---------------------------------------------------------------------------
def test_weak_password_is_refused_without_calling_the_api(profile_page: Page):
    """The browser reports the broken rule itself; no request is made."""
    requests_sent = []
    profile_page.on(
        "request",
        lambda request: requests_sent.append(request.url)
        if "/users/me/password" in request.url
        else None,
    )

    profile_page.fill("#current_password", PASSWORD)
    profile_page.fill("#new_password", "NoSpecial1234")
    profile_page.fill("#confirm_new_password", "NoSpecial1234")
    profile_page.click("#passwordForm button[type='submit']")

    expect(profile_page.locator("#errorMessage")).to_contain_text(
        "special character", timeout=NAV_TIMEOUT
    )
    assert requests_sent == []


def test_strength_is_reported_before_the_confirmation_mismatch(profile_page: Page):
    """A weak password is named as weak even when the confirmation is also wrong."""
    profile_page.fill("#current_password", PASSWORD)
    profile_page.fill("#new_password", "weak")
    profile_page.fill("#confirm_new_password", "alsoweak")
    profile_page.click("#passwordForm button[type='submit']")

    expect(profile_page.locator("#errorMessage")).to_contain_text(
        "at least 8 characters", timeout=NAV_TIMEOUT
    )


def test_reusing_the_current_password_is_refused_without_calling_the_api(profile_page: Page):
    """Submitting the same password again is caught in the browser."""
    requests_sent = []
    profile_page.on(
        "request",
        lambda request: requests_sent.append(request.url)
        if "/users/me/password" in request.url
        else None,
    )

    profile_page.fill("#current_password", PASSWORD)
    profile_page.fill("#new_password", PASSWORD)
    profile_page.fill("#confirm_new_password", PASSWORD)
    profile_page.click("#passwordForm button[type='submit']")

    expect(profile_page.locator("#errorMessage")).to_contain_text(
        "must be different", timeout=NAV_TIMEOUT
    )
    assert requests_sent == []


def test_a_valid_change_still_reaches_the_api(profile_page: Page, base_url: str, user: dict):
    """The new checks do not block a legitimate password change."""
    profile_page.fill("#current_password", PASSWORD)
    profile_page.fill("#new_password", NEW_PASSWORD)
    profile_page.fill("#confirm_new_password", NEW_PASSWORD)
    profile_page.click("#passwordForm button[type='submit']")

    expect(profile_page.locator("#successMessage")).to_contain_text(
        "Password updated", timeout=NAV_TIMEOUT
    )

    login = requests.post(
        f"{base_url}/auth/login",
        json={"username": user["username"], "password": NEW_PASSWORD},
    )
    assert login.status_code == 200


# ---------------------------------------------------------------------------
# Register page: the same helpers, still wired up after the move
# ---------------------------------------------------------------------------
def test_register_password_field_still_validates_live(register_page: Page):
    """The registration form keeps its strength feedback."""
    _type(register_page, "#password", "weak")
    assert RED in _classes(register_page, "#password")

    _type(register_page, "#password", PASSWORD)
    assert GREEN in _classes(register_page, "#password")


def test_register_email_field_still_validates_on_blur(register_page: Page):
    """A malformed email is flagged when the field loses focus."""
    register_page.eval_on_selector("#email", "el => el.type = 'text'")
    register_page.fill("#email", "not-an-email")
    register_page.locator("#email").blur()
    assert RED in _classes(register_page, "#email")

    register_page.fill("#email", "valid.address@example.com")
    register_page.locator("#email").blur()
    assert GREEN in _classes(register_page, "#email")


def test_register_confirmation_field_still_flags_a_mismatch(register_page: Page):
    """The password-match hint still appears for a mismatched confirmation."""
    register_page.fill("#password", PASSWORD)
    register_page.fill("#confirm_password", "Different456!")

    expect(register_page.locator("#passwordMatchError")).to_be_visible()
    assert RED in _classes(register_page, "#confirm_password")

    register_page.fill("#confirm_password", PASSWORD)
    expect(register_page.locator("#passwordMatchError")).to_be_hidden()
    assert GREEN in _classes(register_page, "#confirm_password")


def test_register_refuses_a_weak_password_on_submit(register_page: Page):
    """The submit-time strength check still stops the request."""
    payload = _make_user_payload()
    register_page.fill("#username", payload["username"])
    register_page.fill("#email", payload["email"])
    register_page.fill("#first_name", payload["first_name"])
    register_page.fill("#last_name", payload["last_name"])
    register_page.fill("#password", "weakpass")
    register_page.fill("#confirm_password", "weakpass")
    register_page.click("#registrationForm button[type='submit']")

    expect(register_page.locator("#errorAlert")).to_be_visible(timeout=NAV_TIMEOUT)
    assert "/register" in register_page.url
