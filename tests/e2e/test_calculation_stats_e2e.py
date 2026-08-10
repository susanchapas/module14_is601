"""
Playwright end-to-end tests for the dashboard usage summary.

One test walks the journey the summary exists for: log in with an empty history,
calculate a few things, delete one, and watch the rendered numbers follow. What
the numbers should be is settled in tests/unit/test_calculation_stats.py and how
the endpoint serves them in tests/integration/test_calculation_stats.py; this
file only checks that the dashboard shows them and keeps them current.
"""

import re
from uuid import uuid4

import pytest
import requests
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e

NAV_TIMEOUT = 15_000

PASSWORD = "SecurePass123!"


# ---------------------------------------------------------------------------
# Helpers and fixtures
# ---------------------------------------------------------------------------
def _register_user(base_url: str) -> dict:
    """Register a user over the API; the register form is covered elsewhere."""
    suffix = uuid4().hex[:12]
    payload = {
        "first_name": "Stats",
        "last_name": "Tester",
        "email": f"stats.{suffix}@example.com",
        "username": f"stats_{suffix}",
        "password": PASSWORD,
        "confirm_password": PASSWORD,
    }
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
    expect(page.locator("#statsCard")).to_be_visible(timeout=NAV_TIMEOUT)
    # The placeholder is replaced once the summary has loaded.
    expect(page.locator("#statTotal")).to_have_text(re.compile(r"^\d+$"), timeout=NAV_TIMEOUT)


def _calculate(page: Page, calculation_type: str, inputs: str) -> None:
    """
    Submit the new-calculation form and wait for the summary to take it in.

    Waiting on the total rather than on the success alert is what keeps
    consecutive calls apart: the page clears the form once a submission
    completes, so filling it again too early would wipe the values.
    """
    expected_total = int(page.locator("#statTotal").inner_text()) + 1
    page.select_option("#calcType", calculation_type)
    page.fill("#calcInputs", inputs)
    page.click("#calculationForm button[type='submit']")
    expect(page.locator("#statTotal")).to_have_text(str(expected_total), timeout=NAV_TIMEOUT)


def _type_count(page: Page, calculation_type: str):
    """Locator for one type's count in the per-type breakdown."""
    return page.locator(f'#statsByType [data-type-count="{calculation_type}"]')


@pytest.fixture
def user(base_url: str) -> dict:
    """A freshly registered user with an empty calculation history."""
    return _register_user(base_url)


@pytest.fixture(autouse=True)
def accept_dialogs(page: Page):
    """Auto-accept the confirm() dialogs used by the delete and logout buttons."""
    page.on("dialog", lambda dialog: dialog.accept())


# ---------------------------------------------------------------------------
# The full journey
# ---------------------------------------------------------------------------
def test_summary_follows_the_users_calculations(page: Page, base_url: str, user: dict):
    """
    Full flow: empty summary -> calculate -> summary updates -> delete -> it drops.

    This is the scenario the report exists for, so it is asserted end to end
    rather than split across smaller tests.
    """
    _ui_login(page, base_url, user["username"], user["password"])

    # A new account starts with nothing to report.
    expect(page.locator("#statTotal")).to_have_text("0", timeout=NAV_TIMEOUT)
    expect(page.locator("#statAverageOperands")).to_have_text("0.00")
    expect(page.locator("#statMostUsed")).to_have_text("—")
    expect(page.locator("#statLastCalculation")).to_have_text("—")

    # 1) The first calculation is counted straight away.
    _calculate(page, "addition", "5, 10")
    expect(page.locator("#statTotal")).to_have_text("1", timeout=NAV_TIMEOUT)
    expect(page.locator("#statAverageOperands")).to_have_text("2.00")
    expect(page.locator("#statMostUsed")).to_have_text("addition")
    expect(page.locator("#statLastCalculation")).not_to_have_text("—")

    # 2) A longer calculation of another type moves the average and the breakdown,
    #    which lists every type so its shape never changes.
    _calculate(page, "division", "100, 5, 2")
    expect(page.locator("#statTotal")).to_have_text("2", timeout=NAV_TIMEOUT)
    expect(page.locator("#statAverageOperands")).to_have_text("2.50")
    expect(_type_count(page, "addition")).to_have_text("1")
    expect(_type_count(page, "division")).to_have_text("1")
    expect(_type_count(page, "subtraction")).to_have_text("0")
    expect(_type_count(page, "multiplication")).to_have_text("0")

    # 3) The reported total agrees with the rows the user can actually see.
    expect(page.locator("#calculationsTable tr")).to_have_count(2)

    # 4) Deleting a calculation takes it back out of the summary.
    page.locator(".delete-calc").first.click()
    expect(page.locator("#statTotal")).to_have_text("1", timeout=NAV_TIMEOUT)

    # 5) And the summary is stored, not just held in the browser.
    page.reload()
    expect(page.locator("#statTotal")).to_have_text("1", timeout=NAV_TIMEOUT)
