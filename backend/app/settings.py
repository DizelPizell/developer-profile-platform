from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    app_name: str = "developer-profile-platform"
    app_debug: bool = True

    backend_host: str = "0.0.0.0"
    backend_port: int = 8000

    database_url: str

    github_client_id: str
    github_client_secret: str
    github_callback_url: str
    frontend_url: str
    session_ttl_days: int = 14
    session_cookie_name: str = "session"


settings = Settings()
