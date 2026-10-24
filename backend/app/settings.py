from typing import Literal

from pydantic import Field, HttpUrl, SecretStr
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

    @property
    def secure_cookies(self) -> bool:
        return self.app_env != "development"


settings = Settings()
