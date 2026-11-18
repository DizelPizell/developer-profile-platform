"""The media volume (ADR-0022): the only code that writes or deletes its files.

Moving to S3 replaces this module and nothing else.
"""

import logging
import os
import uuid
from collections.abc import Iterable
from pathlib import Path

from app.settings import settings

logger = logging.getLogger(__name__)


def screenshot_key(project_id: uuid.UUID) -> str:
    # A new name per upload: unguessable, and the content behind a name never changes.
    return f"projects/{project_id}/{uuid.uuid4()}.webp"


def url(key: str) -> str:
    """The address on the site's own origin."""
    return f"/media/{key}"


def _path(key: str) -> Path:
    return Path(settings.media_root) / key


def save(key: str, data: bytes) -> None:
    path = _path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(data)
    # A reader sees either no file or the whole file.
    os.replace(temporary, path)


def delete(keys: Iterable[str]) -> None:
    """Never raises: a file left behind is logged and removed later by the sweep."""
    for key in keys:
        path = _path(key)
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            logger.warning("Media file not deleted: %s (%s)", key, type(exc).__name__)
            continue
        try:
            path.parent.rmdir()
        except OSError:
            pass  # not empty: other screenshots of the project are still there
