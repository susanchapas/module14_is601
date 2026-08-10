"""
FastAPI Main Application Module

This module defines the main FastAPI application, including:
- Application initialization and configuration
- API endpoints for user authentication
- API endpoints for calculation management (BREAD operations)
- Web routes for HTML templates
- Database table creation on startup

The application follows a RESTful API design with proper separation of concerns:
- Routes handle HTTP requests and responses
- Models define database structure
- Schemas validate request/response data
- Dependencies handle authentication and database sessions
"""

from contextlib import asynccontextmanager  # Used for startup/shutdown events
from uuid import UUID  # For type validation of UUIDs in path parameters
from typing import List

# FastAPI imports
from fastapi import Body, FastAPI, Depends, HTTPException, status, Request, Form
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles  # For serving static files (CSS, JS)
from fastapi.templating import Jinja2Templates  # For HTML templates

from sqlalchemy.orm import Session  # SQLAlchemy database session

import uvicorn  # ASGI server for running FastAPI apps

# Application imports
from app.auth.dependencies import get_current_active_user, get_current_user_record  # Authentication dependencies
from app.models.calculation import Calculation  # Database model for calculations
from app.models.user import User  # Database model for users
from app.schemas.calculation import CalculationBase, CalculationReplace, CalculationResponse, CalculationStats, CalculationUpdate  # API request/response schemas
from app.schemas.token import AccessTokenResponse, RefreshRequest, TokenResponse, TokenType  # API token schemas
from app.schemas.user import UserCreate, UserResponse, UserLogin, UserUpdate, PasswordUpdate  # User schemas
from app.database import Base, get_db, engine  # Database connection


