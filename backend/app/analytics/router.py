from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.analytics import service
from app.analytics.schemas import EventIn
from app.dependencies import get_db
from app.rate_limit import limit_events
from app.settings import settings

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.post("/events", status_code=202, dependencies=[Depends(limit_events)])
def track_event(event: EventIn, request: Request, db: Session = Depends(get_db)) -> Response:
    """Counts an event from a public page (ADR-0029). The same 202 whether it is
    counted or dropped, so the answer does not tell whether a hidden project exists."""
    service.record_event(db, event, request.cookies.get(settings.session_cookie_name))
    db.commit()
    return Response(status_code=202)
