"""Test fixtures for the Mansillas backend.

The suite runs against a disposable PostgreSQL database: `TEST_DATABASE_URL`
must point to a database where it is safe to drop and recreate the `mansillas`
schema. The application engine is pointed at that same database before any
`app.*` module is imported.
"""

import itertools
import os
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
SQL_FILE = BACKEND_DIR / "database" / "SQLMansillasSIC.sql"

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
if not TEST_DATABASE_URL:
    raise RuntimeError(
        "TEST_DATABASE_URL is required: point it to a disposable PostgreSQL "
        "database, e.g. postgresql+psycopg://postgres@127.0.0.1:55432/mansillas_test"
    )

os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["APP_ENV"] = "testing"
os.environ.setdefault("FRONTEND_URL", "http://localhost:5173")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.db import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import (  # noqa: E402
    Departamento,
    Empleado,
    Empresa,
    Sede,
    Silla,
    Usuario,
    Visita,
)

TABLAS = (
    "acceso_precotizacion",
    "cotizacion",
    "aceptacion_precotizacion",
    "codigo_verificacion",
    "precotizacion",
    "fotografia",
    "silla_componente",
    "silla",
    "visita",
    "empleado",
    "usuario",
    "departamento",
    "sede",
    "empresa",
    "carga_excel",
    "ticket",
    "comentario_ticket",
    "sesion_usuario",
)


def _sentencias(sql: str) -> list[str]:
    """Split a SQL script on `;`, ignoring comments and `$$ ... $$` bodies."""
    sentencias: list[str] = []
    actual: list[str] = []
    indice = 0
    dentro_de_bloque = False

    while indice < len(sql):
        if sql.startswith("$$", indice):
            dentro_de_bloque = not dentro_de_bloque
            actual.append("$$")
            indice += 2
            continue

        caracter = sql[indice]
        if not dentro_de_bloque and sql.startswith("--", indice):
            fin = sql.find("\n", indice)
            indice = len(sql) if fin == -1 else fin + 1
            continue

        if not dentro_de_bloque and caracter == ";":
            sentencia = "".join(actual).strip()
            if sentencia:
                sentencias.append(sentencia)
            actual = []
            indice += 1
            continue

        actual.append(caracter)
        indice += 1

    resto = "".join(actual).strip()
    if resto:
        sentencias.append(resto)
    return sentencias


@pytest.fixture(scope="session", autouse=True)
def _esquema():
    with engine.connect() as conexion:
        conexion.execute(text("SET search_path TO public"))
        conexion.execute(text("DROP SCHEMA IF EXISTS mansillas CASCADE"))
        conexion.commit()
        for sentencia in _sentencias(SQL_FILE.read_text(encoding="utf-8")):
            conexion.execute(text(sentencia))
        conexion.commit()
    yield


@pytest.fixture(autouse=True)
def _limpiar_tablas():
    with engine.begin() as conexion:
        conexion.execute(
            text(
                "TRUNCATE TABLE "
                + ", ".join(f"mansillas.{tabla}" for tabla in TABLAS)
                + " RESTART IDENTITY CASCADE"
            )
        )
        conexion.execute(text("ALTER SEQUENCE mansillas.secuencia_qr RESTART WITH 1"))


@pytest.fixture
def db():
    sesion = SessionLocal()
    try:
        yield sesion
    finally:
        sesion.close()


@pytest.fixture
def cliente():
    with TestClient(app) as test_client:
        yield test_client


