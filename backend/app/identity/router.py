import logging
import secrets
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.errors import AppError, log_app_error, log_unhandled_exception
from app.identity import service
from app.identity.github_client import GitHubOAuthClient, get_github_client
from app.identity.schemas import MeResponse
from app.models.identity import User
from app.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

_STATE_COOKIE = "oauth_state"
_STATE_COOKIE_PATH = "/api/v1/auth/github"
_STATE_MAX_AGE = 600
_GITHUB_AUTH_URL = "https://github.com/login/oauth/authorize"

# Codes the callback may put into ?error= on the frontend. Any other failure
# (SLUG_CONFLICT, unexpected exceptions) is reported as INTERNAL_ERROR.
_CALLBACK_ERROR_CODES = frozenset(
    {
        "ACCESS_DENIED",
        "INVALID_STATE",
        "MISSING_CODE",
        "OAUTH_CODE_INVALID",
        "GITHUB_UNAVAILABLE",
        "INTERNAL_ERROR",
    }
)


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
    # The user reaches this endpoint by browser navigation, so every error goes back to
    # the frontend's sign-in screen instead of a JSON body. Errors are handled here so
    # the state cookie is removed on every exit.
    try:
        resp = _complete_github_login(request, code, state, error, db, github_client)
    except AppError as exc:
        db.rollback()
        log_app_error(request, exc)
        if exc.code not in _CALLBACK_ERROR_CODES:
            logger.warning(
                "%s reported as INTERNAL_ERROR (request_id=%s)",
                exc.code,
                request.state.request_id,
            )
        resp = _login_error_redirect(exc.code)
    except Exception as exc:
        db.rollback()
        log_unhandled_exception(request, exc)
        resp = _login_error_redirect("INTERNAL_ERROR")
    resp.delete_cookie(**_state_cookie_attrs())
    return resp


def _login_error_redirect(code: str) -> RedirectResponse:
    # Only a code from the closed list goes into the URL; nothing from the request or
    # from GitHub. The address is built from FRONTEND_URL alone.
    if code not in _CALLBACK_ERROR_CODES:
        code = "INTERNAL_ERROR"
    login_url = f"{str(settings.frontend_url).rstrip('/')}/login"
    return RedirectResponse(url=f"{login_url}?{urlencode({'error': code})}", status_code=302)


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
    current_user: User = Depends(get_current_user),
) -> MeResponse:
    profile = service.get_user_profile(db, current_user.id)
    return MeResponse(
        id=current_user.id,
        github_login=current_user.github_login,
        email=current_user.email,
        profile_slug=profile.slug if profile else None,
    )
