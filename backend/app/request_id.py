import uuid

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.canonical_uuid import parse_canonical_uuid

REQUEST_ID_HEADER = "X-Request-ID"


def _parse_request_id(value: str | None) -> str | None:
    """Accept only a canonical UUID string; anything else is ignored."""
    parsed = parse_canonical_uuid(value)
    return str(parsed) if parsed else None


class RequestIdMiddleware:
    """Puts a request id into request.state and the X-Request-ID response header."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = Headers(scope=scope).get(REQUEST_ID_HEADER)
        request_id = _parse_request_id(incoming) or str(uuid.uuid4())
        scope.setdefault("state", {})["request_id"] = request_id

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                if REQUEST_ID_HEADER not in headers:
                    headers.append(REQUEST_ID_HEADER, request_id)
            await send(message)

        await self.app(scope, receive, send_with_request_id)
