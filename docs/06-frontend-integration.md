# Module 6: Frontend Integration

## Introduction

In this module, we'll integrate our FastAPI backend with a frontend using Jinja2 templates, HTML, CSS, and JavaScript. This will create a complete web application where users can register, login, and perform calculations using a user-friendly interface.

## Objectives

- Set up Jinja2 templates with FastAPI
- Create a responsive layout with CSS
- Implement client-side JavaScript for API interactions
- Create HTML templates for different pages
- Implement form validation on the client side

## Setting Up Jinja2 Templates

First, let's configure FastAPI to use Jinja2 templates in `app/main.py`:

```python
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# Mount the static files directory
app.mount("/static", StaticFiles(directory="static"), name="static")

# Set up Jinja2 templates directory
templates = Jinja2Templates(directory="templates")
```

This allows us to:
1. Serve static files (CSS, JavaScript, images) from the `static` directory
2. Render Jinja2 templates from the `templates` directory

## Creating a Base Layout Template

Let's create a base layout template that all other templates will extend:

```html
<!-- templates/layout.html -->
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}Calculations App{% endblock %}</title>

    <!-- Tailwind is the whole stylesheet; there is no static/css/style.css -->
    <script src="https://unpkg.com/@tailwindcss/browser@4"></script>

    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">

    {% block head %}{% endblock %}
</head>
<body>
    <header>
        <nav>
            <div class="logo">Calculator App</div>
            <div class="nav-links">
                <a href="/">Home</a>
                <span id="auth-links">
                    <a href="/login">Login</a>
                    <a href="/register">Register</a>
                </span>
                <span id="user-links" style="display: none;">
                    <a href="/dashboard">Dashboard</a>
                    <a href="#" id="logout-link">Logout</a>
                </span>
            </div>
        </nav>
    </header>
    
    <main>
        {% block content %}{% endblock %}
    </main>

    <!-- Loaded before any page-specific block, so templates can call apiFetch,
         showToast and the validation helpers directly. -->
    <script src="{{ url_for('static', path='js/script.js') }}"></script>
    
    <footer>
        <p>&copy; 2023 Calculator App - A FastAPI Project</p>
    </footer>
    
    <script>
        // Check if user is logged in
        document.addEventListener('DOMContentLoaded', function() {
            const token = localStorage.getItem('access_token');
            const authLinks = document.getElementById('auth-links');
            const userLinks = document.getElementById('user-links');
            
            if (token) {
                authLinks.style.display = 'none';
                userLinks.style.display = 'inline';
            } else {
                authLinks.style.display = 'inline';
                userLinks.style.display = 'none';
            }
            
            // Logout functionality
            document.getElementById('logout-link').addEventListener('click', function(e) {
                e.preventDefault();
                localStorage.removeItem('access_token');
                localStorage.removeItem('refresh_token');
                localStorage.removeItem('user_info');
                window.location.href = '/';
            });
        });
    </script>
</body>
</html>
```

## Creating Page Templates

Now, let's create templates for each page in our application:

### Home Page

```html
<!-- templates/index.html -->
{% extends "layout.html" %}

{% block title %}Home - Calculator App{% endblock %}

{% block content %}
<section class="hero">
    <div class="hero-content">
        <h1>Welcome to Calculator App</h1>
        <p>A simple yet powerful calculator application built with FastAPI.</p>
        <div class="cta-buttons">
            <a href="/register" class="btn primary">Register</a>
            <a href="/login" class="btn secondary">Login</a>
        </div>
    </div>
</section>

<section class="features">
    <h2>Features</h2>
    <div class="feature-grid">
        <div class="feature-card">
            <h3>Basic Operations</h3>
            <p>Perform addition, subtraction, multiplication, and division.</p>
        </div>
        <div class="feature-card">
            <h3>Save Calculations</h3>
            <p>Save your calculations for future reference.</p>
        </div>
        <div class="feature-card">
            <h3>Secure Authentication</h3>
            <p>Secure user authentication using JWT tokens.</p>
        </div>
        <div class="feature-card">
            <h3>API Access</h3>
            <p>Access calculations via RESTful API endpoints.</p>
        </div>
    </div>
</section>
{% endblock %}
```

