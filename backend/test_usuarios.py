"""Prueba de gestión de usuarios (HU-20, R5) sin depender de la BD remota.

Mismo enfoque que test_login.py / test_rbac.py: SQLite en memoria con el esquema
mínimo, override de get_db y cliente de pruebas de Starlette. Cubre:
  - solo COMERCIAL_MANSILLAS crea/lista usuarios (otro rol → 403, sin token → 401);
  - crear un usuario interno guarda la contraseña hasheada y con él se hace login;
  - rol de cliente sin id_empresa → 400; rol interno con id_empresa → 400;
  - correo duplicado → 409;
  - asignar rol a un usuario inexistente → 404.

Ejecutar desde backend/:
    .venv/bin/python3.14 test_usuarios.py
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool
from starlette.testclient import TestClient

from app.db import get_db
from app.main import app
from app.security import create_access_token, hash_token, session_expiry

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


def _override_get_db():
    with _engine.begin() as conn:
        yield conn


app.dependency_overrides[get_db] = _override_get_db

client = TestClient(app)


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)
    print(f"OK  - {msg}")


def _make_user(nombre: str, correo: str, rol: str, id_empresa):
    """Inserta un usuario + sesión válida y devuelve su token Bearer."""
    with _engine.begin() as conn:
        res = conn.execute(
            text(
                "INSERT INTO usuario (id_empresa, nombre, correo, password_hash, rol, activo)"
                " VALUES (:emp, :nombre, :correo, 'x', :rol, 1)"
            ),
            {"emp": id_empresa, "nombre": nombre, "correo": correo, "rol": rol},
        )
        id_usuario = res.lastrowid
        now = datetime.now(timezone.utc)
        expires_at = session_expiry(now)
        token = create_access_token(
            id_usuario=id_usuario, rol=rol, expires_at=expires_at
        )
        conn.execute(
            text(
                "INSERT INTO sesion_usuario"
                " (id_usuario, token_hash, fecha_inicio, ultima_actividad, fecha_expiracion)"
                " VALUES (:u, :h, :ini, :act, :exp)"
            ),
            {
                "u": id_usuario,
                "h": hash_token(token),
                "ini": now.isoformat(),
                "act": now.isoformat(),
                "exp": expires_at.isoformat(),
            },
        )
    return token


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# Administrador (interno) y un técnico que no debe poder gestionar usuarios.
comercial = _make_user("Comercial", "comercial@mansillas.com", "COMERCIAL_MANSILLAS", None)
tecnico = _make_user("Tecnico", "tecnico@mansillas.com", "TECNICO", None)


# 1. RBAC: sin token -> 401.
r = client.get("/usuarios")
_assert(r.status_code == 401, f"sin token listar usuarios devuelve 401 (fue {r.status_code})")

# 2. RBAC: rol no permitido -> 403.
r = client.get("/usuarios", headers=_auth(tecnico))
_assert(r.status_code == 403, f"TECNICO no puede listar usuarios, 403 (fue {r.status_code})")

# 3. COMERCIAL_MANSILLAS crea un usuario interno (sin empresa).
r = client.post(
    "/usuarios",
    headers=_auth(comercial),
    json={
        "nombre": "Nueva Tecnica",
        "correo": "nueva@mansillas.com",
        "password": "secreto123",
        "rol": "TECNICO",
        "id_empresa": None,
    },
)
_assert(r.status_code == 201, f"crear usuario interno devuelve 201 (fue {r.status_code})")
creado = r.json()
_assert(creado["id_empresa"] is None, "usuario interno queda sin id_empresa")
_assert("password_hash" not in creado, "la respuesta no expone password_hash")

# 4. La contraseña quedó hasheada y sirve para iniciar sesión con ella.
r = client.post("/auth/login", json={"correo": "nueva@mansillas.com", "password": "secreto123"})
_assert(r.status_code == 200, f"el usuario creado puede iniciar sesión (fue {r.status_code})")
with _engine.begin() as conn:
    stored = conn.execute(
        text("SELECT password_hash FROM usuario WHERE correo = 'nueva@mansillas.com'")
    ).scalar()
_assert(stored not in (None, "secreto123") and stored.startswith("$2"),
        "la contraseña se guardó como hash bcrypt, no en claro")

# 5. El usuario aparece en el listado.
r = client.get("/usuarios", headers=_auth(comercial))
_assert(r.status_code == 200, f"COMERCIAL_MANSILLAS lista usuarios, 200 (fue {r.status_code})")
correos = {u["correo"] for u in r.json()}
_assert("nueva@mansillas.com" in correos, "el usuario creado aparece en el listado")

# 6. Regla rol/empresa: rol de cliente sin id_empresa -> 400.
r = client.post(
    "/usuarios",
    headers=_auth(comercial),
    json={
        "nombre": "Admin Cliente",
        "correo": "admincli@empresa.com",
        "password": "secreto123",
        "rol": "ADMIN_CLIENTE",
        "id_empresa": None,
    },
)
_assert(r.status_code == 400, f"rol de cliente sin empresa devuelve 400 (fue {r.status_code})")

# 7. Regla rol/empresa: rol interno con id_empresa -> 400.
r = client.post(
    "/usuarios",
    headers=_auth(comercial),
    json={
        "nombre": "Interno Malo",
        "correo": "interno@mansillas.com",
        "password": "secreto123",
        "rol": "COMERCIAL_MANSILLAS",
        "id_empresa": 5,
    },
)
_assert(r.status_code == 400, f"rol interno con empresa devuelve 400 (fue {r.status_code})")

# 8. Correo duplicado -> 409.
r = client.post(
    "/usuarios",
    headers=_auth(comercial),
    json={
        "nombre": "Otra",
        "correo": "nueva@mansillas.com",
        "password": "secreto123",
        "rol": "TECNICO",
        "id_empresa": None,
    },
)
_assert(r.status_code == 409, f"correo duplicado devuelve 409 (fue {r.status_code})")

# 9. Asignar rol a usuario inexistente -> 404.
r = client.put(
    "/usuarios/99999/rol",
    headers=_auth(comercial),
    json={"rol": "TECNICO", "id_empresa": None},
)
_assert(r.status_code == 404, f"asignar rol a inexistente devuelve 404 (fue {r.status_code})")

now = datetime.now(timezone.utc).isoformat()
print(f"\nTodas las comprobaciones pasaron ({now}).")
