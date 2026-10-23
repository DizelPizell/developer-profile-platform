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


settings = Settings()
