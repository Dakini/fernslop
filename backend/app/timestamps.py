"""Timestamp helpers.

The frontend compares timestamps as plain strings, so every timestamp the API
emits uses the exact form ``YYYY-MM-DDTHH:MM:SS.mmmZ`` (UTC, three-digit
milliseconds, literal ``Z``).
"""

from datetime import UTC, datetime


def now() -> datetime:
    """The current time as a timezone-aware UTC datetime."""
    return datetime.now(UTC)


def format_timestamp(dt: datetime) -> str:
    """Format an aware datetime as ``2026-10-22T09:30:00.000Z``.

    Milliseconds are truncated, not rounded. Raises ``ValueError`` for a naive
    datetime, because its zone is unknown.
    """
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("format_timestamp requires a timezone-aware datetime")
    utc = dt.astimezone(UTC)
    millis = utc.microsecond // 1000
    return f"{utc:%Y-%m-%dT%H:%M:%S}.{millis:03d}Z"
