from collections.abc import Generator

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.errors import AppError
from app.identity import service as identity_service
from app.models.identity import User
from app.settings import settings


def get_db() -> Generator[Session]:
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """The user of a valid, non-expired session; otherwise 401."""
    token = request.cookies.get(settings.session_cookie_name)
    user = identity_service.get_session_user(db, token) if token else None
    if user is None:
        raise AppError("UNAUTHORIZED", "Authentication required", 401)
    return user
