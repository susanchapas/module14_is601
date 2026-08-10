# Module 7: Testing

## Introduction

In this module, we'll implement comprehensive testing for our application. Testing is a critical part of software development that helps ensure our code works as expected and continues to work as we make changes. We'll cover different types of tests and how to implement them in our FastAPI application.

## Objectives

- Understand different types of tests (unit, integration, end-to-end)
- Set up pytest for our FastAPI application
- Write unit tests for our models and utility functions
- Write integration tests for our API endpoints
- Implement end-to-end tests for our web interface
- Learn about test fixtures and mocking

## Types of Tests

### Unit Tests

Unit tests focus on testing individual components in isolation. These tests are:
- Fast
- Simple
- Test one thing at a time
- Independent (no external dependencies)

### Integration Tests

Integration tests verify that different components work together correctly. These tests:
- Test the interaction between components
- May involve external dependencies (e.g., database)
- Are slower than unit tests
- Test multiple components together

### End-to-End Tests

End-to-end (E2E) tests verify the entire application from the user's perspective. These tests:
- Test the entire system
- Use a browser or simulate browser behavior
- Are slow
- Test real user scenarios

## Setting Up Testing Environment

Let's set up our testing environment. Create a `conftest.py` file in the `tests` directory:

```python
# tests/conftest.py
import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.user import User
from app.auth.jwt import get_password_hash

# Use an in-memory SQLite database for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"

@pytest.fixture(scope="session")
def test_engine():
    """Create a SQLAlchemy engine for testing."""
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    # Drop all tables after tests complete
    Base.metadata.drop_all(bind=engine)
    
@pytest.fixture(scope="function")
def db_session(test_engine):
    """Create a new database session for a test."""
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()

@pytest.fixture(scope="function")
def client(db_session):
    """Create a test client for FastAPI app."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    
    # Clear dependency overrides after test
    app.dependency_overrides.clear()

@pytest.fixture(scope="function")
def test_user(db_session):
    """Create a test user and return their data."""
    user_data = {
        "username": "testuser",
        "email": "test@example.com",
        "first_name": "Test",
        "last_name": "User",
        "password": get_password_hash("password123")
    }
    
    user = User(**user_data)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    
    return user

@pytest.fixture(scope="function")
def auth_header(test_user):
    """Create authorization headers with JWT token."""
    access_token = User.create_access_token({"sub": str(test_user.id)})
    return {"Authorization": f"Bearer {access_token}"}
```

## Writing Unit Tests

Let's write some tests for our calculation models. These live in
`tests/integration/test_calculation.py`, because the classes under test are
SQLAlchemy models rather than free functions:

```python
# tests/integration/test_calculation.py
import uuid

import pytest

from app.models.calculation import Addition, Subtraction, Multiplication, Division

def dummy_user_id():
    return uuid.uuid4()

def test_addition_get_result():
    """Test that Addition.get_result returns the correct sum."""
    inputs = [10, 5, 3.5]
    addition = Addition(user_id=dummy_user_id(), inputs=inputs)

    assert addition.get_result() == sum(inputs)

def test_subtraction():
    """Test subtraction calculation."""
    # Create a Subtraction calculation
    subtraction = Subtraction(user_id=dummy_user_id(), inputs=[10, 2, 3])
    
    # Test that it calculates the correct result
    assert subtraction.get_result() == 5

def test_multiplication():
    """Test multiplication calculation."""
    # Create a Multiplication calculation
    multiplication = Multiplication(user_id=dummy_user_id(), inputs=[2, 3, 4])
    
    # Test that it calculates the correct result
    assert multiplication.get_result() == 24

def test_division():
    """Test division calculation."""
    # Create a Division calculation
    division = Division(user_id=dummy_user_id(), inputs=[12, 3, 2])
    
    # Test that it calculates the correct result
    assert division.get_result() == 2

def test_division_by_zero():
    """Test division by zero raises ValueError."""
    # Create a Division calculation with a zero divisor
    division = Division(user_id=dummy_user_id(), inputs=[12, 0])
    
    # Test that division by zero raises a ValueError
    with pytest.raises(ValueError) as excinfo:
        division.get_result()
    
    # Verify the error message
    assert "Cannot divide by zero" in str(excinfo.value)

def test_invalid_inputs():
    """Test invalid inputs raise ValueError."""
    # Test with single input
    addition = Addition(user_id=dummy_user_id(), inputs=[1])
    with pytest.raises(ValueError) as excinfo:
        addition.get_result()
    assert "at least two numbers" in str(excinfo.value)
    
    # Test with non-list input
    addition = Addition(user_id=dummy_user_id(), inputs="not a list")
    with pytest.raises(ValueError) as excinfo:
        addition.get_result()
    assert "Inputs must be a list" in str(excinfo.value)
```