class Fabrica:
    """Small factory for the shared rows every scenario needs."""

    def __init__(self, db) -> None:
        self.db = db
        self._secuencia = itertools.count(1)

    def _siguiente(self) -> int:
        return next(self._secuencia)

    def empresa(self, nombre: str = "Cliente") -> Empresa:
        numero = self._siguiente()
        empresa = Empresa(
            nombre=f"{nombre} {numero}",
            nit=f"900{numero:06d}-{numero % 10}",
            correo=f"cliente{numero}@test.local",
        )
        self.db.add(empresa)
        self.db.commit()
        self.db.refresh(empresa)
        return empresa

    def sede(self, empresa: Empresa, nombre: str = "Sede") -> Sede:
        numero = self._siguiente()
        sede = Sede(
            id_empresa=empresa.id_empresa,
            nombre=f"{nombre} {numero}",
            direccion="Calle 1 # 2-3",
            ciudad="Bogotá",
        )
        self.db.add(sede)
        self.db.commit()
        self.db.refresh(sede)
        return sede

    def departamento(
        self, empresa: Empresa, sede: Sede, nombre: str = "Área"
    ) -> Departamento:
        numero = self._siguiente()
        departamento = Departamento(
            id_empresa=empresa.id_empresa,
            id_sede=sede.id_sede,
            nombre=f"{nombre} {numero}",
        )
        self.db.add(departamento)
        self.db.commit()
        self.db.refresh(departamento)
        return departamento

    def usuario(
        self,
        rol: str = "TECNICO",
        empresa: Empresa | None = None,
        nombre: str = "Usuario",
    ) -> Usuario:
        numero = self._siguiente()
        usuario = Usuario(
            id_empresa=empresa.id_empresa if empresa is not None else None,
            nombre=f"{nombre} {numero}",
            correo=f"usuario{numero}@test.local",
            rol=rol,
            activo=True,
        )
        self.db.add(usuario)
        self.db.commit()
        self.db.refresh(usuario)
        return usuario

    def empleado(
        self,
        empresa: Empresa,
        sede: Sede,
        departamento: Departamento,
        cargo: str = "Analista",
    ) -> Empleado:
        numero = self._siguiente()
        empleado = Empleado(
            id_empresa=empresa.id_empresa,
            id_sede=sede.id_sede,
            id_departamento=departamento.id_departamento,
            nombre=f"Empleado {numero}",
            documento=f"10{numero:08d}",
            correo=f"empleado{numero}@test.local",
            cargo=cargo,
            activo=True,
        )
        self.db.add(empleado)
        self.db.commit()
        self.db.refresh(empleado)
        return empleado

    def visita(
        self,
        empresa: Empresa,
        sede: Sede,
        comercial: Usuario,
        tecnico: Usuario,
        cantidad_estimada: int = 10,
    ) -> Visita:
        visita = Visita(
            id_empresa=empresa.id_empresa,
            id_sede=sede.id_sede,
            id_comercial=comercial.id_usuario,
            id_tecnico=tecnico.id_usuario,
            cantidad_estimada=cantidad_estimada,
            estado="PROGRAMADA",
        )
        self.db.add(visita)
        self.db.commit()
        self.db.refresh(visita)
        return visita

    def silla(
        self,
        visita: Visita,
        empleado: Empleado,
        serial_antiguo: str | None = None,
        cargo: str | None = None,
    ) -> Silla:
        silla = Silla(
            id_empresa=visita.id_empresa,
            id_visita=visita.id_visita,
            id_sede=empleado.id_sede,
            id_departamento=empleado.id_departamento,
            id_empleado=empleado.id_empleado,
            cargo=cargo or empleado.cargo,
            codigo_qr="",
            serial_antiguo=serial_antiguo,
        )
        self.db.add(silla)
        self.db.commit()
        self.db.refresh(silla)
        return silla

    def escenario(self, tecnico: Usuario | None = None) -> dict:
        """Empresa + sede + departamento + empleado + comercial + visita."""
        empresa = self.empresa()
        sede = self.sede(empresa)
        departamento = self.departamento(empresa, sede)
        empleado = self.empleado(empresa, sede, departamento)
        comercial = self.usuario("COMERCIAL_MANSILLAS")
        if tecnico is None:
            tecnico = self.usuario("TECNICO")
        visita = self.visita(empresa, sede, comercial, tecnico)
        return {
            "empresa": empresa,
            "sede": sede,
            "departamento": departamento,
            "empleado": empleado,
            "comercial": comercial,
            "tecnico": tecnico,
            "visita": visita,
        }


@pytest.fixture
def fabrica(db) -> Fabrica:
    return Fabrica(db)


@pytest.fixture
def auth():
    """Headers used by the development auth stub."""

    def _auth(usuario: Usuario) -> dict[str, str]:
        return {"X-Dev-User-Id": str(usuario.id_usuario)}

    return _auth