# ------------------------------------------------------------------------------
# Create tables on startup using the lifespan event
# ------------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for FastAPI.
    
    This runs when the application starts and creates all database tables
    defined in SQLAlchemy models. It's an alternative to using Alembic
    for simpler applications.
    
    Args:
        app: FastAPI application instance
    """
    print("Creating tables...")
    Base.metadata.create_all(bind=engine)
    print("Tables created successfully!")
    yield  # This is where application runs
    # Cleanup code would go here (after yield), but we don't need any

# Initialize the FastAPI application with metadata and lifespan
app = FastAPI(
    title="Calculations API",
    description="API for managing calculations",
    version="1.0.0",
    lifespan=lifespan  # Pass our lifespan context manager
)

# ------------------------------------------------------------------------------
# Static Files and Templates Configuration
# ------------------------------------------------------------------------------
# Mount the static files directory for serving CSS, JS, and images
app.mount("/static", StaticFiles(directory="static"), name="static")

# Set up Jinja2 templates directory for HTML rendering
templates = Jinja2Templates(directory="templates")


# ------------------------------------------------------------------------------
# Web (HTML) Routes
# ------------------------------------------------------------------------------
# Our web routes use HTML responses with Jinja2 templates
# These provide a user-friendly web interface alongside the API

@app.get("/", response_class=HTMLResponse, tags=["web"])
def read_index(request: Request):
    """
    Landing page.
    
    Displays the welcome page with links to register and login.
    """
    return templates.TemplateResponse(request, "index.html")

@app.get("/login", response_class=HTMLResponse, tags=["web"])
def login_page(request: Request):
    """
    Login page.
    
    Displays a form for users to enter credentials and log in.
    """
    return templates.TemplateResponse(request, "login.html")

@app.get("/register", response_class=HTMLResponse, tags=["web"])
def register_page(request: Request):
    """
    Registration page.
    
    Displays a form for new users to create an account.
    """
    return templates.TemplateResponse(request, "register.html")

@app.get("/dashboard", response_class=HTMLResponse, tags=["web"])
def dashboard_page(request: Request):
    """
    Dashboard page, listing calculations & new calculation form.
    
    This is the main interface after login, where users can:
    - See all their calculations
    - Create a new calculation
    - Access links to view/edit/delete calculations
    
    JavaScript in this page calls the API endpoints to fetch and display data.
    """
    return templates.TemplateResponse(request, "dashboard.html")

@app.get("/profile", response_class=HTMLResponse, tags=["web"])
def profile_page(request: Request):
    """
    Profile page, for editing account details and changing the password.

    JavaScript in this page calls the /users/me endpoints to load and save data.
    """
    return templates.TemplateResponse(request, "profile.html")

@app.get("/dashboard/view/{calc_id}", response_class=HTMLResponse, tags=["web"])
def view_calculation_page(request: Request, calc_id: str):
    """
    Page for viewing a single calculation (Read).
    
    Part of the BREAD (Browse, Read, Edit, Add, Delete) pattern:
    - This is the Read page
    
    Args:
        request: The FastAPI request object (required by Jinja2)
        calc_id: UUID of the calculation to view
        
    Returns:
        HTMLResponse: Rendered template with calculation ID passed to frontend
    """
    return templates.TemplateResponse(request, "view_calculation.html", {"calc_id": calc_id})

@app.get("/dashboard/edit/{calc_id}", response_class=HTMLResponse, tags=["web"])
def edit_calculation_page(request: Request, calc_id: str):
    """
    Page for editing a calculation (Update).
    
    Part of the BREAD (Browse, Read, Edit, Add, Delete) pattern:
    - This is the Edit page
    
    Args:
        request: The FastAPI request object (required by Jinja2)
        calc_id: UUID of the calculation to edit
        
    Returns:
        HTMLResponse: Rendered template with calculation ID passed to frontend
    """
    return templates.TemplateResponse(request, "edit_calculation.html", {"calc_id": calc_id})


# ------------------------------------------------------------------------------
# Health Endpoint
# ------------------------------------------------------------------------------
@app.get("/health", tags=["health"])
def read_health():
    """Health check."""
    return {"status": "ok"}


# ------------------------------------------------------------------------------
# User Registration Endpoint
# ------------------------------------------------------------------------------
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
    user_data = user_create.dict(exclude={"confirm_password"})
    try:
        user = User.register(db, user_data)
        db.commit()
        db.refresh(user)
        return user
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ------------------------------------------------------------------------------
# User Login Endpoints
# ------------------------------------------------------------------------------
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


@app.post("/auth/refresh", response_model=AccessTokenResponse, tags=["auth"])
def refresh_access_token(refresh_request: RefreshRequest, db: Session = Depends(get_db)):
    """
    Exchange a refresh token for a new access token.

    Access tokens are short-lived, so a client that still holds a valid refresh
    token can stay signed in without asking for the password again. The refresh
    token itself is not reissued; when it expires the user must log in.
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

    return AccessTokenResponse(**User.issue_access_token(user))


# ------------------------------------------------------------------------------
# User Profile Endpoints
# ------------------------------------------------------------------------------
@app.get("/users/me", response_model=UserResponse, tags=["users"])
def read_profile(current_user: User = Depends(get_current_user_record)):
    """
    Return the authenticated user's stored profile.
    """
    return current_user


