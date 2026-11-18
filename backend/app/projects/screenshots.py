"""Screenshots of a project (ADR-0022). Every change runs under the project row lock."""

import uuid

from sqlalchemy import case, delete, func, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.canonical_uuid import parse_canonical_uuid
from app.errors import AppError
from app.media.images import EncodedImage, ImageRejected
from app.models.projects import SCREENSHOTS_PER_PROJECT, Project, ProjectScreenshot


def limit_reached() -> AppError:
    return AppError(
        "SCREENSHOT_LIMIT_REACHED",
        "Screenshot limit reached",
        409,
        {"limit": SCREENSHOTS_PER_PROJECT},
    )


def rejected(exc: ImageRejected) -> AppError:
    # Same shape as a request validation error of the file field.
    return AppError(
        "VALIDATION_ERROR",
        "Invalid request",
        422,
        {"fields": [{"loc": ["body", "file"], "type": exc.kind}]},
    )


def list_screenshots(db: Session, project_id: uuid.UUID) -> list[ProjectScreenshot]:
    stmt = (
        select(ProjectScreenshot)
        .where(ProjectScreenshot.project_id == project_id)
        .order_by(ProjectScreenshot.position)
    )
    return list(db.execute(stmt).scalars())


def storage_keys(db: Session, project_id: uuid.UUID) -> list[str]:
    stmt = select(ProjectScreenshot.storage_key).where(ProjectScreenshot.project_id == project_id)
    return list(db.execute(stmt).scalars())


def check_limit(db: Session, project_id: uuid.UUID) -> None:
    """409 at the limit. Stable only under the project lock; without it, an early
    check that spares the re-encoding."""
    count = db.execute(
        select(func.count())
        .select_from(ProjectScreenshot)
        .where(ProjectScreenshot.project_id == project_id)
    ).scalar_one()
    if count >= SCREENSHOTS_PER_PROJECT:
        raise limit_reached()


def add(db: Session, project: Project, key: str, image: EncodedImage, caption: str | None) -> None:
    """Appends after the last screenshot. The caller holds the project row lock; the
    limit itself is the database's (position 1..6, unique per project)."""
    check_limit(db, project.id)
    position = (
        db.execute(
            select(func.max(ProjectScreenshot.position)).where(
                ProjectScreenshot.project_id == project.id
            )
        ).scalar_one()
        or 0
    ) + 1
    try:
        # A savepoint keeps the transaction usable if the insert is rejected.
        with db.begin_nested():
            db.execute(
                insert(ProjectScreenshot).values(
                    project_id=project.id,
                    position=position,
                    caption=caption,
                    storage_key=key,
                    width=image.width,
                    height=image.height,
                )
            )
    except IntegrityError as exc:
        if getattr(exc.orig.diag, "constraint_name", None) == "ck_project_screenshots_position":
            raise limit_reached() from None
        raise


def get(db: Session, project: Project, screenshot_id: str) -> ProjectScreenshot:
    parsed_id = parse_canonical_uuid(screenshot_id)
    screenshot = None
    if parsed_id is not None:
        screenshot = db.execute(
            select(ProjectScreenshot).where(
                ProjectScreenshot.id == parsed_id, ProjectScreenshot.project_id == project.id
            )
        ).scalar_one_or_none()
    if screenshot is None:
        raise AppError("NOT_FOUND", "Not Found", 404)
    return screenshot


def remove(db: Session, screenshot: ProjectScreenshot) -> str:
    """Deletes the row and closes the gap; returns the key of the file to delete
    after the commit. The deferrable UNIQUE (project_id, position) allows the shift."""
    db.execute(delete(ProjectScreenshot).where(ProjectScreenshot.id == screenshot.id))
    db.execute(
        update(ProjectScreenshot)
        .where(
            ProjectScreenshot.project_id == screenshot.project_id,
            ProjectScreenshot.position > screenshot.position,
        )
        .values(position=ProjectScreenshot.position - 1)
    )
    return screenshot.storage_key


def reorder(db: Session, project: Project, screenshot_ids: list[uuid.UUID]) -> None:
    """screenshot_ids is the complete current set in the new order (unique: checked
    by the request schema). One UPDATE ... CASE, as for featured projects."""
    current = [s.id for s in list_screenshots(db, project.id)]
    if set(screenshot_ids) != set(current):
        raise AppError(
            "SCREENSHOT_ORDER_MISMATCH",
            "The list does not match the current screenshots",
            409,
        )
    if screenshot_ids == current:
        return
    new_positions = {sid: i for i, sid in enumerate(screenshot_ids, start=1)}
    db.execute(
        update(ProjectScreenshot)
        .where(ProjectScreenshot.project_id == project.id)
        .values(position=case(new_positions, value=ProjectScreenshot.id))
    )
