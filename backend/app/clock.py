from datetime import UTC, datetime


def utcnow() -> datetime:
    """Current time as naive UTC, the form the database columns store."""
    return datetime.now(UTC).replace(tzinfo=None)