### Login Page

```html
<!-- templates/login.html -->
{% extends "layout.html" %}

{% block title %}Login - Calculator App{% endblock %}

{% block content %}
<section class="auth-form">
    <h1>Login</h1>
    
    <div id="error-message" class="error" style="display: none;"></div>
    
    <form id="login-form">
        <div class="form-group">
            <label for="username">Username or Email</label>
            <input type="text" id="username" name="username" required>
        </div>
        
        <div class="form-group">
            <label for="password">Password</label>
            <input type="password" id="password" name="password" required>
        </div>
        
        <button type="submit" class="btn primary">Login</button>
    </form>
    
    <p class="auth-link">
        Don't have an account? <a href="/register">Register here</a>
    </p>
</section>

<script>
    document.getElementById('login-form').addEventListener('submit', async function(e) {
        e.preventDefault();
        
        const username = document.getElementById('username').value;
        const password = document.getElementById('password').value;
        const errorMessage = document.getElementById('error-message');
        
        try {
            const response = await fetch('/auth/login', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ username, password })
            });
            
            if (response.ok) {
                const data = await response.json();
                
                // Store tokens and user info
                localStorage.setItem('access_token', data.access_token);
                localStorage.setItem('refresh_token', data.refresh_token);
                localStorage.setItem('user_info', JSON.stringify({
                    id: data.user_id,
                    username: data.username,
                    email: data.email,
                    first_name: data.first_name,
                    last_name: data.last_name
                }));
                
                // Redirect to dashboard
                window.location.href = '/dashboard';
            } else {
                const error = await response.json();
                errorMessage.textContent = error.detail || 'Login failed. Please check your credentials.';
                errorMessage.style.display = 'block';
            }
        } catch (error) {
            errorMessage.textContent = 'An error occurred. Please try again.';
            errorMessage.style.display = 'block';
            console.error('Login error:', error);
        }
    });
</script>
{% endblock %}
```

### Registration Page

```html
<!-- templates/register.html -->
{% extends "layout.html" %}

{% block title %}Register - Calculator App{% endblock %}

{% block content %}
<section class="auth-form">
    <h1>Create Account</h1>
    
    <div id="error-message" class="error" style="display: none;"></div>
    
    <form id="register-form">
        <div class="form-group">
            <label for="first_name">First Name</label>
            <input type="text" id="first_name" name="first_name" required>
        </div>
        
        <div class="form-group">
            <label for="last_name">Last Name</label>
            <input type="text" id="last_name" name="last_name" required>
        </div>
        
        <div class="form-group">
            <label for="username">Username</label>
            <input type="text" id="username" name="username" required>
        </div>
        
        <div class="form-group">
            <label for="email">Email</label>
            <input type="email" id="email" name="email" required>
        </div>
        
        <div class="form-group">
            <label for="password">Password</label>
            <input type="password" id="password" name="password" required minlength="6">
            <small>Password must be at least 6 characters long.</small>
        </div>
        
        <div class="form-group">
            <label for="confirm_password">Confirm Password</label>
            <input type="password" id="confirm_password" name="confirm_password" required>
        </div>
        
        <button type="submit" class="btn primary">Register</button>
    </form>
    
    <p class="auth-link">
        Already have an account? <a href="/login">Login here</a>
    </p>
</section>

<script>
    document.getElementById('register-form').addEventListener('submit', async function(e) {
        e.preventDefault();
        
        const form = e.target;
        const errorMessage = document.getElementById('error-message');
        
        // Basic validation
        const password = document.getElementById('password').value;
        const confirmPassword = document.getElementById('confirm_password').value;
        
        if (password !== confirmPassword) {
            errorMessage.textContent = 'Passwords do not match.';
            errorMessage.style.display = 'block';
            return;
        }
        
        const userData = {
            first_name: document.getElementById('first_name').value,
            last_name: document.getElementById('last_name').value,
            username: document.getElementById('username').value,
            email: document.getElementById('email').value,
            password: password,
            confirm_password: confirmPassword
        };
        
        try {
            const response = await fetch('/auth/register', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(userData)
            });
            
            if (response.ok) {
                // Registration successful, redirect to login
                window.location.href = '/login?registered=true';
            } else {
                const error = await response.json();
                errorMessage.textContent = error.detail || 'Registration failed. Please try again.';
                errorMessage.style.display = 'block';
            }
        } catch (error) {
            errorMessage.textContent = 'An error occurred. Please try again.';
            errorMessage.style.display = 'block';
            console.error('Registration error:', error);
        }
    });
</script>
{% endblock %}
```

