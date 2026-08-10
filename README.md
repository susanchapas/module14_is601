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
- [Security](#security)
- [Docker](#docker)
- [CI/CD Pipeline](#cicd-pipeline)
- [Configuration](#configuration)
- [Beyond the Requirements](#beyond-the-requirements)
- [Troubleshooting](#troubleshooting)
- [Reflection](#reflection)

---

## Features

- **BREAD endpoints** for calculations, scoped to the authenticated user
- Four operation types: `addition`, `subtraction`, `multiplication`, `division`
- JWT authentication (register, login, bearer-token protected routes)
- User profile page: view and edit account details, change password
- Calculation history summary: totals, average operand count, per-type breakdown
- Server-rendered UI with forms for every BREAD operation
- Shared client-side validation (numeric checks, operation types, divide-by-zero)
- 283 automated tests: unit, integration, API end-to-end, and Playwright browser tests

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
| `POST /auth/refresh`  | Exchange a refresh token for a new access token |
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

## Security

| Measure | Where | Detail |
| ------- | ----- | ------ |
| **Password hashing** | [`app/auth/jwt.py`](app/auth/jwt.py) | bcrypt via passlib, cost factor `BCRYPT_ROUNDS` (default 12). Plaintext passwords are never stored or logged. |
| **Password policy** | [`app/schemas/user.py`](app/schemas/user.py) | Minimum 8 characters, and at least one uppercase, one lowercase, one digit, and one special character. Enforced by one shared validator, so registration and password-change cannot drift apart. |
| **JWT authentication** | [`app/auth/dependencies.py`](app/auth/dependencies.py) | Short-lived access tokens (30 min) plus longer refresh tokens (7 days), signed with **separate** secrets so a leaked access-token key cannot mint refresh tokens. Token type is verified on decode, so a refresh token is rejected where an access token is required. |
| **No default secrets** | [`app/core/config.py`](app/core/config.py) | `JWT_SECRET_KEY` and `JWT_REFRESH_SECRET_KEY` have no defaults. A missing value fails at startup instead of silently signing tokens with a value published in this repository. |
| **Ownership scoping** | [`app/main.py`](app/main.py) | Every calculation query filters on `user_id == current_user.id`. Requesting another user's calculation returns **404**, not 403, so the API does not confirm that the record exists. |
| **Input validation** | Pydantic v2 schemas | Types, operand counts, and divide-by-zero are rejected at the schema boundary with 422 before any database or arithmetic work happens. Validation is server-side; the client-side checks are a convenience, not the control. |
| **SQL injection** | SQLAlchemy ORM | All access goes through the ORM's parameterized queries. No string-built SQL anywhere in `app/`. |
| **Container hardening** | [`Dockerfile`](Dockerfile) | Runs as a non-root `appuser` on a slim base image, with a `HEALTHCHECK` against `/health`. |
| **Dependency scanning** | [CI](.github/workflows/test.yml) | Trivy scans the built image on every push and **fails the build** on `CRITICAL` or `HIGH` vulnerabilities. |
| **Secret hygiene** | `.gitignore` | `.env` is never committed. [`.env.example`](.env.example) documents every variable with placeholder values only. |

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

## Beyond the Requirements

The base assignment is BREAD + JWT + tests + CI/CD. These went past it:

**Application**

- **`GET /calculations/stats`** — a history summary endpoint (totals, average operand count, per-type breakdown), surfaced as a live card on the dashboard. Registered *before* `/calculations/{calc_id}` so the router matches `stats` as a literal rather than as a malformed UUID.
- **`POST /auth/refresh`** — access tokens expire in 30 minutes; this exchanges a still-valid refresh token for a new access token so the user is not logged out mid-session.
- **Full profile management** — view and edit account details, plus a password change that requires the current password.
- **Live result preview** on the edit page: the computed result updates as inputs are typed, before anything is submitted.

**Engineering**

- **Ruff in CI**, gating the build before tests run. It is what caught the duplicate imports and several unused ones during cleanup.
- **Deprecation warnings are errors** (`error::DeprecationWarning` in `pytest.ini`). Third-party noise gets narrow, specific ignores rather than one blanket suppression, so the project's own deprecated calls cannot hide.
- **Trivy image scanning** that fails the pipeline on `CRITICAL`/`HIGH` findings, and a **multi-arch** (`linux/amd64` + `linux/arm64`) image published to Docker Hub.
- **A test database that cannot eat production data** — `conftest.py` refuses to start if `TEST_DATABASE_URL` and `DATABASE_URL` name the same database, because the suite drops every table in it.
- **Custom pytest flags** — `--preserve-db` keeps test data for post-mortem inspection, `--run-slow` opts into the expensive tests that are skipped by default.
- **`Dockerfile.postgres`** bakes `init-db.sh` into the database image, so the test database is created automatically and the stack needs **no host bind mounts** — which is what makes it work unmodified on macOS, where Docker cannot mount from `~/Desktop`.

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

---

## Reflection

### A green test suite is not the same as working code

The most useful thing I did on this project was stop adding features and audit
what I had already written. The suite was green and coverage was 84%, which felt
like evidence that the application worked. It was not. Reading the code against a
live client turned up four real defects that every test had passed straight over:

| Bug | What was actually wrong |
| --- | --- |
| Token expiry | The route recomputed `expires_at` as `now + 15min` instead of using the configured value, so clients were told their 30-minute token lasted 15. |
| Missing commit | `POST /auth/token` flushed the `last_login` update but never committed it, so the write was rolled back when the session closed. |
| `PATCH` no-op | An empty body still bumped `updated_at` and committed, contradicting the endpoint's own docstring. |
| Nullable mismatch | The `result` column was `nullable=True` but the response schema required a `float`. One NULL row would have turned `GET /calculations` into an HTTP 500. |

The pattern connecting all four is that my tests asserted status codes and
response shapes. Every one of these bugs produces a 200 with a well-formed body.
The expiry bug returns a perfectly valid number — just the wrong one. I now think
of a test that only checks the status code as barely a test at all; the assertion
has to name the value I actually care about.

### The worst thing I found was a passing test

`test_dependencies.py` mocked `verify_token` to return a dictionary and then
asserted on how the code handled that dictionary. But `verify_token` only ever
returns a `UUID` or `None`. The branch under test could not execute in
production, and the mock was the only reason it looked covered. Meanwhile the
real `UUID` path had no test at all.

That inverted my understanding of what mocks cost. The mock had quietly become
the specification, and because it disagreed with the real function, the test was
protecting dead code while leaving live code exposed. Coverage counted those
lines as green, which made the number actively misleading. Now I check that a
mock's return type matches the real function's signature before I trust anything
built on it.

### Deleting code was the highest-value work

Roughly 200 lines had no caller: an entire `redis.py` module, a `decode_token`
helper nothing imported, orphaned schemas, and a `refresh_token` the front end
dutifully stored in `localStorage` with no endpoint that would accept it. The
last one was the clearest lesson — an unusable credential sitting in browser
storage is strictly worse than not issuing one, because it is pure attack surface
with zero benefit. I resolved it by building the `/auth/refresh` endpoint that
should have existed from the start.

I also found two competing password policies. `schemas/base.py` and
`schemas/user.py` both defined `UserCreate`, and only the second required a
special character. Nothing but a test imported the weaker one, but having two
"sources of truth" for a security rule is exactly how the wrong one eventually
gets wired up. Duplication is not just extra lines to maintain; when the copies
disagree about something that matters, it is a latent vulnerability.

### What I would do differently

- **Write the shared helper first.** I ended up with ~1,450 lines of inline
  `<script>` across eight templates, including eleven near-identical
  `fetch` + bearer-token + redirect-on-401 blocks. Extracting `apiFetch` into
  `script.js` afterwards was mechanical but tedious, and it would have cost
  nothing on day one. Copy-paste felt faster each individual time and was much
  slower in aggregate.
- **Turn on the linter and the warning filters at the start.** `pytest.ini` was
  suppressing every `DeprecationWarning`, which hid a pile of Pydantic v1 calls
  and deprecated `datetime.utcnow()` usage. Both tools took one config file each
  and immediately found real problems. Adding them at the end meant fixing a
  backlog instead of never creating one.
- **Pick timezone-aware datetimes once and never mix.** `User` used aware
  datetimes and `Calculation` used naive ones. That inconsistency is the root
  cause of the token-expiry bug: a `tzinfo is None` guard that could never fire
  sent every request down the wrong branch. Two conventions in one codebase means
  every comparison between them is a bug waiting for the right input.
- **Have CI report one honest number.** The pipeline ran `pytest` three times
  with `--cov=app`, so each pass overwrote the last and only the e2e coverage
  survived. The reported figure was not wrong so much as meaningless — a metric
  nobody had checked the provenance of.

### Where it ended up

283 tests, 89% coverage, a clean `ruff` run, and no deprecation warnings from
first-party code. The number I trust most is not the coverage percentage, though,
but the fact that the four regression tests written for the bugs above fail
loudly if anyone reintroduces them. Coverage says which lines ran. Only an
assertion about a specific value says the line was *right*.
