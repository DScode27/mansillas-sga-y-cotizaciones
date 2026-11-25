"""Prueba de la lógica de login (HU-21, R1) sin depender de la BD remota.

Monta un SQLite en memoria con un esquema mínimo compatible (usuario +
sesion_usuario), inserta usuarios de prueba y ejerce POST /auth/login mediante
el cliente de pruebas de Starlette, sobreescribiendo la dependencia get_db.

Ejecutar desde backend/:
    .venv/bin/python3.14 test_login.py
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool
from starlette.testclient import TestClient

from app.db import get_db
from app.main import app
from app.security import hash_password, hash_token

# --- BD de prueba en memoria ----------------------------------------------
# StaticPool + única conexión para que el :memory: se comparta entre llamadas.

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
    conn.execute(
        text(
            "INSERT INTO usuario (id_empresa, nombre, correo, password_hash, rol, activo)"
            " VALUES (NULL, 'Inactivo', 'inactivo@mansillas.com', :ph, 'TECNICO', 0)"
        ),
        {"ph": hash_password("Secreta123")},
    )
    conn.execute(
        text(
            "INSERT INTO usuario (id_empresa, nombre, correo, password_hash, rol, activo)"
            " VALUES (5, 'Empleado', 'empleado@cliente.com', :ph, 'EMPLEADO_CLIENTE', 1)"
        ),
        {"ph": hash_password("Secreta123")},
    )


def _override_get_db():
    with _engine.begin() as conn:
        yield conn


app.dependency_overrides[get_db] = _override_get_db
client = TestClient(app)


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)
    print(f"OK  - {msg}")


# 1. Credenciales válidas -> 200 + token + usuario + sesión persistida.
r = client.post(
    "/auth/login",
    json={"correo": "admin@mansillas.com", "password": "Secreta123"},
)
_assert(r.status_code == 200, f"login válido devuelve 200 (fue {r.status_code})")
body = r.json()
token = body["access_token"]
_assert(bool(token), "respuesta trae access_token")
_assert(body["token_type"] == "bearer", "token_type es 'bearer'")
_assert(body["usuario"]["rol"] == "COMERCIAL_MANSILLAS", "usuario trae el rol")
_assert("password_hash" not in body["usuario"], "no se filtra password_hash")

with _engine.connect() as conn:
    n = conn.execute(
        text("SELECT COUNT(*) FROM sesion_usuario WHERE token_hash = :h"),
        {"h": hash_token(token)},
    ).scalar()
_assert(n == 1, "se guardó el hash del token en sesion_usuario")

# 2. Contraseña incorrecta -> 401.
r = client.post(
    "/auth/login",
    json={"correo": "admin@mansillas.com", "password": "mala"},
)
_assert(r.status_code == 401, f"contraseña mala devuelve 401 (fue {r.status_code})")

# 3. Correo inexistente -> 401 con el mismo mensaje (no revela la causa).
r2 = client.post(
    "/auth/login",
    json={"correo": "noexiste@mansillas.com", "password": "Secreta123"},
)
_assert(r2.status_code == 401, f"correo inexistente devuelve 401 (fue {r2.status_code})")
_assert(
    r.json()["detail"] == r2.json()["detail"],
    "mismo mensaje para correo y contraseña inválidos",
)

# 4. Usuario inactivo -> 401.
r = client.post(
    "/auth/login",
    json={"correo": "inactivo@mansillas.com", "password": "Secreta123"},
)
_assert(r.status_code == 401, f"usuario inactivo devuelve 401 (fue {r.status_code})")

# 5. Rol sin login por contraseña (EMPLEADO_CLIENTE) -> 401.
r = client.post(
    "/auth/login",
    json={"correo": "empleado@cliente.com", "password": "Secreta123"},
)
_assert(r.status_code == 401, f"EMPLEADO_CLIENTE no inicia por contraseña (fue {r.status_code})")

now = datetime.now(timezone.utc).isoformat()
print(f"\nTodas las comprobaciones pasaron ({now}).")
