"""Conexión a la base de datos con SQLAlchemy Core.

Usamos Core (text() + engine) en vez del ORM: el esquema ya existe en la BD
(backend/database/SQLMansillasSIC.sql) y para un MVP consultas directas son más
simples que mapear todas las tablas.
"""

from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Connection, Engine

from .config import get_settings

_engine: Engine | None = None

# Esquema de la aplicación (ver SQLMansillasSIC.sql).
_SEARCH_PATH = "mansillas, public"


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_engine(
            settings.sqlalchemy_url,
            pool_pre_ping=True,
            # search_path por parámetro de arranque (funciona en conexión directa).
            connect_args={"options": f"-csearch_path={_SEARCH_PATH}"},
        )

        # Supabase suele usarse vía pgbouncer en modo transacción, que ignora el
        # `options` de arranque y reutiliza conexiones entre clientes. Fijamos el
        # search_path dentro de cada transacción con SET LOCAL para no depender de
        # ello ni calificar el esquema en cada consulta.
        @event.listens_for(_engine, "begin")
        def _set_search_path(conn):  # pragma: no cover - efecto de conexión
            conn.exec_driver_sql(f"SET LOCAL search_path TO {_SEARCH_PATH}")

    return _engine


def get_db() -> Iterator[Connection]:
    """Dependencia de FastAPI: entrega una conexión transaccional por request."""
    engine = get_engine()
    with engine.begin() as conn:
        yield conn
