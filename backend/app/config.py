"""Application configuration loaded from environment variables and backend/.env."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
PRODUCTION_ENVIRONMENTS = {"production", "prod"}


def normalizar_database_url(url: str) -> str:
    """Force the `psycopg` (v3) driver required by the design.

    A bare `postgresql://` URL lets SQLAlchemy pick whichever PostgreSQL DBAPI
    happens to be installed, so it is rewritten to `postgresql+psycopg://`.
    """
    limpia = url.strip().strip('"').strip("'")
    if limpia.startswith("postgresql://"):
        return "postgresql+psycopg://" + limpia[len("postgresql://") :]
    return limpia


class Settings(BaseSettings):
    """Runtime configuration; no secret lives in source code."""

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

    # Database: the backend always works over the existing `mansillas` schema.
    database_url: str = ""
    db_schema: str = "mansillas"

    # Development auth stub (see app/deps.py). Ignored in production.
    dev_user_id: int | None = None

    # CORS: origin of the Vite frontend.
    frontend_url: str = "http://localhost:5173"

    # JWT and sessions (HU-21 login, HU-25 logout/inactivity).
    jwt_secret: str = "cambia-esto-en-produccion-por-un-secreto-largo-de-48-bytes"
    jwt_algorithm: str = "HS256"
    session_inactivity_minutes: int = 30
    session_max_hours: int = 12

    supabase_url: str = ""
    supabase_key: str = ""
    supabase_schema: str = "mansillas"

    # SMTP for OTP email delivery (HU-24). Empty host => development log sender.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "no-reply@mansillas.local"

    # One-time password (OTP) parameters for public QR tickets.
    otp_ttl_minutes: int = 10
    otp_length: int = 6

    @property
    def is_production(self) -> bool:
        return self.app_env.strip().lower() in PRODUCTION_ENVIRONMENTS

    @property
    def sqlalchemy_url(self) -> str:
        return normalizar_database_url(self.database_url)

    @property
    def cors_origins(self) -> list[str]:
        origins = {
            self.frontend_url.rstrip("/"),
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        }
        return sorted(origen for origen in origins if origen)


@lru_cache
def get_settings() -> Settings:
    return Settings()


# Module-level instance kept for the modules that import `settings` directly.
settings = get_settings()
