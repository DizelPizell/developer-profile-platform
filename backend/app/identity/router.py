import secrets
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.errors import AppError, app_error_response, internal_error_response
from app.identity import service
from app.identity.github_client import GitHubOAuthClient, get_github_client
from app.identity.schemas import MeResponse
from app.models.identity import User
from app.settings import settings

router = APIRouter(prefix="/auth", tags=["auth"])

_STATE_COOKIE = "oauth_state"
_STATE_COOKIE_PATH = "/api/v1/auth/github"
_STATE_MAX_AGE = 600
_GITHUB_AUTH_URL = "https://github.com/login/oauth/authorize"


def _state_cookie_attrs() -> dict:
    return {
        "key": _STATE_COOKIE,
        "path": _STATE_COOKIE_PATH,
        "httponly": True,
        "samesite": "lax",
        "secure": settings.secure_cookies,
    }


def _session_cookie_attrs() -> dict:
    return {
        "key": settings.session_cookie_name,
        "path": "/",
        "httponly": True,
        "samesite": "lax",
        "secure": settings.secure_cookies,
    }


def get_current_user(
    request: Request, db: Session = Depends(get_db)
) -> User | None:
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        return None
    return service.get_session_user(db, token)


@router.get("/github/login")
def github_login() -> RedirectResponse:
    state = secrets.token_urlsafe(32)
    query = urlencode(
        {
            "client_id": settings.github_client_id,
            "redirect_uri": str(settings.github_callback_url),
            "state": state,
        }
    )
    resp = RedirectResponse(url=f"{_GITHUB_AUTH_URL}?{query}", status_code=302)
    resp.set_cookie(value=state, max_age=_STATE_MAX_AGE, **_state_cookie_attrs())
    return resp


@router.get("/github/callback")
def github_callback(
    request: Request,
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    db: Session = Depends(get_db),
    github_client: GitHubOAuthClient = Depends(get_github_client),
) -> Response:
    # Errors are turned into responses here so the state cookie is removed on every exit.
    try:
        resp = _complete_github_login(request, code, state, error, db, github_client)
    except AppError as exc:
        resp = app_error_response(request, exc)
    except Exception as exc:
        resp = internal_error_response(request, exc)
    resp.delete_cookie(**_state_cookie_attrs())
    return resp


def _complete_github_login(
    request: Request,
    code: str | None,
    state: str | None,
    error: str | None,
    db: Session,
    github_client: GitHubOAuthClient,
) -> Response:
    if error:
        raise AppError("ACCESS_DENIED", "GitHub OAuth access was denied", 400)

    expected_state = request.cookies.get(_STATE_COOKIE)
    if (
        not expected_state
        or not state
        or not secrets.compare_digest(state.encode(), expected_state.encode())
    ):
        raise AppError("INVALID_STATE", "OAuth state mismatch or missing state cookie", 400)

    if not code:
        raise AppError("MISSING_CODE", "Missing OAuth authorization code", 400)

    # All GitHub API calls first, then DB work
    access_token = github_client.exchange_code(
        code=code,
        client_id=settings.github_client_id,
        client_secret=settings.github_client_secret.get_secret_value(),
        redirect_uri=str(settings.github_callback_url),
    )
    github_user = github_client.get_user(access_token)
    # access_token is intentionally discarded here — never stored

    user, is_new = service.get_or_create_user(
        db, github_user.id, github_user.login, github_user.email, github_user.avatar_url
    )
    if not is_new:
        service.update_user_fields(
            db, user, github_user.login, github_user.email, avatar_url=github_user.avatar_url
        )

    previous_token = request.cookies.get(settings.session_cookie_name)
    if previous_token:
        service.delete_session(db, previous_token)
    token = service.create_session(db, user.id)
    db.commit()

    resp = RedirectResponse(url=str(settings.frontend_url), status_code=302)
    resp.set_cookie(
        value=token,
        max_age=settings.session_ttl_days * 86400,
        **_session_cookie_attrs(),
    )
    return resp


@router.post("/logout", status_code=204)
def logout(request: Request, db: Session = Depends(get_db)) -> Response:
    token = request.cookies.get(settings.session_cookie_name)
    if token:
        service.delete_session(db, token)
    db.commit()
    resp = Response(status_code=204)
    resp.delete_cookie(**_session_cookie_attrs())
    return resp


@router.get("/me")
def me(
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user),
) -> MeResponse:
    if current_user is None:
        raise AppError("UNAUTHORIZED", "Authentication required", 401)
    profile = service.get_user_profile(db, current_user.id)
    return MeResponse(
        id=current_user.id,
        github_login=current_user.github_login,
        email=current_user.email,
        profile_slug=profile.slug if profile else None,
    )