@app.put("/users/me", response_model=UserResponse, tags=["users"])
def update_profile(
    user_update: UserUpdate,
    current_user: User = Depends(get_current_user_record),
    db: Session = Depends(get_db)
):
    """
    Update the authenticated user's profile (username, email, first/last name).

    Only the fields present in the request body are changed.
    """
    try:
        current_user.update_profile(db, **user_update.model_dump(exclude_none=True))
        db.commit()
        db.refresh(current_user)
        return current_user
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/users/me/password", tags=["users"])
def change_password(
    password_update: PasswordUpdate,
    current_user: User = Depends(get_current_user_record),
    db: Session = Depends(get_db)
):
    """
    Change the authenticated user's password.

    The current password must be supplied and correct; the new one is stored as
    a hash.
    """
    try:
        current_user.change_password(
            password_update.current_password,
            password_update.new_password
        )
        db.commit()
        return {"message": "Password updated successfully"}
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ------------------------------------------------------------------------------
# Calculations Endpoints (BREAD)
# ------------------------------------------------------------------------------
# Create (Add) Calculation
@app.post(
    "/calculations",
    response_model=CalculationResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["calculations"],
)
def create_calculation(
    calculation_data: CalculationBase,
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Create a new calculation for the authenticated user.
    Automatically computes the 'result'.
    """
    try:
        new_calculation = Calculation.create(
            calculation_type=calculation_data.type,
            user_id=current_user.id,
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


# Browse / List Calculations
@app.get("/calculations", response_model=List[CalculationResponse], tags=["calculations"])
def list_calculations(
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    List all calculations belonging to the current authenticated user.
    """
    calculations = db.query(Calculation).filter(Calculation.user_id == current_user.id).all()
    return calculations


# Report / Usage statistics
# Declared before /calculations/{calc_id} so that "stats" is matched as a
# literal path and not captured as a calculation id.
@app.get("/calculations/stats", response_model=CalculationStats, tags=["calculations"])
def get_calculation_stats(
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Summarize the current authenticated user's calculation history.

    Reports how many calculations they have saved, the average number of
    operands, a per-type breakdown, and when they last calculated something.
    """
    calculations = db.query(Calculation).filter(Calculation.user_id == current_user.id).all()
    return Calculation.summarize(calculations)


def _get_owned_calculation(calc_id: str, current_user, db: Session) -> Calculation:
    """
    Fetch a calculation by UUID, scoped to the current user.

    Raises:
        HTTPException: 400 if the id is not a valid UUID, 404 if the calculation
            does not exist or belongs to a different user.
    """
    try:
        calc_uuid = UUID(calc_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid calculation id format.")

    calculation = db.query(Calculation).filter(
        Calculation.id == calc_uuid,
        Calculation.user_id == current_user.id
    ).first()
    if not calculation:
        raise HTTPException(status_code=404, detail="Calculation not found.")

    return calculation


def _apply_calculation_update(
    calculation: Calculation,
    calculation_update: CalculationUpdate,
    db: Session
) -> Calculation:
    """
    Apply updated inputs to a calculation and recompute its result.

    With no inputs supplied there is nothing to change, so the calculation is
    returned untouched and updated_at keeps its stored value.

    Raises:
        HTTPException: 400 if the new inputs are invalid for the calculation type
            (for example, dividing by zero).
    """
    if calculation_update.inputs is None:
        return calculation

    calculation.inputs = calculation_update.inputs
    try:
        calculation.result = calculation.get_result()
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    db.commit()
    db.refresh(calculation)
    return calculation


# Read / Retrieve a Specific Calculation by ID
@app.get("/calculations/{calc_id}", response_model=CalculationResponse, tags=["calculations"])
def get_calculation(
    calc_id: str,
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Retrieve a single calculation by its UUID, if it belongs to the current user.
    """
    return _get_owned_calculation(calc_id, current_user, db)


# Edit / Update a Calculation (full replace)
@app.put("/calculations/{calc_id}", response_model=CalculationResponse, tags=["calculations"])
def update_calculation(
    calc_id: str,
    calculation_replace: CalculationReplace,
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Replace the inputs (and thus the result) of a specific calculation.

    The inputs are the whole of what a calculation stores, so a full replace
    requires them; omitting them is a 422 rather than a silent no-op. Use PATCH
    for a partial update.
    """
    calculation = _get_owned_calculation(calc_id, current_user, db)
    return _apply_calculation_update(calculation, calculation_replace, db)


# Edit / Update a Calculation (partial)
@app.patch("/calculations/{calc_id}", response_model=CalculationResponse, tags=["calculations"])
def partially_update_calculation(
    calc_id: str,
    calculation_update: CalculationUpdate,
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Partially update a specific calculation.

    Fields omitted from the request body are left unchanged, so sending an empty
    body is a no-op that returns the calculation as-is.
    """
    calculation = _get_owned_calculation(calc_id, current_user, db)
    return _apply_calculation_update(calculation, calculation_update, db)


# Delete a Calculation
@app.delete("/calculations/{calc_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["calculations"])
def delete_calculation(
    calc_id: str,
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Delete a calculation by its UUID, if it belongs to the current user.
    """
    calculation = _get_owned_calculation(calc_id, current_user, db)
    db.delete(calculation)
    db.commit()
    return None


# ------------------------------------------------------------------------------
# Main Block to Run the Server
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=8001, log_level="info")
