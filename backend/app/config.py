"""Configuración de la aplicación leída desde el .env.

Centraliza las variables de entorno con pydantic-settings para que el resto de
la app no lea os.environ directamente.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "MansillasSIC"
    app_env: str = "development"
    debug: bool = True

    host: str = "127.0.0.1"
    port: int = 8000

    # Base de datos (Supabase/PostgreSQL). El .env puede traerla con el driver
    # "postgresql://"; la normalizamos a "postgresql+psycopg://" para SQLAlchemy 2.
    database_url: str

    # CORS: origen del frontend Vite.
    frontend_url: str = "http://localhost:5173"

    # JWT
    jwt_secret: str = "cambia-esto-en-produccion"
    jwt_algorithm: str = "HS256"

    # Minutos de inactividad antes de cerrar la sesión (HU-25, configurable).
    session_inactivity_minutes: int = 30
    # Vida máxima absoluta de la sesión en horas.
    session_max_hours: int = 12

    @property
    def sqlalchemy_url(self) -> str:
        url = self.database_url.strip().strip('"').strip("'")
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+psycopg://", 1)
        return url

    @property
    def cors_origins(self) -> list[str]:
        origins = {self.frontend_url}
        # Orígenes de desarrollo habituales de Vite.
        origins.add("http://localhost:5173")
        origins.add("http://127.0.0.1:5173")
        return [o for o in origins if o]


@lru_cache
def get_settings() -> Settings:
    return Settings()
