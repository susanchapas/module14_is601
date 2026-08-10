# Module 5: API Endpoints (BREAD Operations)

## Introduction

In this module, we'll implement the API endpoints for our calculator application. We'll follow the BREAD pattern, which stands for Browse, Read, Edit, Add, Delete. This is a variation of the more common CRUD (Create, Read, Update, Delete) pattern.

## Objectives

- Understand the BREAD pattern for API design
- Implement REST API endpoints for calculations
- Learn how to handle path and query parameters
- Implement error handling for API endpoints
- Secure endpoints with authentication

## The BREAD Pattern

The BREAD pattern is a variation of CRUD that is more user-centric:

- **Browse**: List or search for resources (GET /calculations)
- **Read**: Retrieve a specific resource (GET /calculations/{id})
- **Edit**: Update an existing resource (PUT /calculations/{id} to replace, PATCH to update partially)
- **Add**: Create a new resource (POST /calculations)
- **Delete**: Remove a resource (DELETE /calculations/{id})

## Implementing Calculation Endpoints

Let's implement the BREAD operations for our calculations:

### Add (Create) Calculation

```python
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
```

### Browse (List) Calculations

```python
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
```

### Read (Retrieve) Calculation

```python
@app.get("/calculations/{calc_id}", response_model=CalculationResponse, tags=["calculations"])
def get_calculation(
    calc_id: str,
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Retrieve a single calculation by its UUID, if it belongs to the current user.
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
```

### Edit (Update) Calculation

`PUT` and `PATCH` are both offered, and they mean different things. The
difference is carried entirely by the schema each one accepts:

```python
# Edit / Update a Calculation (full replace)
@app.put("/calculations/{calc_id}", response_model=CalculationResponse, tags=["calculations"])
def update_calculation(
    calc_id: str,
    calculation_replace: CalculationReplace,   # inputs REQUIRED
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
    calculation_update: CalculationUpdate,     # inputs OPTIONAL
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
```

| | `PUT` | `PATCH` |
|---|---|---|
| Schema | `CalculationReplace` | `CalculationUpdate` |
| `inputs` | Required | Optional |
| Empty body | `422 Unprocessable Entity` | `200`, nothing changed |

Both handlers were once byte-identical, both taking `CalculationUpdate`. `PUT`
was documented as a full replace but behaved as a partial one, so omitting
`inputs` silently did nothing instead of failing. Making the *schema* enforce
the distinction is what makes the two verbs actually differ — the handler
bodies stay one line each.

### The shared helpers

Both routes delegate to two helpers, which is why neither repeats the lookup or
the recompute:

```python
def _get_owned_calculation(calc_id: str, current_user, db: Session) -> Calculation:
    """
    Fetch a calculation by UUID, scoped to the current user.

    Raises:
        HTTPException: 400 if the id is not a valid UUID, 404 if the calculation
            does not exist or belongs to a different user.
    """
    try:
        calc_uuid = UUID(calc_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid calculation id format.") from e

    calculation = db.query(Calculation).filter(
        Calculation.id == calc_uuid,
        Calculation.user_id == current_user.id
    ).first()
    if not calculation:
        raise HTTPException(status_code=404, detail="Calculation not found.")

    return calculation


def _apply_calculation_update(calculation, calculation_update, db) -> Calculation:
    """
    Apply updated inputs to a calculation and recompute its result.

    With no inputs supplied there is nothing to change, so the calculation is
    returned untouched and updated_at keeps its stored value.
    """
    if calculation_update.inputs is None:
        return calculation

    calculation.inputs = calculation_update.inputs
    try:
        calculation.result = calculation.get_result()
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    db.commit()
    db.refresh(calculation)
    return calculation
```

Two details worth calling out:

- **The early return matters.** Without `if calculation_update.inputs is None:
  return calculation`, an empty `PATCH` still fell through to `db.commit()` and
  bumped `updated_at` — so a request that changed nothing reported that the row
  had just been modified.
- **`updated_at` is not set by hand.** The column carries
  `onupdate=utcnow`, so SQLAlchemy maintains it. Assigning
  `datetime.utcnow()` in the route, as an earlier version did, both duplicated
  that and stored a *naive* datetime in a timezone-aware column.

### Delete Calculation

```python
@app.delete("/calculations/{calc_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["calculations"])
def delete_calculation(
    calc_id: str,
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Delete a calculation by its UUID, if it belongs to the current user.
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

    db.delete(calculation)
    db.commit()
    return None
```

## Path and Query Parameters

In our endpoints, we used two types of parameters:

1. **Path Parameters**: Variables part of the URL path
   - Example: `/calculations/{calc_id}`
   - Used for identifying a specific resource

2. **Query Parameters**: Variables appended to the URL after a `?`
   - Example: `/calculations?type=addition`
   - Used for filtering, pagination, or other options

Let's add filtering and pagination to our Browse endpoint:

```python
@app.get("/calculations", response_model=List[CalculationResponse], tags=["calculations"])
def list_calculations(
    type: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    current_user = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    List calculations belonging to the current authenticated user.
    
    Parameters:
    - type: Filter by calculation type (addition, subtraction, etc.)
    - limit: Maximum number of records to return
    - offset: Number of records to skip (for pagination)
    """
    query = db.query(Calculation).filter(Calculation.user_id == current_user.id)
    
    # Apply type filter if provided
    if type:
        query = query.filter(Calculation.type == type.lower())
    
    # Apply pagination
    query = query.order_by(Calculation.created_at.desc())
    query = query.limit(limit).offset(offset)
    
    return query.all()
```

## Error Handling

Notice that in our endpoints, we handle various error cases:

1. **Invalid UUID Format**: When the calculation ID is not a valid UUID
2. **Resource Not Found**: When the calculation doesn't exist or doesn't belong to the current user
3. **Validation Errors**: When the input data doesn't meet our schema requirements
4. **Business Logic Errors**: When the calculation logic throws an error (e.g., division by zero)

This provides a better user experience by giving clear error messages rather than generic 500 errors.

## Security Considerations

Our API endpoints are secured using JWT authentication. Each endpoint requires a valid token, and we also check that the user is only accessing their own resources.

Security best practices implemented:

1. **Authentication**: All endpoints require a valid JWT token
2. **Resource Ownership**: Users can only access their own calculations
3. **Input Validation**: All input data is validated using Pydantic schemas
4. **Error Handling**: Clear error messages without exposing internal details
5. **HTTPS**: In production, all API endpoints should be served over HTTPS

## API Documentation

FastAPI automatically generates API documentation using the OpenAPI specification. When running the application, you can access:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

These pages provide interactive documentation for your API, including:
- Endpoint descriptions and URLs
- Request and response schemas
- Authentication requirements
- Example requests and responses

## Next Steps

In the next module, we'll integrate our API with a frontend using Jinja2 templates and JavaScript.

## Additional Resources

- [FastAPI Path Parameters](https://fastapi.tiangolo.com/tutorial/path-params/)
- [FastAPI Query Parameters](https://fastapi.tiangolo.com/tutorial/query-params/)
- [FastAPI Response Status Codes](https://fastapi.tiangolo.com/tutorial/response-status-code/)
- [REST API Design Best Practices](https://restfulapi.net/)