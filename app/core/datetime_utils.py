"""
Datetime Utilities Module

Provides the single UTC clock used for every timestamp the application stores.

Mixing naive and timezone-aware datetimes was the root cause of the token
expiry bug, so all models read the current time from here.
"""

from datetime import datetime, timezone


def utcnow() -> datetime:
    """Return the current time as a timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)
