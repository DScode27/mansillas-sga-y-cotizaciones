"""Prueba de logout e inactividad (HU-25, R2) sin depender de la BD remota.

Mismo enfoque que test_login.py: SQLite en memoria con el esquema mínimo,
override de get_db y cliente de pruebas de Starlette. Cubre:
  - logout revoca el token (la siguiente petición da 401);
  - una petición autenticada refresca `ultima_actividad`;
  - la sesión expira por inactividad (petición posterior da 401);
  - un token manipulado/ausente da 401 en un endpoint protegido.

Para ejercitar la inactividad usamos una ruta protegida de prueba montada sobre
get_current_user y manipulamos `ultima_actividad` directamente en la BD.

Ejecutar desde backend/:
    .venv/bin/python3.14 test_logout.py
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool
from starlette.testclient import TestClient

from app.config import get_settings
from app.db import get_db
from app.dependencies import get_current_user
from app.main import app
from app.security import hash_password, hash_token

# --- BD de prueba en memoria ----------------------------------------------

_engine = create_engine(
    "sqlite+pysqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

with _engine.begin() as conn:
    conn.execute(
        text(
            """
            CREATE TABLE usuario (
                id_usuario INTEGER PRIMARY KEY AUTOINCREMENT,
                id_empresa INTEGER,
                nombre TEXT NOT NULL,
                correo TEXT NOT NULL UNIQUE,
                password_hash TEXT,
                rol TEXT NOT NULL,
                activo INTEGER NOT NULL DEFAULT 1
            )
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE TABLE sesion_usuario (
                id_sesion INTEGER PRIMARY KEY AUTOINCREMENT,
                id_usuario INTEGER NOT NULL,
                token_hash TEXT NOT NULL UNIQUE,
                fecha_inicio TEXT NOT NULL,
                ultima_actividad TEXT NOT NULL,
                fecha_expiracion TEXT NOT NULL,
                fecha_cierre TEXT
            )
            """
        )
    )
    conn.execute(
        text(
            "INSERT INTO usuario (id_empresa, nombre, correo, password_hash, rol, activo)"
            " VALUES (NULL, 'Admin', 'admin@mansillas.com', :ph, 'COMERCIAL_MANSILLAS', 1)"
        ),
        {"ph": hash_password("Secreta123")},
    )


def _override_get_db():
    with _engine.begin() as conn:
        yield conn


app.dependency_overrides[get_db] = _override_get_db


# Ruta protegida mínima solo para las pruebas: ejercita get_current_user (la
# misma dependencia que usará RBAC) sin depender de otros endpoints.
from fastapi import Depends  # noqa: E402


@app.get("/_test/me")
def _me(user=Depends(get_current_user)):
    return {"id_usuario": user.id_usuario, "rol": user.rol}


client = TestClient(app)


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)
    print(f"OK  - {msg}")


def _login() -> str:
    r = client.post(
        "/auth/login",
        json={"correo": "admin@mansillas.com", "password": "Secreta123"},
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _last_activity(token: str) -> datetime:
    """`ultima_actividad` como datetime. SQLite la devuelve en texto y, según
    cómo se insertó, con 'T' o con espacio; `fromisoformat` acepta ambos."""
    with _engine.connect() as conn:
        raw = conn.execute(
            text("SELECT ultima_actividad FROM sesion_usuario WHERE token_hash = :h"),
            {"h": hash_token(token)},
        ).scalar()
    return datetime.fromisoformat(raw) if isinstance(raw, str) else raw


# 1. Sin token -> 401 en ruta protegida.
r = client.get("/_test/me")
_assert(r.status_code == 401, f"sin token -> 401 (fue {r.status_code})")

# 2. Token basura -> 401.
r = client.get("/_test/me", headers=_auth("no-es-un-jwt"))
_assert(r.status_code == 401, f"token inválido -> 401 (fue {r.status_code})")

# 3. Token válido -> 200 y refresca ultima_actividad.
token = _login()
# Envejecemos ultima_actividad para notar el refresco (dentro del límite).
with _engine.begin() as conn:
    stale = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    conn.execute(
        text("UPDATE sesion_usuario SET ultima_actividad = :t WHERE token_hash = :h"),
        {"t": stale, "h": hash_token(token)},
    )
before = _last_activity(token)
r = client.get("/_test/me", headers=_auth(token))
_assert(r.status_code == 200, f"token válido -> 200 (fue {r.status_code})")
after = _last_activity(token)
_assert(after > before, "la petición autenticada refresca ultima_actividad")

# 4. Expiración por inactividad: pasamos del límite configurado -> 401.
minutes = get_settings().session_inactivity_minutes
with _engine.begin() as conn:
    expired = (
        datetime.now(timezone.utc) - timedelta(minutes=minutes + 1)
    ).isoformat()
    conn.execute(
        text("UPDATE sesion_usuario SET ultima_actividad = :t WHERE token_hash = :h"),
        {"t": expired, "h": hash_token(token)},
    )
r = client.get("/_test/me", headers=_auth(token))
_assert(r.status_code == 401, f"sesión inactiva -> 401 (fue {r.status_code})")

# 5. Logout revoca el token: la siguiente petición da 401.
token = _login()
r = client.post("/auth/logout", headers=_auth(token))
_assert(r.status_code == 200, f"logout con sesión válida -> 200 (fue {r.status_code})")
with _engine.connect() as conn:
    cerrada = conn.execute(
        text("SELECT fecha_cierre FROM sesion_usuario WHERE token_hash = :h"),
        {"h": hash_token(token)},
    ).scalar()
_assert(cerrada is not None, "logout marca fecha_cierre")
r = client.get("/_test/me", headers=_auth(token))
_assert(r.status_code == 401, f"token revocado -> 401 (fue {r.status_code})")

# 6. Logout sin sesión válida -> 401 (no se puede cerrar lo que no es válido).
r = client.post("/auth/logout", headers=_auth("no-es-un-jwt"))
_assert(r.status_code == 401, f"logout sin token válido -> 401 (fue {r.status_code})")

now = datetime.now(timezone.utc).isoformat()
print(f"\nTodas las comprobaciones pasaron ({now}).")
