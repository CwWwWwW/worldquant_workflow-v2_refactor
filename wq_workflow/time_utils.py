from __future__ import annotations

from datetime import UTC, datetime


def utc_now() -> datetime:
    """Return the current timezone-aware UTC datetime."""
    return datetime.now(UTC)


def utc_now_iso(*, timespec: str = "seconds") -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return utc_now().isoformat(timespec=timespec)


def utc_now_strftime(fmt: str) -> str:
    """Return the current UTC time formatted with strftime."""
    return utc_now().strftime(fmt)