### Dashboard Page

```html
<!-- templates/dashboard.html -->
{% extends "layout.html" %}

{% block title %}Dashboard - Calculator App{% endblock %}

{% block content %}
<section class="dashboard">
    <h1>Dashboard</h1>
    
    <div class="dashboard-grid">
        <div class="calculator-card">
            <h2>New Calculation</h2>
            
            <form id="calculation-form">
                <div class="form-group">
                    <label for="calculation-type">Operation</label>
                    <select id="calculation-type" name="type" required>
                        <option value="addition">Addition</option>
                        <option value="subtraction">Subtraction</option>
                        <option value="multiplication">Multiplication</option>
                        <option value="division">Division</option>
                    </select>
                </div>
                
                <div class="form-group">
                    <label for="calculation-inputs">Numbers (comma-separated)</label>
                    <input type="text" id="calculation-inputs" name="inputs" 
                           placeholder="e.g. 5, 10, 15" required>
                    <small>Enter at least two numbers, separated by commas.</small>
                </div>
                
                <button type="submit" class="btn primary">Calculate</button>
            </form>
            
            <div id="calculation-result" class="result-box" style="display: none;">
                <h3>Result</h3>
                <p id="result-value"></p>
            </div>
        </div>
        
        <div class="calculations-list">
            <h2>Your Calculations</h2>
            
            <div id="calculations-container">
                <p>Loading your calculations...</p>
            </div>
        </div>
    </div>
</section>

<script>
    document.addEventListener('DOMContentLoaded', async function() {
        // Bounce straight to /login if there is no stored token
        if (!requireLogin()) return;

        loadCalculations();

        document.getElementById('calculation-form').addEventListener('submit', async function(e) {
            e.preventDefault();

            const type = document.getElementById('calculation-type').value;
            const raw = document.getElementById('calculation-inputs').value;

            // Shared validation, so the page rejects what the API would reject
            const inputs = validateCalculationInputs(raw, type);
            if (!inputs) return;

            try {
                const response = await apiFetch('/calculations', {
                    method: 'POST',
                    body: JSON.stringify({ type, inputs })
                });
                if (!response) return;   // 401 handled; page is unloading

                const data = await response.json();
                if (!response.ok) {
                    showToast(extractErrorMessage(data, 'Something went wrong'), 'error');
                    return;
                }

                document.getElementById('result-value').textContent = data.result;
                document.getElementById('calculation-result').style.display = 'block';
                loadCalculations();
            } catch (error) {
                console.error('Calculation error:', error);
                showToast('An error occurred. Please try again.', 'error');
            }
        });
    });

    async function loadCalculations() {
        const container = document.getElementById('calculations-container');

        try {
            const response = await apiFetch('/calculations');
            if (!response) return;

            if (!response.ok) {
                container.innerHTML = '<p>Error loading calculations. Please try again.</p>';
                return;
            }

            const calculations = await response.json();

            if (calculations.length === 0) {
                container.innerHTML = '<p>No calculations yet. Create your first one!</p>';
                return;
            }

            let html = '<div class="calculations-grid">';

            calculations.forEach(calc => {
                const date = new Date(calc.created_at).toLocaleDateString();
                const time = new Date(calc.created_at).toLocaleTimeString();

                // result is nullable, so never render it bare
                const result = calc.result ?? '—';

                html += `
                    <div class="calculation-item">
                        <div class="calc-type ${calc.type}">${calc.type}</div>
                        <div class="calc-inputs">${calc.inputs.join(' , ')}</div>
                        <div class="calc-result">${result}</div>
                        <div class="calc-date">${date} ${time}</div>
                        <div class="calc-actions">
                            <a href="/dashboard/view/${calc.id}" class="btn small">View</a>
                            <a href="/dashboard/edit/${calc.id}" class="btn small secondary">Edit</a>
                            <button class="btn small danger" onclick="deleteCalculation('${calc.id}')">Delete</button>
                        </div>
                    </div>
                `;
            });

            html += '</div>';
            container.innerHTML = html;
        } catch (error) {
            console.error('Error loading calculations:', error);
            container.innerHTML = '<p>Error loading calculations. Please try again.</p>';
        }
    }

    async function deleteCalculation(id) {
        if (!confirm('Are you sure you want to delete this calculation?')) {
            return;
        }

        try {
            const response = await apiFetch(`/calculations/${id}`, { method: 'DELETE' });
            if (!response) return;

            if (response.ok) {
                showToast('Calculation deleted', 'success');
                loadCalculations();
            } else {
                showToast('Error deleting calculation. Please try again.', 'error');
            }
        } catch (error) {
            console.error('Delete error:', error);
            showToast('An error occurred. Please try again.', 'error');
        }
    }
</script>
{% endblock %}
```

