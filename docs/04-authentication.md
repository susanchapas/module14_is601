# Module 4: Authentication with JWT

## Introduction

In this module, we'll implement user authentication using JSON Web Tokens (JWT). JWT is a compact, URL-safe means of representing claims to be transferred between two parties. In our application, we'll use JWTs to authenticate users and secure API endpoints.

## Objectives

- Understand the JWT authentication flow
- Implement password hashing
- Create JWT token generation and verification
- Implement protected routes with dependencies
- Add token-based authentication to our API

## Understanding JWT Authentication

JWT authentication follows these general steps:

1. User provides credentials (username/password)
2. Server validates credentials
3. Server generates a JWT token and returns it to the client
4. Client includes the token in subsequent requests in an Authorization header
5. Server validates the token and grants access if valid

JWTs consist of three parts:
- Header: Contains the token type and algorithm
- Payload: Contains claims (user information, expiration time, etc.)
- Signature: Used to verify the token hasn't been tampered with

## Implementing Password Hashing

First, let's create a module for password hashing in `app/auth/jwt.py`:

```python
from datetime import datetime, timedelta, timezone
from passlib.context import CryptContext
from jose import jwt
from uuid import UUID

from app.core.config import get_settings
from app.schemas.token import TokenType

settings = get_settings()

# Set up password hashing with bcrypt
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plain-text password against a hashed password.
    
    Args:
        plain_password: The plain-text password to verify
        hashed_password: The hashed password to compare against
        
    Returns:
        bool: True if passwords match, False otherwise
    """
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """
    Hash a plain-text password using bcrypt.
    
    Args:
        password: The plain-text password to hash
        
    Returns:
        str: The hashed password
    """
    return pwd_context.hash(password)

def create_token(subject: str, token_type: TokenType) -> str:
    """
    Create a JWT token with the given subject and type.
    
    Args:
        subject: The subject of the token (usually user ID)
        token_type: The type of token (access or refresh)
        
    Returns:
        str: JWT token
    """
    if token_type == TokenType.ACCESS:
        expire_minutes = settings.ACCESS_TOKEN_EXPIRE_MINUTES
    else:  # TokenType.REFRESH
        expire_minutes = settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60
        
    expire = datetime.now(timezone.utc) + timedelta(minutes=expire_minutes)
    
    to_encode = {
        "sub": subject,
        "exp": expire,
        "type": token_type
    }
    
    encoded_jwt = jwt.encode(
        to_encode, 
        settings.JWT_SECRET_KEY, 
        algorithm=settings.ALGORITHM
    )
    
    return encoded_jwt
```

## Creating Authentication Dependencies

`app/auth/dependencies.py` provides three dependencies, layered so that each
endpoint pays only for what it needs. Note that they are plain `def`, not
`async def`: they do blocking database work, so FastAPI should run them in its
threadpool rather than on the event loop.

```python
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.datetime_utils import utcnow
from app.database import get_db
from app.models.user import User
from app.schemas.user import UserResponse

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token")

def get_current_user(token: str = Depends(oauth2_scheme)) -> UserResponse:
    """
    Get the current user from the JWT token, without a database lookup.

    User.verify_token yields only the subject UUID, so every field other than
    the id is a placeholder.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    user_id = User.verify_token(token)
    if user_id is None:
        raise credentials_exception

    now = utcnow()
    return UserResponse(
        id=user_id,
        username="unknown",
        email="unknown@example.com",
        first_name="Unknown",
        last_name="User",
        is_active=True,
        is_verified=False,
        created_at=now,
        updated_at=now,
    )

def get_current_active_user(
    current_user: UserResponse = Depends(get_current_user)
) -> UserResponse:
    """Ensure the current user is active."""
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )
    return current_user

def get_current_user_record(
    current_user: UserResponse = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> User:
    """Load the current user's database record."""
    user = db.query(User).filter(User.id == current_user.id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    return user
```

### Which dependency should an endpoint use?

This is the part that most often goes wrong, so it is worth being explicit.

| Dependency | Hits the database? | Returns | Use it when |
|---|---|---|---|
| `get_current_user` | No | `UserResponse` with **placeholder fields** | You only need the caller's `id` |
| `get_current_active_user` | No | Same, after an `is_active` check | You only need the id, and want inactive users rejected |
| `get_current_user_record` | Yes | The real `User` row | You need to read or write any stored profile field |

