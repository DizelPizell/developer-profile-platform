"""Removes media files left behind by a crash (ADR-0022, p. 6).

    python -m app.media.sweep [--dry-run]

A file goes when no screenshot row names it and it is older than a day: an
upload writes its file just before its row, so a younger file may still get one.
A temporary file (.name.tmp) older than a day is always a leftover.
"""

import sys
import time
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.projects import ProjectScreenshot

MIN_AGE_SECONDS = 24 * 60 * 60


def orphans(db: Session, root: Path, now: float) -> list[Path]:
    """Files under root/projects that the sweep removes, oldest first."""
    if not root.is_dir():
        # A wrong MEDIA_ROOT must not look like "every row is gone".
        raise FileNotFoundError(f"MEDIA_ROOT is not a directory: {root}")
    # shortcut: every key in memory, hundreds in V1; check one project directory
    # at a time if this grows to millions.
    keys = set(db.execute(select(ProjectScreenshot.storage_key)).scalars())
    found = []
    for path in (root / "projects").glob("*/*"):
        if not path.is_file() or now - path.stat().st_mtime < MIN_AGE_SECONDS:
            continue
        if path.relative_to(root).as_posix() not in keys:
            found.append(path)
    return sorted(found, key=lambda p: p.stat().st_mtime)


def sweep(db: Session, root: Path, now: float, *, dry_run: bool) -> list[Path]:
    found = orphans(db, root, now)
    if not dry_run:
        for path in found:
            path.unlink(missing_ok=True)
        for directory in (root / "projects").glob("*"):
            if directory.is_dir() and not any(directory.iterdir()):
                directory.rmdir()
    return found


def main(argv: list[str]) -> int:
    from app.database import SessionLocal
    from app.settings import settings

    unknown = [arg for arg in argv if arg != "--dry-run"]
    if unknown:
        print(f"usage: python -m app.media.sweep [--dry-run]; unknown: {' '.join(unknown)}")
        return 2
    dry_run = "--dry-run" in argv
    root = Path(settings.media_root)
    with SessionLocal() as db:
        try:
            found = sweep(db, root, time.time(), dry_run=dry_run)
        except FileNotFoundError as exc:
            print(exc)
            return 1
    for path in found:
        print(path.relative_to(root).as_posix())
    print(f"{len(found)} file(s) {'would be removed' if dry_run else 'removed'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
