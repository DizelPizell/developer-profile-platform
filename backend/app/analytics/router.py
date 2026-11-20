from collections import Counter
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import AfterValidator
from sqlalchemy.orm import Session

from app.analytics import service
from app.analytics.schemas import (
    EventIn,
    Period,
    ProfileAnalyticsResponse,
    ProfileCounts,
    ProjectAnalyticsItem,
    ProjectAnalyticsResponse,
    ProjectCounts,
    ProjectDay,
)
from app.clock import utcnow
from app.dependencies import get_current_user, get_db
from app.models.identity import User
from app.profile import service as profile_service
from app.projects import service as projects_service
from app.rate_limit import limit_events
from app.settings import settings

router = APIRouter(prefix="/analytics", tags=["analytics"])

PERIODS = (7, 30, 90)


def _known_period(days: int) -> int:
    if days not in PERIODS:
        raise ValueError(f"days must be one of {PERIODS}")
    return days


# Literal[7, 30, 90] would not accept the string a query parameter arrives as.
Days = Annotated[int, AfterValidator(_known_period), Query()]


@router.post("/events", status_code=202, dependencies=[Depends(limit_events)])
def track_event(event: EventIn, request: Request, db: Session = Depends(get_db)) -> Response:
    """Counts an event from a public page (ADR-0029). The same 202 whether it is
    counted or dropped, so the answer does not tell whether a hidden project exists."""
    service.record_event(db, event, request.cookies.get(settings.session_cookie_name))
    db.commit()
    return Response(status_code=202)


def _period(days: int) -> Period:
    end = utcnow().date()
    return Period(days=days, start=end - timedelta(days=days - 1), end=end)


def _project_counts(counts: Counter[str]) -> ProjectCounts:
    return ProjectCounts(
        project_views=counts["PROJECT_VIEW"],
        demo_clicks=counts["DEMO_CLICK"],
        github_clicks=counts["GITHUB_CLICK"],
    )


@router.get("/profile")
def get_profile_analytics(
    days: Days = 30,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ProfileAnalyticsResponse:
    """The owner's counters for the last `days` UTC days, today included: totals and
    every own project (ADR-0029). Sums of events, not visitors."""
    period = _period(days)
    profile = profile_service.get_own_profile(db, user)
    totals, per_project = service.profile_counts(db, profile.id, period.start)
    return ProfileAnalyticsResponse(
        period=period,
        totals=ProfileCounts(
            profile_views=totals["PROFILE_VIEW"],
            contact_clicks=totals["CONTACT_CLICK"],
            **_project_counts(totals).model_dump(),
        ),
        projects=[
            ProjectAnalyticsItem(
                id=project.id,
                title=project.title,
                status=project.status,
                visibility=project.visibility,
                counts=_project_counts(per_project.get(project.id, Counter())),
            )
            for project in projects_service.list_own_projects(db, user)
        ],
    )


@router.get("/projects/{project_id}")
def get_project_analytics(
    project_id: str,
    days: Days = 30,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ProjectAnalyticsResponse:
    """One own project's counters by UTC day for the last `days` days; another
    user's project is the same 404 as in GET /projects/{id}."""
    project = projects_service.get_own_project(db, user, project_id)
    period = _period(days)
    daily = service.project_daily(db, project.id, period.start)
    days_list = [period.start + timedelta(days=offset) for offset in range(days)]
    return ProjectAnalyticsResponse(
        period=period,
        totals=_project_counts(sum(daily.values(), Counter())),
        daily=[
            ProjectDay(day=day, counts=_project_counts(daily.get(day, Counter())))
            for day in days_list
        ],
    )