> **Trap.** `get_current_user` never queries the database. It reconstructs a
> `UserResponse` from the token's subject claim alone, so `username`, `email`
> and the rest are literal placeholders (`"unknown"`, `"Unknown"`). They are
> there to satisfy the response model, not to be read. An endpoint that returns
> profile data must depend on `get_current_user_record`, or it will serve
> `"unknown@example.com"` to every caller.

Token decoding itself is not duplicated here: it lives in `User.verify_token`,
which is the single place that knows which secret goes with which token type.

## Implementing Authentication Endpoints

Now, let's implement the authentication endpoints in `app/main.py`:

```python
# User Registration Endpoint
@app.post(
    "/auth/register", 
    response_model=UserResponse, 
    status_code=status.HTTP_201_CREATED,
    tags=["auth"]
)
def register(user_create: UserCreate, db: Session = Depends(get_db)):
    """
    Create a new user account.
    """
    user_data = user_create.model_dump(exclude={"confirm_password"})
    try:
        user = User.register(db, user_data)
        db.commit()
        db.refresh(user)
        return user
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


# User Login Endpoints
@app.post("/auth/login", response_model=TokenResponse, tags=["auth"])
def login_json(user_login: UserLogin, db: Session = Depends(get_db)):
    """
    Login with JSON payload (username & password).
    Returns an access token, refresh token, and user info.
    """
    auth_result = User.authenticate(db, user_login.username, user_login.password)
    if auth_result is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = auth_result["user"]

    return TokenResponse(
        access_token=auth_result["access_token"],
        refresh_token=auth_result["refresh_token"],
        token_type="bearer",
        expires_at=auth_result["expires_at"],
        user_id=user.id,
        username=user.username,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        is_active=user.is_active,
        is_verified=user.is_verified
    )

@app.post("/auth/token", tags=["auth"])
def login_form(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """
    Login with form data (Swagger/UI).
    Returns an access token.
    """
    auth_result = User.authenticate(db, form_data.username, form_data.password)
    if auth_result is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return {
        "access_token": auth_result["access_token"],
        "token_type": "bearer"
    }
```

### Two things worth noticing

**The route does not recompute `expires_at`.** It passes
`auth_result["expires_at"]` straight through. `User.authenticate` derives that
value from `ACCESS_TOKEN_EXPIRE_MINUTES` and returns it already timezone-aware,
so there is exactly one place that decides how long a token lives.

An earlier version of this route tried to "normalize" the value instead:

```python
# Don't do this.
expires_at = auth_result.get("expires_at")
if expires_at and expires_at.tzinfo is None:
    expires_at = expires_at.replace(tzinfo=timezone.utc)
else:
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)
```

Because `authenticate` already returned an aware datetime, the `if` never fired
and the `else` silently overwrote the real expiry with a hardcoded 15 minutes.
Clients were told their 30-minute token expired in 15, and logged out halfway
through its life. Deriving a value in two places is how the two places come to
disagree.

**Neither route commits.** `User.authenticate` updates `last_login` and commits
it itself, so both login routes behave identically. When only `login_json`
committed, a `/auth/token` login left `last_login` as `NULL`, because
`get_db()` closed the session and rolled the write back.

## Refreshing an Access Token

Access tokens are deliberately short-lived. `POST /auth/refresh` lets a client
that still holds a valid refresh token get a new access token without asking
for the password again:

```python
@app.post("/auth/refresh", response_model=AccessTokenResponse, tags=["auth"])
def refresh_access_token(refresh_request: RefreshRequest, db: Session = Depends(get_db)):
    """
    Exchange a refresh token for a new access token.
    """
    invalid_token = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid refresh token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    user_id = User.verify_token(refresh_request.refresh_token, TokenType.REFRESH)
    if user_id is None:
        raise invalid_token

    user = db.query(User).filter(User.id == user_id).first()
    if user is None or not user.is_active:
        raise invalid_token
    ...
```

Two details matter here. The token is verified with
`TokenType.REFRESH`, so an *access* token cannot be replayed against this
endpoint — the two token types are signed with different secrets. And the
refresh token is not reissued; when it expires, the user logs in again.

> If you are following an older version of this guide: the refresh token used
> to be issued at login and stored in `localStorage` with no endpoint that
> accepted it. Storing a credential the API will not honour is strictly worse
> than not issuing one, so the endpoint above was added to make it real.

## Implementing User Authentication Methods

Let's add the authentication methods to our User model:

