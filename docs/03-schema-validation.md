# Module 3: Schema Validation with Pydantic

## Introduction

In this module, we'll learn about schema validation using Pydantic. Pydantic is a data validation and settings management library using Python type annotations. It ensures that the data received by our API endpoints and sent in responses is valid according to our specifications.

## Objectives

- Understand the importance of data validation
- Create Pydantic models for request and response validation
- Learn about schema inheritance and composition
- Implement validation for our API endpoints

## Why Data Validation Matters

Data validation is crucial in API development for several reasons:

1. **Security**: Preventing malicious input that could lead to security vulnerabilities
2. **Data Integrity**: Ensuring that the data stored in our database is valid and consistent
3. **Documentation**: Automatically generating API documentation through OpenAPI
4. **Type Safety**: Leveraging Python's type system for better code quality and IDE support
5. **Error Handling**: Providing meaningful error messages to clients when validation fails

## Where the Schemas Live

The application keeps one schema module per resource, and every model derives
directly from Pydantic's `BaseModel`:

| Module | Contents |
|---|---|
| `app/schemas/user.py` | `UserBase`, `UserCreate`, `UserResponse`, `UserLogin`, `UserUpdate`, `PasswordUpdate` |
| `app/schemas/calculation.py` | `CalculationType`, `CalculationBase`, `CalculationUpdate`, `CalculationReplace`, `CalculationStats`, `CalculationResponse` |
| `app/schemas/token.py` | `TokenType`, `RefreshRequest`, `AccessTokenResponse`, `TokenResponse` |

There is no shared `BaseSchema` class. An earlier version of this project had a
second `app/schemas/base.py` that redeclared `UserBase`/`UserCreate` with a
*weaker* password policy than `app/schemas/user.py`, which meant two competing
sources of truth for the same rules. It was removed. Shared configuration is
expressed per-model with `model_config = ConfigDict(...)` instead:

```python
from pydantic import BaseModel, ConfigDict

class Example(BaseModel):
    # from_attributes lets a model be built straight from a SQLAlchemy row
    model_config = ConfigDict(from_attributes=True)
```

> **Pydantic v2 note.** This project uses Pydantic v2. The v1 spellings you may
> find in older tutorials have all been replaced: `class Config` is now
> `model_config = ConfigDict(...)`, `orm_mode` is now `from_attributes`,
> `@validator`/`@root_validator` are now `@field_validator`/`@model_validator`,
> and `.dict()` is now `.model_dump()`.

## User Schemas

`app/schemas/user.py` validates registration, login, profile edits and password
changes. The password policy lives in one shared function so that registration
and password-change both enforce exactly the same rules:

```python
# app/schemas/user.py
SPECIAL_CHARACTERS = "!@#$%^&*()_+-=[]{}|;:,.<>?"

def validate_password_strength(password: str) -> str:
    """Check a plain-text password against the application's strength rules."""
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters long")
    if not any(char.isupper() for char in password):
        raise ValueError("Password must contain at least one uppercase letter")
    if not any(char.islower() for char in password):
        raise ValueError("Password must contain at least one lowercase letter")
    if not any(char.isdigit() for char in password):
        raise ValueError("Password must contain at least one digit")
    if not any(char in SPECIAL_CHARACTERS for char in password):
        raise ValueError("Password must contain at least one special character")
    return password

class UserBase(BaseModel):
    """Base user schema with common fields"""
    first_name: str = Field(min_length=1, max_length=50, examples=["John"])
    last_name: str = Field(min_length=1, max_length=50, examples=["Doe"])
    email: EmailStr = Field(examples=["john.doe@example.com"])
    username: str = Field(min_length=3, max_length=50, examples=["johndoe"])

    model_config = ConfigDict(from_attributes=True)

class UserCreate(UserBase):
    """Schema for user creation with password validation"""
    password: str = Field(min_length=8, max_length=128, examples=["SecurePass123!"])
    confirm_password: str = Field(min_length=8, max_length=128, examples=["SecurePass123!"])

    @model_validator(mode="after")
    def verify_password_match(self) -> "UserCreate":
        if self.password != self.confirm_password:
            raise ValueError("Passwords do not match")
        return self

    @model_validator(mode="after")
    def validate_password_strength(self) -> "UserCreate":
        validate_password_strength(self.password)
        return self
```

Note `examples=[...]` rather than the older `example=...`. `example=` was an
extra keyword that Pydantic v2 deprecates; `examples` is a real JSON Schema
keyword and takes a *list* of sample values.

`UserResponse` is the read model. It deliberately omits `password` and
`hashed_password`, so a password hash cannot leak through a response:

```python
class UserResponse(BaseModel):
    """Schema for user response data"""
    id: UUID
    username: str
    email: EmailStr
    first_name: str
    last_name: str
    is_active: bool
    is_verified: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
```

## Calculation Schemas

`app/schemas/calculation.py` uses a `str`-based `Enum` for the operation, so
only the four supported types can ever reach the model layer:

