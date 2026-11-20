from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.analytics.schemas import EventIn
from app.clock import utcnow
from app.identity import service as identity_service
from app.models.analytics import PROFILE_EVENTS, PROJECT_EVENTS, AnalyticsDailyCount
from app.profile import service as profile_service
from app.projects import service as projects_service


def record_event(db: Session, event: EventIn, session_token: str | None) -> bool:
    """Adds one to today's counter (UTC); False when the event is dropped: the profile
    is not published, the project is not PUBLISHED + PUBLIC on it, the project id does
    not fit the type, or the viewer is the owner (ADR-0029)."""
    found = profile_service.get_public_profile(db, event.slug)
    if found is None:
        return False
    profile, owner, _ = found

    if event.type in PROJECT_EVENTS and event.project_id is None:
        return False
    if event.type in PROFILE_EVENTS and event.project_id is not None:
        return False
    project_id = None
    if event.project_id is not None:
        project = projects_service.get_public_project(db, owner.id, event.project_id)
        if project is None:
            return False
        project_id = project.id

    viewer = identity_service.get_session_user(db, session_token) if session_token else None
    if viewer is not None and viewer.id == owner.id:
        return False

    table = AnalyticsDailyCount.__table__
    statement = insert(table).values(
        profile_id=profile.id,
        project_id=project_id,
        event_type=event.type,
        day=utcnow().date(),
        count=1,
    )
    db.execute(
        statement.on_conflict_do_update(
            constraint="uq_analytics_daily_counts", set_={"count": table.c.count + 1}
        )
    )
    return True
