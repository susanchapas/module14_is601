# Calculations API — Module 14 (IS601)

A FastAPI application that stores per-user calculations with full **BREAD**
(Browse, Read, Edit, Add, Delete) support, JWT authentication, a server-rendered
front end, and a CI/CD pipeline that tests, scans, and publishes a Docker image.

- **Docker Hub:** https://hub.docker.com/r/susanchapas/module14_is601
- **Source:** https://github.com/susanchapas/module14_is601

---

## Table of Contents

- [Features](#features)
- [Tech Stack](#tech-stack)
- [Quick Start (Docker Compose)](#quick-start-docker-compose)
- [Local Development Setup](#local-development-setup)
- [Running the Application](#running-the-application)
- [Running the Tests](#running-the-tests)
- [Linting](#linting)
- [BREAD API Reference](#bread-api-reference)
- [Front-End Pages](#front-end-pages)
- [Validation Rules](#validation-rules)
- [Docker](#docker)
- [CI/CD Pipeline](#cicd-pipeline)
- [Configuration](#configuration)
- [Troubleshooting](#troubleshooting)

---

## Features

- **BREAD endpoints** for calculations, scoped to the authenticated user
- Four operation types: `addition`, `subtraction`, `multiplication`, `division`
- JWT authentication (register, login, bearer-token protected routes)
- User profile page: view and edit account details, change password
- Calculation history summary: totals, average operand count, per-type breakdown
- Server-rendered UI with forms for every BREAD operation
- Shared client-side validation (numeric checks, operation types, divide-by-zero)
- 310 automated tests: unit, integration, API end-to-end, and Playwright browser tests

## Tech Stack

| Layer      | Technology                              |
| ---------- | --------------------------------------- |
| API        | FastAPI, Pydantic v2, Uvicorn           |
| Database   | PostgreSQL, SQLAlchemy 2.0              |
| Auth       | python-jose (JWT), passlib + bcrypt     |
| Front end  | Jinja2 templates, Tailwind CSS, vanilla JS |
| Testing    | pytest, Playwright, requests, Faker     |
| CI/CD      | GitHub Actions, Trivy, Docker Hub       |

---

## Quick Start (Docker Compose)

The fastest way to get the whole stack (app + PostgreSQL + pgAdmin) running:

```bash
docker compose up --build
```

Then open:

| Service    | URL                          |
| ---------- | ---------------------------- |
| App        | http://localhost:8000        |
| API docs   | http://localhost:8000/docs   |
| pgAdmin    | http://localhost:5050        |

This creates both `fastapi_db` and the `fastapi_test_db` used by the test suite.

Stop everything with:

```bash
docker compose down       # keeps database data
docker compose down -v    # also wipes the database volume
```

> **Note:** the app image bakes in the source code, so after changing Python code
> rebuild with `docker compose up -d --build web`. For an edit-reload workflow,
> run only the database in Docker and the app locally — see
> [Local Development Setup](#local-development-setup).

---

## Local Development Setup

### 1. Prerequisites

- Python 3.10+
- Docker (for PostgreSQL, or install PostgreSQL 17 natively)

### 2. Create a virtual environment and install dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Install the Playwright browser

Required for the browser-based end-to-end tests:

```bash
playwright install chromium
```

### 4. Start PostgreSQL

Run only the database in Docker, and the app locally with hot reload:

```bash
docker compose up -d db
```

This creates `fastapi_db` and `fastapi_test_db` automatically on first start.

Or as a standalone container, without Compose:

```bash
docker run -d --name m14_pg \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=fastapi_db \
  -p 5432:5432 postgres:17

# Create the database used by the test suite
docker exec m14_pg psql -U postgres -c "CREATE DATABASE fastapi_test_db;"
```

---

## Running the Application

With the virtual environment active and PostgreSQL running:

```bash
export DATABASE_URL="postgresql://postgres:postgres@localhost:5432/fastapi_db"
uvicorn app.main:app --reload --port 8000
```

Visit http://localhost:8000. Tables are created automatically on startup.

Interactive API documentation is available at:

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

---

## Running the Tests

All test commands assume the virtual environment is active and PostgreSQL is
running.

The suite uses its own database, `TEST_DATABASE_URL`, which defaults to
`fastapi_test_db`. Nothing needs to be exported: the tests never touch
`DATABASE_URL`, so the application's data is safe to leave in place.

> **The test database is wiped on every run.** Every table in
> `TEST_DATABASE_URL` is dropped at the start of a run and again at the end. If
> `TEST_DATABASE_URL` and `DATABASE_URL` name the same database, the suite
> refuses to start rather than destroy the application's data.

### Everything

```bash
pytest
```

### By category

```bash
pytest tests/unit/           # Stats aggregation, client-side validators, profile logic
pytest tests/integration/    # Models, schemas, routes, database, auth
pytest tests/e2e/            # API + Playwright browser tests
```

### Only the Playwright browser tests

```bash
pytest tests/e2e/test_calculations_bread_e2e.py
```

### Useful flags

| Flag                | Effect                                            |
| ------------------- | ------------------------------------------------- |
| `--no-cov`          | Skip coverage reporting (faster)                  |
| `--preserve-db`     | Keep test data after the run, for inspection      |
| `--run-slow`        | Include tests marked `slow`                       |
| `-m e2e`            | Run only end-to-end tests                         |
| `-k <expr>`         | Run tests matching an expression                  |

Coverage is enabled by default via `pytest.ini`, which prints a
`term-missing` report. The HTML and XML reports are *not* on by default, so a
single-test run does not regenerate them; ask for them explicitly:

```bash
pytest --cov-report=html   # writes htmlcov/index.html
pytest --cov-report=xml    # writes coverage.xml
```

CI runs the whole suite in one `pytest tests/` invocation. Running unit,
integration and e2e as three separate invocations would make each pass
overwrite the previous coverage data, leaving only the last one's numbers.

The test suite starts its own Uvicorn server on a free port, so you do **not**
need the app running separately.

### Deprecation warnings are errors

`pytest.ini` sets `error::DeprecationWarning`, so a deprecated call in
first-party code fails the test that reaches it rather than scrolling past in a
warnings summary. Third-party noise gets a narrow, specific `ignore` line — not
a blanket one.

One caveat worth knowing: the e2e tests drive a Uvicorn **subprocess**, which
runs outside pytest's warning filters. Code paths exercised only through e2e
tests are therefore not covered by this guard.

---

## Linting

[`ruff`](https://docs.astral.sh/ruff/) is configured in [`ruff.toml`](ruff.toml)
and runs in CI before the tests:

```bash
ruff check .          # report
ruff check . --fix    # apply the safe fixes
```

The selected rule sets are `E`, `F`, `I` and `B`. `F` is the one that pays for
itself — it catches unused and duplicated imports, which is what motivated
adding a linter here.

Two configuration notes:

- **`B008` is exempted for FastAPI.** Bugbear flags function calls in default
  arguments, and `Depends()` is exactly that. The exemption list in `ruff.toml`
  covers `Depends`, `Query`, `Path`, `Body`, `Header`, `Form` and `File`.
- **`UP` (pyupgrade) is not selected.** Its only findings in this codebase are
  `typing.List`/`Optional` rewrites — style, not correctness — and the schema
  modules it would rewrite are quoted verbatim in the course docs.

Beware one autofix in particular: `F401` will happily delete an import that
exists for its side effect. `app/models/user.py` imports `Calculation` so that
SQLAlchemy can resolve the `relationship("Calculation")` string, and it carries
a `# noqa: F401` with an explanation for that reason.

---

## BREAD API Reference

All calculation endpoints require an `Authorization: Bearer <token>` header and
operate only on the authenticated user's own records.

| Operation  | Method & Path              | Success | Description                                   |
| ---------- | -------------------------- | ------- | --------------------------------------------- |
| **Browse** | `GET /calculations`        | 200     | List all of the current user's calculations   |
| —          | `GET /calculations/stats`  | 200     | History summary: totals, averages, per-type counts |
| **Read**   | `GET /calculations/{id}`   | 200     | Retrieve one calculation by UUID              |
| **Edit**   | `PUT /calculations/{id}`   | 200     | Replace the inputs and recompute the result   |
| **Edit**   | `PATCH /calculations/{id}` | 200     | Partial update; omitted fields are unchanged  |
| **Add**    | `POST /calculations`       | 201     | Create a calculation and compute its result   |
| **Delete** | `DELETE /calculations/{id}`| 204     | Delete a calculation                          |

### Authentication

| Method & Path         | Description                                  |
| --------------------- | -------------------------------------------- |
| `POST /auth/register` | Create an account (201)                      |
| `POST /auth/login`    | Log in with JSON, returns access + refresh    |
| `POST /auth/token`    | OAuth2 form login (used by Swagger UI)        |
| `GET /health`         | Health check, returns `{"status": "ok"}`      |

### User profile

| Method & Path            | Description                                       |
| ------------------------ | ------------------------------------------------- |
| `GET /users/me`          | Current user's profile                            |
| `PUT /users/me`          | Update first name, last name, email, or username  |
| `POST /users/me/password`| Change password (requires the current password)   |

### Error responses

| Status | Meaning                                                             |
| ------ | ------------------------------------------------------------------- |
| 400    | Malformed UUID, or an update that would divide by zero              |
| 401    | Missing, invalid, or expired token                                  |
| 404    | Calculation does not exist **or** belongs to another user           |
| 422    | Request body failed validation (bad type, <2 inputs, divide by zero) |

### Example

```bash
# Register
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"first_name":"Ada","last_name":"Lovelace","email":"ada@example.com",
       "username":"ada","password":"SecurePass123!","confirm_password":"SecurePass123!"}'

# Log in and capture the token
TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"ada","password":"SecurePass123!"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# Add
curl -X POST http://localhost:8000/calculations \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"type":"addition","inputs":[10.5,3,2]}'      # -> result 15.5

# Browse
curl http://localhost:8000/calculations -H "Authorization: Bearer $TOKEN"
```

---

## Front-End Pages

| Route                       | BREAD operation | Description                                   |
| --------------------------- | --------------- | --------------------------------------------- |
| `/`                         | —               | Landing page                                  |
| `/register`                 | —               | Account registration form                     |
| `/login`                    | —               | Login form                                    |
| `/dashboard`                | Browse + Add    | History table, summary card, new-calculation form |
| `/profile`                  | —               | Account details and password change form      |
| `/dashboard/view/{id}`      | Read + Delete   | Calculation details, with a Delete button     |
| `/dashboard/edit/{id}`      | Edit            | Update inputs, with a live result preview     |

The dashboard table provides **View**, **Edit**, and **Delete** actions per row,
so every BREAD operation is reachable from the UI.

## Validation Rules

Shared client-side validation lives in [`static/js/script.js`](static/js/script.js)
and is applied on both the dashboard and the edit page, mirroring the server-side
Pydantic rules:

- Inputs must be a comma-separated list of **valid numbers** (`"5, abc"` is rejected)
- At least **two** numbers are required
- **Division by zero** is blocked before the request is sent
- Operation type is constrained to the four supported types (dropdown + enum)
- The operation type is read-only when editing an existing calculation

---

## Docker

The project defines two images:

| File                  | Image                                                        |
| --------------------- | ------------------------------------------------------------ |
| `Dockerfile`          | The FastAPI application (published to Docker Hub)             |
| `Dockerfile.postgres` | PostgreSQL 17 with `init-db.sh` baked in, so the test database is created automatically |

Baking the init script into the database image rather than bind-mounting it keeps
the stack free of host filesystem mounts, which avoids permission problems on
macOS and Windows.

### Pull the published image

```bash
docker pull susanchapas/module14_is601:latest
```

### Build locally

```bash
docker build -t module14_is601:local .
```

### Run the container

The image needs a reachable PostgreSQL instance:

```bash
docker run -d --name m14_app -p 8000:8000 \
  -e DATABASE_URL="postgresql://postgres:postgres@host.docker.internal:5432/fastapi_db" \
  -e JWT_SECRET_KEY="super-secret-key-for-jwt-min-32-chars" \
  -e JWT_REFRESH_SECRET_KEY="super-refresh-secret-key-min-32-chars" \
  susanchapas/module14_is601:latest
```

The image runs as a non-root user and includes a `HEALTHCHECK` against `/health`.

---

## CI/CD Pipeline

Defined in [`.github/workflows/test.yml`](.github/workflows/test.yml), triggered on
push and pull request to `main`:

1. **test** — spins up a PostgreSQL service, installs dependencies and the
   Playwright browser, runs `ruff check .`, then runs the whole suite in a
   single `pytest tests/` invocation and emits one coverage report.
2. **security** — builds the Docker image and scans it with Trivy, failing on
   `CRITICAL` or `HIGH` vulnerabilities.
3. **deploy** — on `main` only, builds a multi-arch image and pushes it to
   Docker Hub.

### Required GitHub repository secrets

| Secret                | Purpose                                  |
| --------------------- | ---------------------------------------- |
| `DOCKERHUB_USERNAME`  | Docker Hub account name                  |
| `DOCKERHUB_TOKEN`     | Docker Hub access token (not a password) |

The `deploy` job also uses a GitHub environment named `production`.

---

## Configuration

Settings are read from environment variables (or a `.env` file) by
[`app/core/config.py`](app/core/config.py):

| Variable                      | Default                                                    |
| ----------------------------- | ---------------------------------------------------------- |
| `DATABASE_URL`                | `postgresql://postgres:postgres@localhost:5432/fastapi_db` |
| `TEST_DATABASE_URL`           | `postgresql://postgres:postgres@localhost:5432/fastapi_test_db` — wiped by the test suite |
| `JWT_SECRET_KEY`              | **required — no default; the app will not start without it** |
| `JWT_REFRESH_SECRET_KEY`      | **required — no default; the app will not start without it** |
| `ALGORITHM`                   | `HS256`                                                     |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30`                                                        |
| `REFRESH_TOKEN_EXPIRE_DAYS`   | `7`                                                         |
| `BCRYPT_ROUNDS`               | `12`                                                        |

The two JWT secrets deliberately have no defaults. A default would mean a
missing environment variable produces a working app that signs its tokens with
a value published in this repository, which is worse than a startup failure.
Without them, `Settings` raises a `ValidationError` naming the missing keys.

Copy [`.env.example`](.env.example) to get started — it documents every
variable above:

```bash
cp .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(32))"   # for each key
```

`.env` is gitignored.

---

## Troubleshooting

**`operation not permitted` on a mount path (macOS)**
Docker cannot bind-mount from a macOS privacy-protected folder such as
`~/Desktop`, `~/Documents`, or `~/Downloads`. This stack uses **no host bind
mounts**, so Compose is unaffected. If you hit this with your own `docker run -v`
command, either grant Docker **Full Disk Access** in *System Settings → Privacy &
Security*, or keep the project outside those folders.

**Code changes are not showing up in the container**
The image bakes in the source, so rebuild it:
`docker compose up -d --build web`. For hot reload, run `docker compose up -d db`
and start the app locally with `uvicorn app.main:app --reload`.

**Port 5432 or 8000 is already in use**
Another container or a local PostgreSQL is bound to it. Check with `docker ps`
and stop the conflicting container, e.g. `docker rm -f m14_pg`.

**`psycopg2.OperationalError: connection refused`**
PostgreSQL is not running or is on a different port. Check with `docker ps` and
confirm `DATABASE_URL` matches.

**`MissingBackendError: bcrypt: no backends available`**
Dependencies are out of date. Re-run `pip install -r requirements.txt`.

**Playwright tests fail with a missing-executable error**
The browser was never downloaded. Run `playwright install chromium`.

**Dependency installation fails to build wheels**
Use Python 3.10–3.12. Newer versions may lack prebuilt wheels for the pinned
dependency versions.
