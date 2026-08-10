/**
 * Shared client-side helpers for the calculations UI.
 *
 * Loaded by layout.html before any page-specific script block, so the dashboard
 * and the edit page validate input the same way instead of each rolling its own.
 */

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
