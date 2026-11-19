from pathlib import Path
from typing import Literal

from pydantic import Field, HttpUrl, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# The OAuth callback route: /api/v1 + the auth router's /auth/github/callback.
PRODUCTION_CALLBACK_PATH = "/api/v1/auth/github/callback"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: Literal["development", "test", "production"]
    app_name: str = "developer-profile-platform"

    backend_host: str = "0.0.0.0"
    backend_port: int = 8000

    database_url: str

    github_client_id: str = Field(min_length=1)
    github_client_secret: SecretStr = Field(min_length=1)
    github_callback_url: HttpUrl
    frontend_url: HttpUrl
    session_ttl_days: int = Field(default=14, ge=1)
    session_cookie_name: str = "session"
    # GitHub requests one user may spend in any 60 minutes (ADR-018); at least
    # the most expensive operation, a manual sync of 7.
    github_user_requests_per_hour: int = Field(default=60, ge=7)
    # How long a page of the repository list is kept in memory (ADR-017).
    github_repository_list_cache_seconds: int = Field(default=300, ge=1)
    # The pause between manual syncs of one repository, counted from its latest
    # job (ADR-018).
    github_manual_sync_cooldown_seconds: int = Field(default=600, ge=1)
    # The sync worker (ADR-009, ADR-018).
    github_worker_poll_seconds: float = Field(default=5, gt=0)
    github_worker_max_attempts: int = Field(default=5, ge=1)
    github_worker_retry_base_seconds: int = Field(default=30, ge=1)
    github_worker_retry_max_seconds: int = Field(default=1800, ge=1)
    # A SYNCING job not updated for this long is taken back by the watchdog.
    github_worker_stale_seconds: int = Field(default=600, ge=1)
    # The worker claims no job while GitHub's remaining budget is at or below this.
    github_worker_reserve: int = Field(default=500, ge=0)
    # A repository linked to a published project gets a job this often; the worker
    # queues at most this many such jobs a minute (ADR-018).
    github_periodic_sync_seconds: int = Field(default=86_400, ge=1)
    github_periodic_sync_batch: int = Field(default=30, ge=1)
    # The media volume: screenshots written by the API, served by Nginx (ADR-0022).
    media_root: Path = Path("/srv/media")
    # The worker's dead-man's switch (ADR-0027): a GET after a good iteration, at
    # most every 5 minutes. Empty turns it off; production requires it. A secret:
    # anyone with the URL can report the worker alive.
    worker_heartbeat_url: HttpUrl | None = None

    @field_validator("worker_heartbeat_url", mode="before")
    @classmethod
    def _empty_url_is_none(cls, value: object) -> object:
        return None if value == "" else value

    @model_validator(mode="after")
    def _retry_max_not_below_base(self) -> "Settings":
        if self.github_worker_retry_max_seconds < self.github_worker_retry_base_seconds:
            raise ValueError(
                "GITHUB_WORKER_RETRY_MAX_SECONDS is below GITHUB_WORKER_RETRY_BASE_SECONDS"
            )
        return self

    @model_validator(mode="after")
    def _production_is_one_https_origin(self) -> "Settings":
        # ADR-0021: in production the frontend and the API share one https origin.
        # A wrong value here would only show up as a broken sign-in.
        if self.app_env != "production":
            return self
        if self.worker_heartbeat_url is None:
            # ADR-0027: without it a dead worker goes unnoticed.
            raise ValueError("WORKER_HEARTBEAT_URL is required in production")
        front, callback = self.frontend_url, self.github_callback_url
        if front.scheme != "https":
            raise ValueError("FRONTEND_URL must use https in production")
        same_origin = (callback.scheme, callback.host, callback.port) == (
            front.scheme,
            front.host,
            front.port,
        )
        if not same_origin or callback.path != PRODUCTION_CALLBACK_PATH:
            raise ValueError(
                "GITHUB_CALLBACK_URL must be the origin of FRONTEND_URL followed by "
                f"{PRODUCTION_CALLBACK_PATH} in production"
            )
        return self

    @property
    def secure_cookies(self) -> bool:
        return self.app_env != "development"


settings = Settings()