```python
# app/schemas/calculation.py
class CalculationType(str, Enum):
    ADDITION = "addition"
    SUBTRACTION = "subtraction"
    MULTIPLICATION = "multiplication"
    DIVISION = "division"

class CalculationBase(BaseModel):
    type: CalculationType = Field(
        ...,
        description="Type of calculation (addition, subtraction, multiplication, division)",
        examples=["addition"]
    )
    inputs: List[float] = Field(
        ...,
        description="List of numeric inputs for the calculation",
        examples=[[10.5, 3, 2]],
        min_length=2
    )

    @model_validator(mode="after")
    def validate_inputs(self) -> "CalculationBase":
        if len(self.inputs) < 2:
            raise ValueError("At least two numbers are required for calculation")
        if self.type == CalculationType.DIVISION:
            # Skip the first value: it is the numerator, and may be zero
            if any(x == 0 for x in self.inputs[1:]):
                raise ValueError("Cannot divide by zero")
        return self
```

`min_length=2` is the list-length constraint. Pydantic v1 spelled this
`min_items`; that name is deprecated in v2 and `min_length` covers both strings
and sequences.

### Update vs. replace

`PATCH` and `PUT` take different schemas, which is what gives them different
semantics:

```python
class CalculationUpdate(BaseModel):
    """PATCH: inputs may be omitted, and an empty body is a no-op."""
    inputs: Optional[List[float]] = Field(None, min_length=2)

class CalculationReplace(CalculationUpdate):
    """PUT: replaces the whole resource, so inputs must be stated."""
    inputs: List[float] = Field(..., min_length=2)
```

### The response schema

```python
class CalculationResponse(CalculationBase):
    id: UUID
    user_id: UUID
    created_at: datetime
    updated_at: datetime
    result: Optional[float] = Field(
        None,
        description="Result of the calculation, or null if it has not been computed yet"
    )
```

`result` is `Optional[float]`, not `float`. The `result` column is nullable, so
a required `float` here made every response containing an uncomputed row fail
serialization and return HTTP 500. **The schema and the column must always
agree on nullability** — this is a common and easy mistake to make.

## Token Schemas

`app/schemas/token.py` holds three response/request models plus the token-type
enum. `TokenResponse` is returned by login, `AccessTokenResponse` by the
refresh endpoint, and `RefreshRequest` is what the client posts to refresh:

```python
# app/schemas/token.py
class TokenType(str, Enum):
    ACCESS = "access"
    REFRESH = "refresh"

class RefreshRequest(BaseModel):
    """Schema for exchanging a refresh token for a new access token."""
    refresh_token: str = Field(..., description="JWT refresh token issued at login")

class AccessTokenResponse(BaseModel):
    """Schema for a freshly minted access token."""
    access_token: str
    token_type: str = Field(default="bearer")
    expires_at: datetime

class TokenResponse(BaseModel):
    """Schema for complete token response including user data."""
    access_token: str
    refresh_token: str
    token_type: str = Field(default="bearer")
    expires_at: datetime
    user_id: UUID
    username: str
    email: str
    first_name: str
    last_name: str
    is_active: bool
    is_verified: bool

    model_config = ConfigDict(from_attributes=True)
```

`expires_at` is derived from `ACCESS_TOKEN_EXPIRE_MINUTES` in a single place
(`User.authenticate`) and passed through unchanged by the route. Computing it a
second time in the route is how it once came to disagree with the configured
value.

## Using Schemas in API Endpoints

Now that we have our schemas defined, we can use them in our API endpoints to validate requests and responses:

```python
@app.post(
    "/auth/register", 
    response_model=UserResponse,  # Validates the response
    status_code=status.HTTP_201_CREATED,
    tags=["auth"]
)
def register(
    user_create: UserCreate,  # Validates the request body
    db: Session = Depends(get_db)
):
    """Create a new user account."""
    user_data = user_create.model_dump(exclude={"confirm_password"})
    try:
        user = User.register(db, user_data)
        db.commit()
        db.refresh(user)
        return user
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
```

## Benefits of Using Pydantic

1. **Automatic Validation**: Pydantic automatically validates request data
2. **Meaningful Error Messages**: Clear error messages when validation fails
3. **Documentation**: Generates OpenAPI schema for API documentation
4. **Type Hints**: Provides type information to your IDE
5. **Conversion**: Handles conversion between types (e.g., string to datetime)

## Best Practices

1. **Separate Schemas**: Create different schemas for different operations (create, update, response)
2. **Schema Inheritance**: Use inheritance to avoid duplicating code
3. **Validation Methods**: Use Pydantic validators for complex validation logic
4. **Documentation**: Add field descriptions for better API documentation
5. **Config Options**: Use Pydantic Config for fine-grained control

## Next Steps

In the next module, we'll implement the authentication system using JWT tokens and implement security best practices.

## Additional Resources

- [Pydantic Documentation](https://pydantic-docs.helpmanual.io/)
- [FastAPI Schema Documentation](https://fastapi.tiangolo.com/tutorial/schema/)
- [Pydantic Field Types](https://pydantic-docs.helpmanual.io/usage/types/)