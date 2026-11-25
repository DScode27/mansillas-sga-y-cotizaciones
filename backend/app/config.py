from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
PRODUCTION_ENVIRONMENTS = {"production", "prod"}


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables and backend/.env."""

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Mansillas SGA API"
    app_env: str = "development"
    debug: bool = False
    host: str = "127.0.0.1"
    port: int = 8000
    frontend_url: str = "http://localhost:3000"

    # Database: the backend always works over the existing `mansillas` schema.
    database_url: str = ""
    db_schema: str = "mansillas"

    # Development auth stub (see app/deps.py). Ignored in production.
    dev_user_id: int | None = None

    supabase_url: str = ""
    supabase_key: str = ""
    supabase_schema: str = "mansillas"

    @property
    def is_production(self) -> bool:
        return self.app_env.strip().lower() in PRODUCTION_ENVIRONMENTS


settings = Settings()
