# marketedge/src/utils.py
"""Shared, dependency-light helpers used across the workbench."""

from datetime import datetime, timezone


def utcnow() -> datetime:
    """Return the current time as a timezone-aware UTC datetime.

    Prefer this over the deprecated ``datetime.utcnow()`` (which returns a
    naive datetime and is slated for removal in a future Python release).
    """
    return datetime.now(timezone.utc)


def ensure_utc(value: datetime) -> datetime:
    """Return ``value`` as a UTC-aware datetime.

    Naive datetimes are assumed to already be in UTC. Useful at boundaries
    where inputs may be either naive (e.g. parsed without tzinfo) or aware
    (e.g. loaded from the UTC-aware state layer), so arithmetic between them
    never raises "can't compare offset-naive and offset-aware".
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def parse_timestamp(value: str) -> datetime:
    """Parse an ISO-8601 timestamp, accepting a trailing ``Z`` for UTC.

    ``datetime.fromisoformat`` did not accept the ``Z`` suffix before Python
    3.11, and we still normalize it here so behavior is identical across the
    backtesting, settlement, paper-ledger, and experiment loaders.
    """
    clean = value.strip()
    if clean.endswith("Z"):
        clean = f"{clean[:-1]}+00:00"
    return datetime.fromisoformat(clean)
