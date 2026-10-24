from fastapi import FastAPI

from app.errors import AppError, app_error_handler
from app.identity.router import router as auth_router
from app.settings import settings  # validates config at startup

app = FastAPI(title=settings.app_name)
app.add_exception_handler(AppError, app_error_handler)
app.include_router(auth_router, prefix="/api/v1")


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
