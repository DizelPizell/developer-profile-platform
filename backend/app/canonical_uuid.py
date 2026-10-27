import uuid


def parse_canonical_uuid(value: str | None) -> uuid.UUID | None:
    """The canonical 8-4-4-4-12 hex form only (either case); anything else is None.

    uuid.UUID() alone also accepts forms without hyphens, with braces, with a
    urn:uuid: prefix or with hyphens in other places.
    """
    if not value or len(value) != 36:
        return None
    try:
        parsed = uuid.UUID(value)
    except ValueError:
        return None
    return parsed if str(parsed) == value.lower() else None
