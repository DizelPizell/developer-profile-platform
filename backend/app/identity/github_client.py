from collections.abc import Generator

import httpx

from app.errors import AppError

_TIMEOUT = httpx.Timeout(10.0)


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
        except httpx.TimeoutException as exc:
            raise AppError("GITHUB_UNAVAILABLE", "GitHub OAuth is unavailable", 502) from exc
        except (httpx.HTTPStatusError, httpx.RequestError) as exc:
            raise AppError("GITHUB_UNAVAILABLE", "GitHub OAuth is unavailable", 502) from exc

        data = response.json()
        if "error" in data:
            raise AppError(
                "OAUTH_CODE_INVALID",
                "Invalid or expired OAuth code",
                400,
            )
        return data["access_token"]

    def get_user(self, access_token: str) -> dict:
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
        except httpx.TimeoutException as exc:
            raise AppError("GITHUB_UNAVAILABLE", "GitHub API is unavailable", 502) from exc
        except (httpx.HTTPStatusError, httpx.RequestError) as exc:
            raise AppError("GITHUB_UNAVAILABLE", "GitHub API is unavailable", 502) from exc

        return response.json()


def get_github_client() -> Generator[GitHubOAuthClient]:
    with httpx.Client() as client:
        yield GitHubOAuthClient(client)
