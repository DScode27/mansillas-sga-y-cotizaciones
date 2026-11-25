from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


def normalizar_database_url(url: str) -> str:
    """Force the `psycopg` (v3) driver required by the design.

    A bare `postgresql://` URL lets SQLAlchemy pick whichever PostgreSQL DBAPI
    happens to be installed, so it is rewritten to `postgresql+psycopg://`.
    """
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


if not settings.database_url:
    raise RuntimeError("DATABASE_URL must be set in backend/.env or the environment")

engine = create_engine(
    normalizar_database_url(settings.database_url),
    pool_pre_ping=True,
    connect_args={"options": f"-c search_path={settings.db_schema}"},
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    """Declarative base shared by every model mapped over the `mansillas` schema."""


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding one SQLAlchemy session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
