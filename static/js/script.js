/**
 * Shared client-side helpers for the calculations UI.
 *
 * Loaded by layout.html before any page-specific script block, so the dashboard
 * and the edit page validate input the same way instead of each rolling its own.
 */

/**
 * Send the browser back to the login page with the stale session discarded.
 */
window.endSession = function () {
  localStorage.clear();
  window.location.href = '/login';
};

/**
 * Redirect to the login page unless an access token is stored.
 *
 * @returns {boolean} True when the page may carry on loading.
 */
window.requireLogin = function () {
  if (localStorage.getItem('access_token')) {
    return true;
  }
  window.location.href = '/login';
  return false;
};

/**
 * Call the API with the stored access token attached.
 *
 * A 401 means the token is no longer usable by any request on the page, so the
 * session is ended here rather than at each call site. Callers get null in that
 * case and should return without touching the page, which is about to unload.
 *
 * @param {string} path - API path, e.g. "/calculations".
 * @param {RequestInit} [options] - Standard fetch options; a body implies JSON.
 * @returns {Promise<(Response|null)>} The response, or null when signed out.
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

/**
 * Show a dismissible notification in the corner of the page.
 *
 * @param {string} message
 * @param {('info'|'success'|'error'|'warning')} [type]
 * @param {number} [duration] - Milliseconds to keep the toast on screen.
 */
window.showToast = function (message, type = 'info', duration = 5000) {
  const styles = {
    success: ['bg-green-500', 'M5 13l4 4L19 7'],
    error: ['bg-red-500', 'M6 18L18 6M6 6l12 12'],
    warning: ['bg-yellow-500', 'M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z'],
    info: ['bg-blue-500', 'M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z']
  };
  const [bgColor, iconPath] = styles[type] || styles.info;

  const toast = document.createElement('div');
  toast.className = `${bgColor} text-white px-4 py-3 rounded-lg shadow-lg flex items-center transform transition-all duration-300 opacity-0 translate-y-2`;
  toast.innerHTML = `
    <svg class="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="${iconPath}"></path></svg>
    <p class="text-sm font-medium">${message}</p>
    <button class="ml-auto text-white hover:text-gray-200" aria-label="Close">
      <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
      </svg>
    </button>
  `;

  document.getElementById('toastContainer').appendChild(toast);
  setTimeout(() => toast.classList.remove('opacity-0', 'translate-y-2'), 10);

  const removeToast = () => {
    toast.classList.add('opacity-0', 'translate-y-2');
    setTimeout(() => toast.remove(), 300);
  };

  toast.querySelector('button').addEventListener('click', removeToast);
  setTimeout(removeToast, duration);
};

/**
 * Parse and validate a comma-separated list of numbers for a calculation.
 *
 * @param {string} raw - Raw text from the inputs field, e.g. "5, 10, 15".
 * @param {string} type - Operation type (addition, subtraction, multiplication, division).
 * @returns {{values: number[], error: (string|null)}} Parsed values and the first
 *   validation error, or null when the input is valid.
 */
window.validateCalculationInputs = function (raw, type) {
  const tokens = String(raw || '')
    .split(',')
    .map((token) => token.trim())
    .filter((token) => token !== '');

  const invalid = tokens.filter((token) => !Number.isFinite(Number(token)));
  if (invalid.length > 0) {
    return {
      values: [],
      error: `Please enter numbers only. Invalid: ${invalid.join(', ')}`
    };
  }

  const values = tokens.map(Number);

  if (values.length < 2) {
    return {
      values,
      error: 'Please enter at least two valid numbers, separated by commas'
    };
  }

  if (type === 'division' && values.slice(1).some((value) => value === 0)) {
    return { values, error: 'Cannot divide by zero' };
  }

  return { values, error: null };
};

/**
 * Check an email address for a plausible shape before sending it to the server.
 *
 * @param {string} email
 * @returns {boolean}
 */
window.isValidEmail = function (email) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
};

/**
 * Describe the first strength rule a password fails.
 *
 * The rules and their wording mirror validate_password_strength in
 * app/schemas/user.py, so the browser reports the same reason the API would
 * without needing a round trip.
 *
 * @param {string} password
 * @returns {(string|null)} The failure message, or null when the password is strong.
 */
window.describePasswordError = function (password) {
  const rules = [
    [(value) => value.length >= 8, 'Password must be at least 8 characters long'],
    [(value) => /[A-Z]/.test(value), 'Password must contain at least one uppercase letter'],
    [(value) => /[a-z]/.test(value), 'Password must contain at least one lowercase letter'],
    [(value) => /[0-9]/.test(value), 'Password must contain at least one digit'],
    [
      (value) => /[!@#$%^&*()_+\-=\[\]{}|;:,.<>?]/.test(value),
      'Password must contain at least one special character'
    ]
  ];

  const failed = rules.find(([passes]) => !passes(String(password || '')));
  return failed ? failed[1] : null;
};

/**
 * Check a password against the same strength rules the API enforces.
 *
 * @param {string} password
 * @returns {boolean}
 */
window.isValidPassword = function (password) {
  return window.describePasswordError(password) === null;
};

/**
 * Mark an input as valid or invalid with a coloured border.
 *
 * @param {HTMLElement} input
 * @param {boolean} isValid
 */
window.setInputValidation = function (input, isValid) {
  if (isValid) {
    input.classList.remove('border-red-500');
    input.classList.add('border-green-500');
  } else {
    input.classList.remove('border-green-500');
    input.classList.add('border-red-500');
  }
};

/**
 * Pull a human-readable message out of an error response body.
 *
 * FastAPI returns `detail` as a string for HTTPException but as a list of error
 * objects for request-validation (422) failures; without this the list renders
 * as "[object Object]".
 *
 * @param {*} data - Parsed JSON response body.
 * @param {string} fallback - Message to use when nothing usable is present.
 * @returns {string}
 */
window.extractErrorMessage = function (data, fallback) {
  const detail = data && data.detail;

  if (typeof detail === 'string' && detail.trim() !== '') {
    return detail;
  }

  if (Array.isArray(detail) && detail.length > 0) {
    const messages = [...new Set(
      detail
        .map((item) => (item && item.msg ? item.msg : null))
        .filter(Boolean)
        .map((msg) => msg.replace(/^Value error,\s*/, ''))
    )];
    if (messages.length > 0) {
      return messages.join('; ');
    }
  }

  return fallback;
};
