from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

if not settings.database_url:
    raise RuntimeError("DATABASE_URL must be set in backend/.env or the environment")

engine = create_engine(
    settings.database_url,
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
