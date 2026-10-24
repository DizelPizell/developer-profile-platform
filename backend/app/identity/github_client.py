from collections.abc import Generator
from dataclasses import dataclass

import httpx

from app.errors import AppError

_TIMEOUT = httpx.Timeout(10.0)


@dataclass(frozen=True)
class GitHubUser:
    id: int
    login: str
    email: str | None


def _unavailable() -> AppError:
    return AppError("GITHUB_UNAVAILABLE", "GitHub is unavailable", 502)


def _json_object(response: httpx.Response) -> dict:
    try:
        data = response.json()
    except ValueError:
        raise _unavailable() from None
    if not isinstance(data, dict):
        raise _unavailable()
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
        except (httpx.HTTPStatusError, httpx.RequestError):
            raise _unavailable() from None

        data = _json_object(response)
        if "error" in data:
            raise AppError("OAUTH_CODE_INVALID", "Invalid or expired OAuth code", 400)
        access_token = data.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise _unavailable()
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
        except (httpx.HTTPStatusError, httpx.RequestError):
            raise _unavailable() from None

        data = _json_object(response)
        user_id = data.get("id")
        login = data.get("login")
        if isinstance(user_id, bool) or not isinstance(user_id, int):
            raise _unavailable()
        if not isinstance(login, str) or not login:
            raise _unavailable()
        email = data.get("email")
        return GitHubUser(id=user_id, login=login, email=email if isinstance(email, str) else None)


def get_github_client() -> Generator[GitHubOAuthClient]:
    with httpx.Client() as client:
        yield GitHubOAuthClient(client)