## Writing Integration Tests

Now, let's write integration tests for our API endpoints:

```python
# tests/integration/test_calculation.py
import pytest
import uuid
from app.models.calculation import Calculation

def test_create_calculation(client, auth_header):
    """Test creating a new calculation."""
    # Create a calculation via the API
    response = client.post(
        "/calculations",
        json={"type": "addition", "inputs": [1, 2, 3]},
        headers=auth_header
    )
    
    # Check that the response is successful
    assert response.status_code == 201
    
    # Check that the response contains the expected data
    data = response.json()
    assert data["type"] == "addition"
    assert data["inputs"] == [1, 2, 3]
    assert data["result"] == 6
    assert "id" in data
    assert "created_at" in data
    assert "updated_at" in data

def test_list_calculations(client, auth_header, db_session, test_user):
    """Test listing calculations for a user."""
    # Create a few calculations for the test user
    calcs = []
    for i in range(3):
        calc = Calculation.create(
            calculation_type="addition",
            user_id=test_user.id,
            inputs=[i, i+1, i+2]
        )
        calc.result = calc.get_result()
        db_session.add(calc)
    db_session.commit()
    
    # Get the calculations via the API
    response = client.get("/calculations", headers=auth_header)
    
    # Check that the response is successful
    assert response.status_code == 200
    
    # Check that the response contains all the calculations
    data = response.json()
    assert len(data) == 3
    
    # Check that the calculations belong to the test user
    for calc in data:
        assert str(calc["user_id"]) == str(test_user.id)

def test_get_calculation(client, auth_header, db_session, test_user):
    """Test getting a specific calculation."""
    # Create a calculation for the test user
    calc = Calculation.create(
        calculation_type="addition",
        user_id=test_user.id,
        inputs=[1, 2, 3]
    )
    calc.result = calc.get_result()
    db_session.add(calc)
    db_session.commit()
    db_session.refresh(calc)
    
    # Get the calculation via the API
    response = client.get(f"/calculations/{calc.id}", headers=auth_header)
    
    # Check that the response is successful
    assert response.status_code == 200
    
    # Check that the response contains the expected data
    data = response.json()
    assert data["type"] == "addition"
    assert data["inputs"] == [1, 2, 3]
    assert data["result"] == 6
    assert str(data["id"]) == str(calc.id)

def test_update_calculation(client, auth_header, db_session, test_user):
    """Test updating a calculation."""
    # Create a calculation for the test user
    calc = Calculation.create(
        calculation_type="addition",
        user_id=test_user.id,
        inputs=[1, 2, 3]
    )
    calc.result = calc.get_result()
    db_session.add(calc)
    db_session.commit()
    db_session.refresh(calc)
    
    # Update the calculation via the API
    response = client.put(
        f"/calculations/{calc.id}",
        json={"inputs": [4, 5, 6]},
        headers=auth_header
    )
    
    # Check that the response is successful
    assert response.status_code == 200
    
    # Check that the response contains the updated data
    data = response.json()
    assert data["inputs"] == [4, 5, 6]
    assert data["result"] == 15  # Updated result (4+5+6=15)

def test_delete_calculation(client, auth_header, db_session, test_user):
    """Test deleting a calculation."""
    # Create a calculation for the test user
    calc = Calculation.create(
        calculation_type="addition",
        user_id=test_user.id,
        inputs=[1, 2, 3]
    )
    calc.result = calc.get_result()
    db_session.add(calc)
    db_session.commit()
    db_session.refresh(calc)
    
    # Delete the calculation via the API
    response = client.delete(f"/calculations/{calc.id}", headers=auth_header)
    
    # Check that the response is successful (204 No Content)
    assert response.status_code == 204
    
    # Check that the calculation is no longer in the database
    deleted_calc = db_session.query(Calculation).filter(Calculation.id == calc.id).first()
    assert deleted_calc is None
```

