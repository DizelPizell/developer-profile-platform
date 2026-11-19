"""Deletes accounts again after a restore from a backup (ADR-0028, DEPLOY.md).

    python -m app.identity.delete_user <user_id> [<user_id> ...]

A snapshot taken before an account was deleted brings the account back. The ids
come from the backend's `account deleted user_id=...` log lines after the
snapshot's date. Each account is deleted as by DELETE /api/v1/auth/me, files
included; an id with no account is reported and skipped.
"""

import sys
import uuid

from sqlalchemy.orm import Session

from app.identity.service import delete_account
from app.media import storage


def run(db: Session, user_ids: list[uuid.UUID]) -> list[str]:
    lines = []
    for user_id in user_ids:
        keys = delete_account(db, user_id)
        db.commit()
        if keys is None:
            lines.append(f"{user_id}: no such account")
            continue
        storage.delete(keys)
        lines.append(f"{user_id}: deleted, {len(keys)} files")
    return lines


def main(argv: list[str]) -> int:
    from app.database import SessionLocal

    try:
        user_ids = [uuid.UUID(arg) for arg in argv]
    except ValueError:
        user_ids = []
    if not user_ids:
        print("usage: python -m app.identity.delete_user <user_id> [<user_id> ...]")
        return 2
    with SessionLocal() as db:
        for line in run(db, user_ids):
            print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
