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

    # Chair photographs (HU-10). Files live on local disk; only the relative
    # path is stored in `fotografia.ruta_archivo`. `photo_storage_dir` is
    # resolved under BACKEND_DIR when relative.
    photo_storage_dir: str = "var/fotos"
    photo_max_bytes: int = 10 * 1024 * 1024  # 10 MB per photo
    photo_allowed_formats: tuple[str, ...] = ("JPEG", "PNG", "WEBP")

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

    # SMTP for the pre-quotation link email (HU-13). No credentials in source;
    # all come from the environment. Missing config does not stop the app; a
    # send attempt without enough config returns a controlled error.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_tls: bool = True  # STARTTLS; a secure connection is never silently downgraded
    smtp_timeout: float = 10.0
    # Public proposal path appended to FRONTEND_URL for the link (provisional).
    proposal_path: str = "/propuesta"

    # OTP for pre-quotation acceptance (HU-15). Only the SECRET is configurable
    # from the environment; it is INDEPENDENT of `jwt_secret` and empty by
    # default, so the app starts without it, but OTP operations fail with a
    # controlled error when it is missing/insecure. The numeric OTP parameters
    # are fixed, documented MVP constants and live in `app/services/otp.py`
    # (not env-overridable).
    otp_secret: str = ""

    @property
    def smtp_configurado(self) -> bool:
        """True when the minimum SMTP settings to send are present."""
        return bool(self.smtp_host and self.smtp_from)

    @property
    def is_production(self) -> bool:
        return self.app_env.strip().lower() in PRODUCTION_ENVIRONMENTS

    @property
    def photo_storage_path(self) -> Path:
        """Absolute photo storage directory (relative paths resolve under BACKEND_DIR)."""
        base = Path(self.photo_storage_dir)
        return base if base.is_absolute() else (BACKEND_DIR / base)

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
