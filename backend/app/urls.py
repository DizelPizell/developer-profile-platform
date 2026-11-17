"""User-provided web links: contacts of type OTHER (ADR-020) and the project demo (ADR-0023)."""

from urllib.parse import urlsplit

from pydantic_core import PydanticCustomError

from app.plain_text import has_control_characters


def http_url(value: str) -> str:
    """An http(s) URL with a dotted host and no login; the scheme comes back in lower case.

    The caller trims the value and enforces the length; the server never requests it.
    """
    if has_control_characters(value, set()) or any(ch.isspace() or ch == "\\" for ch in value):
        raise _invalid()
    try:
        parts = urlsplit(value)
        parts.port  # noqa: B018 - raises ValueError for a malformed port
    except ValueError:
        raise _invalid() from None
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https") or "@" in parts.netloc:
        raise _invalid()
    if not parts.hostname or "." not in parts.hostname:
        raise _invalid()
    return scheme + value[len(parts.scheme) :]


def _invalid() -> PydanticCustomError:
    # The message names the rule only: input values are never echoed (ADR-013).
    return PydanticCustomError("invalid_url", "Invalid URL")
