from collections.abc import Generator
from dataclasses import dataclass

import httpx

from app.errors import AppError

_TIMEOUT = httpx.Timeout(10.0)


_MAX_AVATAR_URL = 2048


@dataclass(frozen=True)
class GitHubUser:
    id: int
    login: str
    email: str | None
    avatar_url: str | None


def _avatar_url(value: object) -> str | None:
    # Rendered as <img src> by the frontend: accept only bounded https URLs.
    if isinstance(value, str) and value.startswith("https://") and len(value) <= _MAX_AVATAR_URL:
        return value
    return None


def _unavailable(reason: str, github_status: int | None) -> AppError:
    # Logged as the failure reason: exception type or a fixed label plus GitHub's
    # HTTP status — never the response body, URLs, code, state or tokens.
    return AppError(
        "GITHUB_UNAVAILABLE",
        "GitHub is unavailable",
        502,
        log_context={"reason": reason, "github_status": github_status},
    )


def _request_failed(exc: httpx.HTTPError) -> AppError:
    status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
    return _unavailable(type(exc).__name__, status)


def _json_object(response: httpx.Response) -> dict:
    try:
        data = response.json()
    except ValueError as exc:
        raise _unavailable(type(exc).__name__, response.status_code) from None
    if not isinstance(data, dict):
        raise _unavailable("non_object_body", response.status_code)
    return data


class GitHubOAuthClient:
    def __init__(self, http_client: httpx.Client) -> None:
        self._client = http_client

    def exchange_code(
        self,
        code: str,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
    ) -> str:
        """Exchange authorization code for GitHub access token."""
        try:
            response = self._client.post(
                "https://github.com/login/oauth/access_token",
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "code": code,
                    "redirect_uri": redirect_uri,
                },
                headers={"Accept": "application/json"},
                timeout=_TIMEOUT,
            )
            response.raise_for_status()
        except (httpx.HTTPStatusError, httpx.RequestError) as exc:
            raise _request_failed(exc) from None

        data = _json_object(response)
        if "error" in data:
            raise AppError("OAUTH_CODE_INVALID", "Invalid or expired OAuth code", 400)
        access_token = data.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise _unavailable("missing_access_token", response.status_code)
        return access_token

    def get_user(self, access_token: str) -> GitHubUser:
        """Fetch authenticated GitHub user (id, login, email)."""
        try:
            response = self._client.get(
                "https://api.github.com/user",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github+json",
                },
                timeout=_TIMEOUT,
            )
            response.raise_for_status()
        except (httpx.HTTPStatusError, httpx.RequestError) as exc:
            raise _request_failed(exc) from None

        data = _json_object(response)
        user_id = data.get("id")
        login = data.get("login")
        if isinstance(user_id, bool) or not isinstance(user_id, int):
            raise _unavailable("invalid_user_id", response.status_code)
        if not isinstance(login, str) or not login:
            raise _unavailable("invalid_login", response.status_code)
        email = data.get("email")
        return GitHubUser(
            id=user_id,
            login=login,
            email=email if isinstance(email, str) else None,
            avatar_url=_avatar_url(data.get("avatar_url")),
        )


def get_github_client() -> Generator[GitHubOAuthClient]:
    with httpx.Client() as client:
        yield GitHubOAuthClient(client)
