from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.access_log import install_access_log_filter
from app.errors import UnhandledErrorMiddleware, register_error_handlers
from app.identity.router import router as auth_router
from app.origin_check import OriginCheckMiddleware, origin_of
from app.profile.router import public_router as public_profile_router
from app.profile.router import router as profile_router
from app.projects.router import router as projects_router
from app.request_id import REQUEST_ID_HEADER, RequestIdMiddleware
from app.settings import settings  # validates config at startup

install_access_log_filter()

frontend_origin = origin_of(settings.frontend_url)

app = FastAPI(title=settings.app_name)
register_error_handlers(app)

# Each add_middleware wraps the previous one, so this list runs innermost first.
# Request flow: RequestId -> CORS (answers preflight) -> Origin check -> 500 catcher -> routes.
app.add_middleware(UnhandledErrorMiddleware)
app.add_middleware(OriginCheckMiddleware, allowed_origin=frontend_origin)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[frontend_origin],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Content-Type"],
    expose_headers=[REQUEST_ID_HEADER],
)
app.add_middleware(RequestIdMiddleware)

app.include_router(auth_router, prefix="/api/v1")
app.include_router(profile_router, prefix="/api/v1")
app.include_router(public_profile_router, prefix="/api/v1")
app.include_router(projects_router, prefix="/api/v1")


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