## Testing Authentication

Let's write tests for our authentication endpoints:

```python
# tests/integration/test_user_auth.py
def test_register(client):
    """Test user registration."""
    # Register a new user
    response = client.post(
        "/auth/register",
        json={
            "username": "newuser",
            "email": "newuser@example.com",
            "first_name": "New",
            "last_name": "User",
            "password": "password123",
            "confirm_password": "password123"
        }
    )
    
    # Check that the response is successful
    assert response.status_code == 201
    
    # Check that the response contains the expected data
    data = response.json()
    assert data["username"] == "newuser"
    assert data["email"] == "newuser@example.com"
    assert data["first_name"] == "New"
    assert data["last_name"] == "User"
    assert "id" in data
    assert "password" not in data  # Password should not be returned

def test_login(client, test_user):
    """Test user login."""
    # Login with the test user
    response = client.post(
        "/auth/login",
        json={
            "username": "testuser",
            "password": "password123"
        }
    )
    
    # Check that the response is successful
    assert response.status_code == 200
    
    # Check that the response contains the expected data
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"
    assert "expires_at" in data
    assert data["username"] == "testuser"
    assert data["email"] == "test@example.com"

def test_protected_route_with_token(client, auth_header):
    """Test accessing a protected route with a valid token."""
    # Access a protected route with the authorization header
    response = client.get("/calculations", headers=auth_header)
    
    # Check that the response is successful
    assert response.status_code == 200

def test_protected_route_without_token(client):
    """Test accessing a protected route without a token."""
    # Access a protected route without authorization
    response = client.get("/calculations")
    
    # Check that the response is unauthorized
    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"
```

## Writing End-to-End Tests

For end-to-end tests, we'll use Playwright to test the application from a user's perspective:

```python
# tests/e2e/test_fastapi_calculator.py
import pytest
from playwright.sync_api import Page, expect

def test_home_page(page: Page):
    """Test the home page loads correctly."""
    # Navigate to the home page
    page.goto("http://localhost:8001/")
    
    # Check that the page title is correct
    expect(page).to_have_title("Home - Calculator App")
    
    # Check that the page contains the expected elements
    expect(page.locator("h1")).to_contain_text("Welcome to Calculator App")
    expect(page.locator(".feature-card")).to_have_count(4)
    
    # Check that login and register links exist
    expect(page.locator("a[href='/login']")).to_be_visible()
    expect(page.locator("a[href='/register']")).to_be_visible()

def test_user_registration_and_login(page: Page):
    """Test user registration and login flow."""
    # Generate a unique username to avoid conflicts
    unique_username = f"testuser_{pytest.unique_id}"
    
    # Navigate to the registration page
    page.goto("http://localhost:8001/register")
    
    # Fill out the registration form
    page.fill("#first_name", "Test")
    page.fill("#last_name", "User")
    page.fill("#username", unique_username)
    page.fill("#email", f"{unique_username}@example.com")
    page.fill("#password", "password123")
    page.fill("#confirm_password", "password123")
    
    # Submit the form
    page.click("button[type='submit']")
    
    # Wait for redirect to login page
    page.wait_for_url("**/login**")
    
    # Fill out the login form
    page.fill("#username", unique_username)
    page.fill("#password", "password123")
    
    # Submit the form
    page.click("button[type='submit']")
    
    # Wait for redirect to dashboard
    page.wait_for_url("**/dashboard")
    
    # Check that we're on the dashboard
    expect(page.locator("h1")).to_contain_text("Dashboard")
    
    # Check that the logout link is visible
    expect(page.locator("#logout-link")).to_be_visible()

def test_calculator_functionality(page: Page, auth_setup):
    """
    Test the calculator functionality.
    
    Requires the auth_setup fixture to log in before the test.
    """
    # Navigate to the dashboard
    page.goto("http://localhost:8001/dashboard")
    
    # Fill out the calculation form
    page.select_option("#calculation-type", "addition")
    page.fill("#calculation-inputs", "5, 10, 15")
    
    # Submit the form
    page.click("#calculation-form button[type='submit']")
    
    # Wait for the result to appear
    page.wait_for_selector("#calculation-result", state="visible")
    
    # Check that the result is correct
    expect(page.locator("#result-value")).to_contain_text("30")
    
    # Check that the calculation appears in the list
    expect(page.locator(".calc-result")).to_contain_text("30")
    expect(page.locator(".calc-type.addition")).to_be_visible()
    expect(page.locator(".calc-inputs")).to_contain_text("5 , 10 , 15")

@pytest.fixture
def auth_setup(page: Page):
    """Set up authentication for tests that require login."""
    # Navigate to the login page
    page.goto("http://localhost:8001/login")
    
    # Fill out the login form
    page.fill("#username", "testuser")
    page.fill("#password", "password123")
    
    # Submit the form
    page.click("button[type='submit']")
    
    # Wait for redirect to dashboard
    page.wait_for_url("**/dashboard")
    
    yield
    
    # Log out after the test
    page.click("#logout-link")
    page.wait_for_url("**/")
```

