"""
Unit tests for the shared client-side validators in static/js/script.js.

The email, password and input-styling helpers moved out of register.html so the
profile page could reuse them. They are exercised here one function at a time by
loading the script into a blank browser page: no server, no database and no
page markup are involved.

The password rules are also compared against validate_password_strength in
app/schemas/user.py, which is the contract the browser copy claims to mirror.
"""

from pathlib import Path

import pytest

from app.schemas.user import validate_password_strength

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "static" / "js" / "script.js"

STRONG_PASSWORD = "StrongPass1!"

WEAK_PASSWORDS = [
    ("Sh0rt!", "Password must be at least 8 characters long"),
    ("nouppercase1!", "Password must contain at least one uppercase letter"),
    ("NOLOWERCASE1!", "Password must contain at least one lowercase letter"),
    ("NoDigitsHere!", "Password must contain at least one digit"),
    ("NoSpecial1234", "Password must contain at least one special character"),
]

WEAK_PASSWORD_IDS = [
    "too_short",
    "no_uppercase",
    "no_lowercase",
    "no_digit",
    "no_special",
]

WEAK_PASSWORD_VALUES = [password for password, _ in WEAK_PASSWORDS]


@pytest.fixture(scope="module")
def js(browser_context):
    """A blank page with the shared validators loaded and nothing else."""
    context = browser_context.new_context()
    page = context.new_page()
    page.goto("about:blank")
    page.add_script_tag(path=str(SCRIPT_PATH))
    try:
        yield page
    finally:
        page.close()
        context.close()


# ---------------------------------------------------------------------------
# isValidEmail
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "email",
    [
        "user@example.com",
        "first.last@mail.example.co.uk",
        "user+tag@example.io",
        "u@e.co",
    ],
)
def test_is_valid_email_accepts_a_well_formed_address(js, email):
    """Addresses with a local part, a domain and a dotted suffix pass."""
    assert js.evaluate("(value) => window.isValidEmail(value)", email) is True


@pytest.mark.parametrize(
    "email",
    [
        "",
        "not-an-email",
        "missing-domain@",
        "@missing-local.com",
        "no.dot@localhost",
        "spaces in@example.com",
        "two@@example.com",
    ],
    ids=[
        "empty",
        "no_at_sign",
        "no_domain",
        "no_local_part",
        "no_dot_in_domain",
        "contains_a_space",
        "two_at_signs",
    ],
)
def test_is_valid_email_rejects_a_malformed_address(js, email):
    """Anything without the local@domain.tld shape is refused."""
    assert js.evaluate("(value) => window.isValidEmail(value)", email) is False


# ---------------------------------------------------------------------------
# describePasswordError
# ---------------------------------------------------------------------------
def test_describe_password_error_returns_null_for_a_strong_password(js):
    """A password meeting every rule has no failure to report."""
    assert js.evaluate("(value) => window.describePasswordError(value)", STRONG_PASSWORD) is None


@pytest.mark.parametrize("password, expected_message", WEAK_PASSWORDS, ids=WEAK_PASSWORD_IDS)
def test_describe_password_error_names_the_broken_rule(js, password, expected_message):
    """Each rule reports its own message when it is the one that fails."""
    assert (
        js.evaluate("(value) => window.describePasswordError(value)", password)
        == expected_message
    )


def test_describe_password_error_reports_the_first_failure_only(js):
    """A password breaking several rules reports the earliest one."""
    assert (
        js.evaluate("(value) => window.describePasswordError(value)", "abc")
        == "Password must be at least 8 characters long"
    )


@pytest.mark.parametrize("value", [None, ""], ids=["null", "empty_string"])
def test_describe_password_error_handles_a_missing_password(js, value):
    """A missing value is treated as an empty password, not a crash."""
    assert (
        js.evaluate("(value) => window.describePasswordError(value)", value)
        == "Password must be at least 8 characters long"
    )


@pytest.mark.parametrize("password", WEAK_PASSWORD_VALUES, ids=WEAK_PASSWORD_IDS)
def test_browser_rules_report_the_same_message_as_the_api(js, password):
    """The browser copy of the rules matches validate_password_strength word for word."""
    with pytest.raises(ValueError) as excinfo:
        validate_password_strength(password)

    assert js.evaluate("(value) => window.describePasswordError(value)", password) == str(
        excinfo.value
    )


def test_browser_and_api_agree_on_a_strong_password(js):
    """Neither side objects to a password that satisfies every rule."""
    assert validate_password_strength(STRONG_PASSWORD) == STRONG_PASSWORD
    assert js.evaluate("(value) => window.isValidPassword(value)", STRONG_PASSWORD) is True


# ---------------------------------------------------------------------------
# isValidPassword
# ---------------------------------------------------------------------------
def test_is_valid_password_accepts_a_strong_password(js):
    """The boolean wrapper agrees with describePasswordError."""
    assert js.evaluate("(value) => window.isValidPassword(value)", STRONG_PASSWORD) is True


@pytest.mark.parametrize("password", WEAK_PASSWORD_VALUES, ids=WEAK_PASSWORD_IDS)
def test_is_valid_password_rejects_a_weak_password(js, password):
    """Any broken rule makes the password invalid."""
    assert js.evaluate("(value) => window.isValidPassword(value)", password) is False


# ---------------------------------------------------------------------------
# setInputValidation
# ---------------------------------------------------------------------------
def test_set_input_validation_marks_a_valid_input_green(js):
    """A valid input gains the green border class only."""
    classes = js.evaluate(
        """
        () => {
          const input = document.createElement('input');
          window.setInputValidation(input, true);
          return [...input.classList];
        }
        """
    )
    assert classes == ["border-green-500"]


def test_set_input_validation_marks_an_invalid_input_red(js):
    """An invalid input gains the red border class only."""
    classes = js.evaluate(
        """
        () => {
          const input = document.createElement('input');
          window.setInputValidation(input, false);
          return [...input.classList];
        }
        """
    )
    assert classes == ["border-red-500"]


def test_set_input_validation_replaces_the_previous_state(js):
    """Re-checking an input swaps the colour instead of stacking both classes."""
    classes = js.evaluate(
        """
        () => {
          const input = document.createElement('input');
          window.setInputValidation(input, false);
          window.setInputValidation(input, true);
          window.setInputValidation(input, false);
          return [...input.classList];
        }
        """
    )
    assert classes == ["border-red-500"]


def test_set_input_validation_keeps_unrelated_classes(js):
    """Styling classes the template set are left alone."""
    classes = js.evaluate(
        """
        () => {
          const input = document.createElement('input');
          input.className = 'w-full rounded-md';
          window.setInputValidation(input, true);
          return [...input.classList];
        }
        """
    )
    assert classes == ["w-full", "rounded-md", "border-green-500"]
