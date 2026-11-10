"""Contacts of a profile: normalization and links (ADR-020).

For the standard types only the normalized name, slug, address or number is
stored, and the server builds the link itself, so a stored standard contact
cannot point to another host.
"""

import re
from urllib.parse import urlsplit

from pydantic_core import PydanticCustomError

from app.models.identity import CONTACT_VALUE_LIMITS
from app.plain_text import has_control_characters

# ADR-020, "Validation". ASCII only: no ?, &, % or spaces, so a mailto: link
# needs no escaping and cannot carry parameters.
_EMAIL = re.compile(r"[A-Za-z0-9._+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
_TELEGRAM_LINK = re.compile(r"(?:https://)?t\.me/(\w+)/?", re.IGNORECASE | re.ASCII)
_TELEGRAM_NAME = re.compile(r"[A-Za-z0-9_]{5,32}")
# The whole input is matched: hosts are compared exactly, not by suffix.
_LINKEDIN = re.compile(
    r"(?:https://)?(?:www\.|[a-z]{2}\.)?linkedin\.com/in/([A-Za-z0-9-]{3,100})/?",
    re.IGNORECASE | re.ASCII,
)
_PHONE = re.compile(r"\+[1-9][0-9]{7,14}")
_PHONE_SEPARATORS = re.compile(r"[ ()-]")

# Paths of t.me that are not usernames, from https://core.telegram.org/api/links
# (checked 2026-11-10): the reserved <username>.t.me values and the first path
# segments of the link formats. Values shorter than 5 characters or with + and $
# already fail the username rule; they are listed for completeness.
TELEGRAM_RESERVED = frozenset(
    {
        "addemoji", "addlist", "addstickers", "addstyle", "addtheme", "auction", "auth",
        "boost", "call", "confirmphone", "contact", "giftcode", "invoice", "joinchat",
        "login", "m", "nft", "proxy", "setlanguage", "share", "socks", "web", "a", "k", "z",
        "newbot", "oauth", "bg", "msg", "c",
    }
)  # fmt: skip


def _invalid(kind: str) -> PydanticCustomError:
    # The message names the rule only: input values are never echoed (ADR-013).
    return PydanticCustomError(f"invalid_{kind}", f"Invalid {kind} contact")


def _email(value: str) -> str:
    if not _EMAIL.fullmatch(value):
        raise _invalid("email")
    local, domain = value.rsplit("@", 1)
    return f"{local}@{domain.lower()}"


def _telegram(value: str) -> str:
    link = _TELEGRAM_LINK.fullmatch(value)
    name = link.group(1) if link else value.removeprefix("@")
    if not _TELEGRAM_NAME.fullmatch(name) or name.lower() in TELEGRAM_RESERVED:
        raise _invalid("telegram")
    return name


def _linkedin(value: str) -> str:
    link = _LINKEDIN.fullmatch(value)
    if not link:
        raise _invalid("linkedin")
    return link.group(1)


def _phone(value: str) -> str:
    value = _PHONE_SEPARATORS.sub("", value)
    if not _PHONE.fullmatch(value):
        raise _invalid("phone")
    return value


def _other(value: str) -> str:
    if has_control_characters(value, set()) or any(ch.isspace() or ch == "\\" for ch in value):
        raise _invalid("url")
    try:
        parts = urlsplit(value)
        parts.port  # noqa: B018 - raises ValueError for a malformed port
    except ValueError:
        raise _invalid("url") from None
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https") or "@" in parts.netloc:
        raise _invalid("url")
    if not parts.hostname or "." not in parts.hostname:
        raise _invalid("url")
    return scheme + value[len(parts.scheme) :]


_NORMALIZERS = {
    "EMAIL": _email,
    "TELEGRAM": _telegram,
    "LINKEDIN": _linkedin,
    "PHONE": _phone,
    "OTHER": _other,
}


def normalize(contact_type: str, value: str) -> str:
    """The value to store for this type; PydanticCustomError when it is not accepted."""
    value = value.strip()
    if not value:
        # A blank value is an error, not a removed contact.
        raise PydanticCustomError("string_too_short", "String is too short")
    value = _NORMALIZERS[contact_type](value)
    if len(value) > CONTACT_VALUE_LIMITS[contact_type][1]:
        raise PydanticCustomError("string_too_long", "String is too long")
    return value


def contact_url(contact_type: str, value: str) -> str:
    """The link the server builds; for OTHER the stored URL itself."""
    match contact_type:
        case "EMAIL":
            return f"mailto:{value}"
        case "TELEGRAM":
            return f"https://t.me/{value}"
        case "LINKEDIN":
            return f"https://www.linkedin.com/in/{value}"
        case "PHONE":
            return f"tel:{value}"
        case _:
            return value
