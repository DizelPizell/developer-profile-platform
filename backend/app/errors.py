import logging
from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.request_id import REQUEST_ID_HEADER

logger = logging.getLogger(__name__)


class AppError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
        details: dict | None = None,
        *,
        log_context: dict[str, str | int | None] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        # Server-side diagnostics only; never part of the response. Callers must
        # not put secrets, URLs with parameters or upstream response bodies here.
        self.log_context = log_context


def error_response(
    request: Request,
    status_code: int,
    code: str,
    message: str,
    details: dict | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    request_id = request.state.request_id
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": details or {},
                "request_id": request_id,
            }
        },
        # Set here as well: the 500 handler runs outside RequestIdMiddleware.
        headers={**(headers or {}), REQUEST_ID_HEADER: request_id},
    )


def log_app_error(request: Request, exc: AppError) -> None:
    if exc.log_context:
        context = " ".join(f"{key}={value}" for key, value in exc.log_context.items())
        logger.warning("%s (request_id=%s) %s", exc.code, request.state.request_id, context)


def log_unhandled_exception(request: Request, exc: Exception) -> None:
    logger.error("Unhandled exception (request_id=%s)", request.state.request_id, exc_info=exc)


def app_error_response(request: Request, exc: AppError) -> JSONResponse:
    log_app_error(request, exc)
    return error_response(request, exc.status_code, exc.code, exc.message, exc.details)


def internal_error_response(request: Request, exc: Exception) -> JSONResponse:
    log_unhandled_exception(request, exc)
    return error_response(request, 500, "INTERNAL_ERROR", "Internal server error")


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return app_error_response(request, exc)


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    # Only location and error type: input values must never be echoed back.
    fields = [{"loc": list(err["loc"]), "type": err["type"]} for err in exc.errors()]
    return error_response(request, 422, "VALIDATION_ERROR", "Invalid request", {"fields": fields})


async def http_error_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    try:
        status = HTTPStatus(exc.status_code)
        code, message = status.name, status.phrase
    except ValueError:
        code, message = "HTTP_ERROR", "HTTP error"
    return error_response(request, exc.status_code, code, message, headers=exc.headers)


class UnhandledErrorMiddleware:
    """
    Turns unexpected exceptions into 500 INTERNAL_ERROR responses.

    Replaces an Exception handler, which Starlette runs in ServerErrorMiddleware
    outside every user middleware; placed inside CORSMiddleware, the 500 response
    gets CORS headers like any other response.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        response_started = False

        async def send_tracking(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, send_tracking)
        except Exception as exc:
            if response_started:
                raise
            response = internal_error_response(Request(scope), exc)
            await response(scope, receive, send)


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_error_handler)