## Styling: Tailwind, not a stylesheet

This project does not ship a CSS file. `layout.html` pulls in Tailwind's browser
build and every template styles itself with utility classes:

```html
<script src="https://unpkg.com/@tailwindcss/browser@4"></script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
```

There used to be a `static/css/style.css` here as well. It was linked from every
page but contained nothing — a zero-byte file fetched on every page load — so it
and its `<link>` were removed. The same clean-up dropped a duplicate Inter font
import (the page was loading the same family from both `rsms.me` and Google
Fonts) and a `<link>` to a `favicon.ico` that was never added to the repo and so
returned a 404 on every page.

The general rule: a `<link>` to a file that does not exist, or exists but is
empty, is not harmless. It is a request per page load that can only fail.

## Adding JavaScript Functionality

`static/js/script.js` holds the helpers shared by every page. `layout.html`
loads it *before* any page-specific `<script>` block, so each template can call
into it directly.

### The API wrapper

Every authenticated request goes through one function. This is the most
important helper in the file:

```javascript
/**
 * Call the API with the stored access token attached.
 *
 * A 401 means the token is no longer usable by any request on the page, so the
 * session is ended here rather than at each call site. Callers get null in that
 * case and should return without touching the page, which is about to unload.
 */
window.apiFetch = async function (path, options = {}) {
  const headers = { ...options.headers };
  headers['Authorization'] = `Bearer ${localStorage.getItem('access_token')}`;
  if (options.body !== undefined) {
    headers['Content-Type'] = 'application/json';
  }

  const response = await fetch(path, { ...options, headers });

  if (response.status === 401) {
    window.endSession();
    return null;
  }

  return response;
};
```

Call sites become short, and — more to the point — they all handle expiry the
same way:

```javascript
const response = await apiFetch('/calculations');
if (!response) return;          // 401 already handled; page is unloading
const calculations = await response.json();
```

Before this existed, each page hand-wrote the same three things: read the token
from `localStorage`, set the `Authorization` header, and check for a 401. There
were eleven such blocks across `dashboard`, `edit_calculation`,
`view_calculation` and `profile`. Eleven copies of a rule means eleven chances
for one of them to drift — and a page whose 401 check was missed leaves the user
staring at an empty screen instead of the login form.

### Session helpers

```javascript
window.endSession = function () {
  localStorage.clear();
  window.location.href = '/login';
};

window.requireLogin = function () {
  if (localStorage.getItem('access_token')) {
    return true;
  }
  window.location.href = '/login';
  return false;
};
```

