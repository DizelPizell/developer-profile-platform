from fastapi import FastAPI

from app.access_log import install_access_log_filter
from app.errors import setup_error_handling
from app.identity.router import router as auth_router
from app.profile.router import public_router as public_profile_router
from app.profile.router import router as profile_router
from app.settings import settings  # validates config at startup

install_access_log_filter()

app = FastAPI(title=settings.app_name)
setup_error_handling(app)
app.include_router(auth_router, prefix="/api/v1")
app.include_router(profile_router, prefix="/api/v1")
app.include_router(public_profile_router, prefix="/api/v1")


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
