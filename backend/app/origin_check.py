from urllib.parse import urlsplit

from pydantic import HttpUrl
from starlette.datastructures import Headers
from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from app.errors import error_response

_CHECKED_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_DEFAULT_PORTS = {"http": 80, "https": 443}


def origin_of(url: HttpUrl) -> str:
    """Browser-style origin string (no path, default port omitted), e.g. http://localhost:3000."""
    port = "" if url.port in (None, _DEFAULT_PORTS.get(url.scheme)) else f":{url.port}"
    return f"{url.scheme}://{url.host}{port}"


def _normalize(origin: str) -> tuple[str, str, int] | None:
    try:
        parts = urlsplit(origin)
        port = parts.port
    except ValueError:
        return None
    if parts.scheme not in _DEFAULT_PORTS or not parts.hostname:
        return None
    if parts.path or parts.query or parts.fragment or parts.username or parts.password:
        return None
    return parts.scheme, parts.hostname, port or _DEFAULT_PORTS[parts.scheme]


class OriginCheckMiddleware:
    """Rejects state-changing requests whose Origin is missing or not the frontend's origin."""

    def __init__(self, app: ASGIApp, allowed_origin: str) -> None:
        self.app = app
        self.allowed = _normalize(allowed_origin)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["method"] in _CHECKED_METHODS:
            origin = Headers(scope=scope).get("origin")
            if origin is None or _normalize(origin) != self.allowed:
                response = error_response(
                    Request(scope), 403, "CSRF_ORIGIN_INVALID", "Request origin is not allowed"
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)
