import secrets

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.errors import AppError
from app.identity import service
from app.identity.github_client import GitHubOAuthClient, get_github_client
from app.identity.schemas import MeResponse
from app.models.identity import User
from app.settings import settings

router = APIRouter(prefix="/auth", tags=["auth"])

_STATE_COOKIE = "oauth_state"
_GITHUB_AUTH_URL = "https://github.com/login/oauth/authorize"


def _session_cookie_kwargs(secure: bool) -> dict:
    return {
        "key": settings.session_cookie_name,
        "httponly": True,
        "samesite": "lax",
        "path": "/",
        "max_age": settings.session_ttl_days * 86400,
        "secure": secure,
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
    redirect_url = (
        f"{_GITHUB_AUTH_URL}"
        f"?client_id={settings.github_client_id}"
        f"&redirect_uri={settings.github_callback_url}"
        f"&state={state}"
    )
    resp = RedirectResponse(url=redirect_url, status_code=302)
    resp.set_cookie(
        key=_STATE_COOKIE,
        value=state,
        httponly=True,
        samesite="lax",
        path="/api/v1/auth/github",
        max_age=600,
        secure=settings.app_env != "development",
    )
    return resp


@router.get("/github/callback")
def github_callback(
    request: Request,
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    db: Session = Depends(get_db),
    github_client: GitHubOAuthClient = Depends(get_github_client),
) -> RedirectResponse:
    if error:
        raise AppError("ACCESS_DENIED", "GitHub OAuth access was denied", 400)

    expected_state = request.cookies.get(_STATE_COOKIE)
    if not expected_state or state != expected_state:
        raise AppError("INVALID_STATE", "OAuth state mismatch or missing state cookie", 400)

    if not code:
        raise AppError("MISSING_CODE", "Missing OAuth authorization code", 400)

    # All GitHub API calls first, then DB work
    access_token = github_client.exchange_code(
        code=code,
        client_id=settings.github_client_id,
        client_secret=settings.github_client_secret,
        redirect_uri=settings.github_callback_url,
    )
    github_user_data = github_client.get_user(access_token)
    # access_token is intentionally discarded here — never stored

    github_user_id: int = github_user_data["id"]
    github_login: str = github_user_data["login"]
    email: str | None = github_user_data.get("email")

    user, is_new = service.get_or_create_user(db, github_user_id, github_login, email)
    if not is_new:
        service.update_user_fields(db, user, github_login, email)

    token = service.create_session(db, user.id)
    db.commit()

    resp = RedirectResponse(url=settings.frontend_url, status_code=302)
    resp.set_cookie(
        value=token,
        **_session_cookie_kwargs(secure=settings.app_env != "development"),
    )
    resp.delete_cookie(key=_STATE_COOKIE, path="/api/v1/auth/github")
    return resp


@router.post("/logout", status_code=204)
def logout(request: Request, db: Session = Depends(get_db)) -> Response:
    token = request.cookies.get(settings.session_cookie_name)
    if token:
        service.delete_session(db, token)
    db.commit()
    resp = Response(status_code=204)
    resp.delete_cookie(key=settings.session_cookie_name, path="/")
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
