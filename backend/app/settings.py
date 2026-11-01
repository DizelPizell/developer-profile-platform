from typing import Literal

from pydantic import Field, HttpUrl, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    @model_validator(mode="after")
    def _retry_max_not_below_base(self) -> "Settings":
        if self.github_worker_retry_max_seconds < self.github_worker_retry_base_seconds:
            raise ValueError(
                "GITHUB_WORKER_RETRY_MAX_SECONDS is below GITHUB_WORKER_RETRY_BASE_SECONDS"
            )
        return self

    @property
    def secure_cookies(self) -> bool:
        return self.app_env != "development"


settings = Settings()