```python
@classmethod
def register(cls, db, user_data: dict):
    """
    Register a new user.

    Args:
        db: SQLAlchemy database session
        user_data: Dictionary containing user registration data
        
    Returns:
        User: The newly created user instance
        
    Raises:
        ValueError: If password is invalid or username/email already exists
    """
    password = user_data.get("password")
    if not password or len(password) < 6:
        raise ValueError("Password must be at least 6 characters long")
    
    # Check for duplicate email or username
    existing_user = db.query(cls).filter(
        or_(cls.email == user_data["email"], cls.username == user_data["username"])
    ).first()
    if existing_user:
        raise ValueError("Username or email already exists")
    
    # Create new user instance
    hashed_password = cls.hash_password(password)
    user = cls(
        first_name=user_data["first_name"],
        last_name=user_data["last_name"],
        email=user_data["email"],
        username=user_data["username"],
        password=hashed_password,
        is_active=True,
        is_verified=False
    )
    db.add(user)
    return user

@classmethod
def authenticate(cls, db, username_or_email: str, password: str):
    """
    Authenticate a user by username/email and password.

    Args:
        db: SQLAlchemy database session
        username_or_email: Username or email to authenticate
        password: Password to verify

    The updated last_login is committed here so that every caller persists
    it, whatever route it came from.

    Returns:
        dict: Authentication result with tokens and user data, or None if authentication fails
    """
    user = db.query(cls).filter(
        or_(cls.username == username_or_email, cls.email == username_or_email)
    ).first()

    if not user or not user.verify_password(password):
        return None

    # Update the last_login timestamp
    user.last_login = utcnow()
    db.commit()

    return {
        **cls.issue_access_token(user),
        "refresh_token": cls.create_refresh_token({"sub": str(user.id)}),
        "user": user
    }

@classmethod
def issue_access_token(cls, user) -> dict:
    """
    Mint an access token for a user and report when it expires.

    Shared by /auth/login and /auth/refresh so that both report the same
    lifetime, derived from ACCESS_TOKEN_EXPIRE_MINUTES.
    """
    return {
        "access_token": cls.create_access_token({"sub": str(user.id)}),
        "token_type": "bearer",
        "expires_at": utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    }
```

Two deliberate choices here:

- **`db.commit()`, not `db.flush()`.** A flush sends the `UPDATE` to the
  database but leaves it inside the open transaction. `get_db()` closes the
  session when the request ends, which rolls that transaction back, so a
  flushed `last_login` was silently discarded for any route that did not commit
  on its own. Committing in `authenticate` means every caller behaves the same.
- **`issue_access_token` is shared.** Both `/auth/login` and `/auth/refresh`
  mint tokens through it, so a change to the token lifetime takes effect in
  both places at once.

## Protecting API Routes

Now we can protect our API routes using the dependencies we created. Here's an example with the calculations endpoints:

```python
@app.post(
    "/calculations",
    response_model=CalculationResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["calculations"],
)
def create_calculation(
    calculation_data: CalculationBase,
    current_user = Depends(get_current_active_user),  # Protected route
    db: Session = Depends(get_db)
):
    """
    Create a new calculation for the authenticated user.
    Automatically computes the 'result'.
    """
    try:
        new_calculation = Calculation.create(
            calculation_type=calculation_data.type,
            user_id=current_user.id,  # Use current user's ID
            inputs=calculation_data.inputs,
        )
        new_calculation.result = new_calculation.get_result()

        db.add(new_calculation)
        db.commit()
        db.refresh(new_calculation)
        return new_calculation

    except ValueError as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
```

## JWT Security Considerations

When implementing JWT authentication, keep these security considerations in mind:

1. **Secret Key**: Use a strong, unique secret key for signing JWTs
2. **Token Expiration**: Set appropriate expiration times for tokens
3. **HTTPS**: Always use HTTPS in production to protect tokens in transit
4. **Token Storage**: Advise clients to store tokens securely (e.g., HttpOnly cookies)
5. **Token Revocation**: Consider implementing a token blacklist for logout/revocation
6. **Claims**: Include only necessary information in the token payload

## Next Steps

In the next module, we'll implement the API endpoints for our calculator application using the authentication we've set up.

## Additional Resources

- [JSON Web Tokens (JWT)](https://jwt.io/)
- [FastAPI Security Documentation](https://fastapi.tiangolo.com/tutorial/security/)
- [Passlib Documentation](https://passlib.readthedocs.io/en/stable/)
- [Python-JOSE Documentation](https://python-jose.readthedocs.io/en/latest/)