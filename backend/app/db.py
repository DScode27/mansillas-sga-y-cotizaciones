"""Database access with SQLAlchemy over the existing `mansillas` schema.

The engine keeps two safety nets so queries always see the application schema,
even behind Supabase's pgbouncer in transaction mode (where startup `options`
are ignored):
  * `connect_args` sets `search_path` when the connection is created.
  * a `begin` listener runs `SET LOCAL search_path` inside every transaction.
"""

from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings, normalizar_database_url

__all__ = [
    "Base",
    "SessionLocal",
    "engine",
    "get_db",
    "get_engine",
    "normalizar_database_url",
]

_engine: Engine | None = None


def get_engine() -> Engine:
    """Build (once) the engine for the configured database."""
    global _engine
    if _engine is None:
        actual = get_settings()
        if not actual.database_url:
            raise RuntimeError(
                "DATABASE_URL must be set in backend/.env or the environment"
            )

        # libpq splits `options` on spaces, so the list must not contain any.
        search_path_option = f"{actual.db_schema},public"
        search_path_sql = f"{actual.db_schema}, public"
        _engine = create_engine(
            actual.sqlalchemy_url,
            pool_pre_ping=True,
            connect_args={"options": f"-csearch_path={search_path_option}"},
        )

        @event.listens_for(_engine, "begin")
        def _set_search_path(conn) -> None:  # pragma: no cover - connection effect
            conn.exec_driver_sql(f"SET LOCAL search_path TO {search_path_sql}")

    return _engine


engine = get_engine()
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
