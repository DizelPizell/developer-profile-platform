from fastapi import FastAPI

from app.settings import settings  # validates config at startup

app = FastAPI(title=settings.app_name)


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