## Running Tests

To run the tests, we'll set up a pytest configuration file:

```ini
# pytest.ini
[pytest]
testpaths = tests

addopts = --cov=app --cov-report=term-missing

python_files = test_*.py *_test.py
python_classes = Test*
python_functions = test_*

markers =
    slow: marks tests as slow (deselect with '-m "not slow"')
    fast: marks tests as fast (deselect with '-m "not fast"')
    e2e: marks tests as end-to-end (use with '-m "e2e"')

# Deprecation warnings from our own code are failures, not noise. Third-party
# noise gets a narrow, specific ignore below rather than a blanket one.
filterwarnings =
    error::DeprecationWarning
    error::PendingDeprecationWarning
    ignore::ResourceWarning
    ignore:Using `httpx` with `starlette.testclient` is deprecated
```

### Why deprecations are errors

It is tempting to write `ignore::DeprecationWarning` and move on. Don't. A
blanket ignore hides your own deprecated calls along with everyone else's, and
the warnings you most want to see — `.dict()` instead of `.model_dump()`,
`min_items` instead of `min_length` — are precisely the ones that will break on
the next major upgrade of a dependency.

Setting `error::DeprecationWarning` makes the test that reaches a deprecated
call fail, with a traceback pointing at the call. Third-party warnings you
genuinely cannot fix get one narrow `ignore` line each, matched on the message
text, so the exemption is visible and reviewable.

One limitation to be aware of: the e2e tests drive a Uvicorn **subprocess**,
which does not inherit pytest's warning filters. A deprecated call on a path
that only e2e tests exercise will not be caught by this.

Now we can run the tests with different options:

```bash
# Run all tests
pytest

# Run unit tests only
pytest tests/unit/

# Run a specific test file
pytest tests/integration/test_user_auth.py

# Run a specific test function
pytest tests/integration/test_user_auth.py::test_user_authentication

# Show detailed output
pytest -v

# Skip coverage for a faster run
pytest --no-cov
```

## Test Mocking and Fixtures

### Mocking

Mocking is a technique used in testing to replace a real implementation with a controlled version that simulates the behavior of the real implementation. This is useful for:

- Isolating the unit under test
- Eliminating external dependencies
- Testing edge cases or error conditions
- Speeding up tests

Example of mocking the JWT functions:

```python
from unittest.mock import patch

def test_login_with_mocked_jwt(client, test_user):
    """Test login with mocked JWT function."""
    # Mock the create_token function to return a predefined token
    with patch('app.models.user.User.create_access_token') as mock_access_token:
        with patch('app.models.user.User.create_refresh_token') as mock_refresh_token:
            # Set the return values for the mocked functions
            mock_access_token.return_value = "mocked_access_token"
            mock_refresh_token.return_value = "mocked_refresh_token"
            
            # Login with the test user
            response = client.post(
                "/auth/login",
                json={
                    "username": "testuser",
                    "password": "password123"
                }
            )
            
            # Check that the response is successful
            assert response.status_code == 200
            
            # Check that the response contains the mocked tokens
            data = response.json()
            assert data["access_token"] == "mocked_access_token"
            assert data["refresh_token"] == "mocked_refresh_token"
            
            # Verify that the mock functions were called
            mock_access_token.assert_called_once()
            mock_refresh_token.assert_called_once()
```