`requireLogin()` runs at the top of each protected page. `endSession()` is what
`apiFetch` calls on a 401, and what the logout button calls directly. Note that
it clears *all* of `localStorage`, so a stale refresh token cannot outlive the
session it belonged to.

### Notifications

`showToast` renders a dismissible message in the corner of the page:

```javascript
window.showToast = function (message, type = 'info', duration = 5000) { ... }

showToast('Calculation saved', 'success');
showToast('Could not reach the server', 'error');
```

It takes `'info'`, `'success'`, `'error'` or `'warning'`. This lives in
`script.js` rather than in an inline `<script>` in `layout.html`, so that pages
and helpers can both reach it.

### Validation helpers

The remaining exports keep client-side validation consistent with what the API
will actually accept:

| Helper | Purpose |
|---|---|
| `validateCalculationInputs(raw, type)` | Parse the operand box; enforce ≥2 numbers and reject division by zero |
| `isValidEmail(email)` | Email shape check |
| `describePasswordError(password)` | Return the first unmet password rule, or null |
| `isValidPassword(password)` | Boolean form of the above |
| `setInputValidation(input, isValid)` | Toggle the valid/invalid styling on a field |
| `extractErrorMessage(data, fallback)` | Pull a readable message out of a FastAPI error body |

`describePasswordError` mirrors `validate_password_strength` in
`app/schemas/user.py`. The server is still the authority — the client copy only
exists so the user gets feedback before submitting.

> **Keep them in step.** If you change the password policy, change it in both
> places. The server rule is the one that is enforced; the client rule is the
> one the user sees. When they disagree, the form either rejects a password the
> API would accept, or accepts one it will not.

## Connecting FastAPI Routes with Templates

Now, let's create the web routes in `app/main.py`:

```python
# Web (HTML) Routes
@app.get("/", response_class=HTMLResponse, tags=["web"])
def read_index(request: Request):
    """Landing page."""
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/login", response_class=HTMLResponse, tags=["web"])
def login_page(request: Request):
    """Login page."""
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/register", response_class=HTMLResponse, tags=["web"])
def register_page(request: Request):
    """Registration page."""
    return templates.TemplateResponse("register.html", {"request": request})

@app.get("/dashboard", response_class=HTMLResponse, tags=["web"])
def dashboard_page(request: Request):
    """Dashboard page, listing calculations & new calculation form."""
    return templates.TemplateResponse("dashboard.html", {"request": request})

@app.get("/dashboard/view/{calc_id}", response_class=HTMLResponse, tags=["web"])
def view_calculation_page(request: Request, calc_id: str):
    """
    Page for viewing a single calculation (Read).
    Renders 'view_calculation.html' and passes calc_id to the template.
    """
    return templates.TemplateResponse("view_calculation.html", {"request": request, "calc_id": calc_id})

@app.get("/dashboard/edit/{calc_id}", response_class=HTMLResponse, tags=["web"])
def edit_calculation_page(request: Request, calc_id: str):
    """
    Page for editing a calculation (Update).
    Renders 'edit_calculation.html' and passes calc_id to the template.
    """
    return templates.TemplateResponse("edit_calculation.html", {"request": request, "calc_id": calc_id})
```

## Client-Side vs. Server-Side Rendering

In our implementation, we're using a hybrid approach:

1. **Server-side rendering**: Using Jinja2 templates to render the initial HTML
2. **Client-side JavaScript**: Using JavaScript to fetch data from the API and update the DOM

This approach gives us the benefits of both worlds:
- Initial page load is fast with server-rendered HTML
- Dynamic updates happen without page refreshes using JavaScript
- SEO benefits from server-rendered content
- Better user experience with client-side interactivity

## Next Steps

In the next module, we'll implement testing for our application, including unit tests, integration tests, and end-to-end tests.

## Additional Resources

- [FastAPI Templates](https://fastapi.tiangolo.com/advanced/templates/)
- [Jinja2 Documentation](https://jinja.palletsprojects.com/)
- [Frontend Best Practices](https://developers.google.com/web/fundamentals)
- [Modern CSS Guide](https://moderncss.dev/)