"""Prueba de RBAC y aislamiento por empresa (HU-22/HU-23, R3/R4).

Mismo enfoque que test_login.py / test_logout.py: SQLite en memoria con el
esquema mínimo, override de get_db y cliente de pruebas de Starlette. Cubre:
  - require_roles deja pasar al rol permitido (200);
  - require_roles bloquea con 403 a un rol autenticado pero no permitido;
  - require_roles responde 401 (no 403) si no hay sesión válida;
  - ensure_same_empresa deja al interno (TECNICO) ver cualquier empresa;
  - ensure_same_empresa deja al externo ver su empresa y bloquea (403) la ajena.

Para ejercer las dependencias montamos rutas de prueba sobre require_roles y
ensure_same_empresa, igual que test_logout.py monta una ruta sobre
get_current_user.

Ejecutar desde backend/:
    .venv/bin/python3.14 test_rbac.py
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import Depends
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool
from starlette.testclient import TestClient

from app.db import get_db
from app.dependencies import ensure_same_empresa, require_roles
from app.main import app
from app.schemas import UsuarioPublico
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


# --- Rutas de prueba sobre las dependencias de la tarea 5 ------------------
# Solo COMERCIAL_MANSILLAS puede entrar aquí (RBAC).
@app.get("/_test/solo-comercial")
def _solo_comercial(
    user: UsuarioPublico = Depends(require_roles("COMERCIAL_MANSILLAS")),
):
    return {"ok": True, "rol": user.rol}


# Recurso ficticio que pertenece a la empresa 10; comprobamos aislamiento.
@app.get("/_test/recurso-empresa-10")
def _recurso_empresa_10(
    user: UsuarioPublico = Depends(require_roles(
        "COMERCIAL_MANSILLAS", "TECNICO", "ADMIN_CLIENTE"
    )),
):
    ensure_same_empresa(user, id_empresa_recurso=10)
    return {"ok": True}


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


# Usuarios de prueba.
comercial = _make_user("Comercial", "comercial@mansillas.com", "COMERCIAL_MANSILLAS", None)
tecnico = _make_user("Tecnico", "tecnico@mansillas.com", "TECNICO", None)
cliente_10 = _make_user("Cliente10", "admin@empresa10.com", "ADMIN_CLIENTE", 10)
cliente_20 = _make_user("Cliente20", "admin@empresa20.com", "ADMIN_CLIENTE", 20)


# 1. RBAC: rol permitido entra (200).
r = client.get("/_test/solo-comercial", headers=_auth(comercial))
_assert(r.status_code == 200, f"COMERCIAL_MANSILLAS accede a ruta permitida (fue {r.status_code})")

# 2. RBAC: rol autenticado pero no permitido -> 403 (no 401).
r = client.get("/_test/solo-comercial", headers=_auth(tecnico))
_assert(r.status_code == 403, f"TECNICO recibe 403 en ruta solo-comercial (fue {r.status_code})")

# 3. RBAC: sin sesión -> 401 (la autenticación va antes que la autorización).
r = client.get("/_test/solo-comercial")
_assert(r.status_code == 401, f"sin token devuelve 401, no 403 (fue {r.status_code})")

# 4. Aislamiento: interno (TECNICO) ve el recurso de cualquier empresa.
r = client.get("/_test/recurso-empresa-10", headers=_auth(tecnico))
_assert(r.status_code == 200, f"TECNICO (interno) ve recurso de la empresa 10 (fue {r.status_code})")

# 5. Aislamiento: externo de la empresa 10 ve su propio recurso.
r = client.get("/_test/recurso-empresa-10", headers=_auth(cliente_10))
_assert(r.status_code == 200, f"ADMIN_CLIENTE de empresa 10 ve su recurso (fue {r.status_code})")

# 6. Aislamiento: externo de otra empresa (20) NO ve el recurso de la 10 -> 403.
r = client.get("/_test/recurso-empresa-10", headers=_auth(cliente_20))
_assert(r.status_code == 403, f"ADMIN_CLIENTE de empresa 20 no ve recurso de la 10 (fue {r.status_code})")

now = datetime.now(timezone.utc).isoformat()
print(f"\nTodas las comprobaciones pasaron ({now}).")