### Fixtures

Fixtures are a way to provide data or state to tests. We've already seen several examples in our `conftest.py` file. Fixtures can be used for:

- Setting up test data
- Creating test clients
- Managing database connections
- Providing authentication
- Cleaning up after tests

Here's an example of a more complex fixture:

```python
@pytest.fixture(scope="function")
def test_calculations(db_session, test_user):
    """Create test calculations for a user."""
    calculations = []
    
    # Create one of each calculation type
    calc_types = ["addition", "subtraction", "multiplication", "division"]
    for calc_type in calc_types:
        calc = Calculation.create(
            calculation_type=calc_type,
            user_id=test_user.id,
            inputs=[10, 5]
        )
        calc.result = calc.get_result()
        db_session.add(calc)
    
    db_session.commit()
    
    # Refresh the calculations to get their IDs
    for calc in calculations:
        db_session.refresh(calc)
    
    return calculations
```

## Test Coverage

Test coverage measures how much of your code is executed during your tests. To check coverage, use:

```bash
pytest --cov=app --cov-report=term-missing
```

This is already the default in `pytest.ini`, so a bare `pytest` reports it.
The HTML and XML reports are deliberately *not* on by default — otherwise
running one test would regenerate the whole `htmlcov/` tree:

```bash
pytest --cov-report=html   # htmlcov/index.html
pytest --cov-report=xml    # coverage.xml, for CI to upload
```

This will show which lines of code are not covered by tests, helping you identify areas that need more testing.

### Run the suite once, not once per directory

Coverage data is written at the end of a run, so **each `pytest` invocation
overwrites the last one's data** unless you pass `--cov-append`. A CI script
like this looks thorough and silently reports only the last number:

```bash
# Wrong: each line discards the coverage data from the line above it
pytest tests/unit/
pytest tests/integration/
pytest tests/e2e/
```

Run the suite in one invocation instead:

```bash
pytest tests/ --cov-report=xml
```

## Linting

Tests catch behaviour; a linter catches the things that are wrong on sight.
[`ruff`](https://docs.astral.sh/ruff/) is configured in `ruff.toml` and runs in
CI before the test job:

```bash
ruff check .          # report
ruff check . --fix    # apply the safe fixes
```

Rule sets `E`, `F`, `I` and `B` are selected. `F` alone justifies it: unused
imports, duplicate imports and unused variables are all things that accumulate
quietly and that no test will ever fail on.

> **Review the autofixes.** `ruff check --fix` is not a rubber stamp. `F401`
> removes imports it believes are unused, but an import can exist purely for
> its side effect. `app/models/user.py` imports `Calculation` so SQLAlchemy can
> resolve the `relationship("Calculation")` string at mapper-configuration
> time; deleting it makes `import app.models.user` raise `InvalidRequestError`.
> That import carries a `# noqa: F401` and a comment saying why.

## Test-Driven Development (TDD)

Test-Driven Development is a methodology where you write tests before writing the implementation. The cycle is:

1. Write a failing test for a new feature
2. Implement the minimal code to make the test pass
3. Refactor the code while keeping the tests passing
4. Repeat

This approach helps ensure that your code is testable and that all code is covered by tests.

## Next Steps

In the next module, we'll learn about containerizing our application with Docker for easier deployment and consistency across environments.

## Additional Resources

- [pytest Documentation](https://docs.pytest.org/)
- [FastAPI Testing Documentation](https://fastapi.tiangolo.com/tutorial/testing/)
- [Playwright Documentation](https://playwright.dev/python/docs/intro)
- [SQLAlchemy Testing Documentation](https://docs.sqlalchemy.org/en/14/orm/session_basics.html#session-frequently-asked-questions)