"""Plain text fields of the profile and of projects (ADR-013, ADR-015)."""

import unicodedata

from pydantic import AfterValidator
from pydantic_core import PydanticCustomError


def has_control_characters(value: str, allowed: set[str]) -> bool:
    return any(unicodedata.category(ch) == "Cc" and ch not in allowed for ch in value)


# Line and paragraph separators break a line like \n but are not control
# characters (Zl, Zp). U+0085 (next line) is a control character already.
_LINE_SEPARATORS = {" ", " "}


def plain_text(max_length: int, *, allow_newline: bool = False) -> AfterValidator:
    """Trim all edge whitespace, turn blank into null, reject control characters
    (newlines only where allowed) and, in single-line fields, line separators,
    enforce the length limit."""
    allowed_controls = {"\n"} if allow_newline else set()

    def breaks_line(value: str) -> bool:
        return not allow_newline and any(ch in _LINE_SEPARATORS for ch in value)

    def normalize(value: str | None) -> str | None:
        if value is None:
            return None
        if allow_newline:
            value = value.replace("\r\n", "\n")
        value = value.strip()
        if not value:
            return None
        if has_control_characters(value, allowed_controls) or breaks_line(value):
            raise PydanticCustomError("control_characters", "Control characters are not allowed")
        if len(value) > max_length:
            raise PydanticCustomError("string_too_long", "String is too long")
        return value

    return AfterValidator(normalize)
