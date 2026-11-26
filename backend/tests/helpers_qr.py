"""Helpers de prueba para la feature QR público, permisos y tickets.

Agrupa lo que comparten las pruebas de HU-17, HU-18 y HU-24:

- `crear_admin_cliente`: crea un `ADMIN_CLIENTE` ligado a una empresa con la
  `Fabrica` de `conftest.py` (crea la empresa si no se pasa una).
- `EmailSenderFalso` + la fixture `email_falso`: sustituyen `get_email_sender`
  vía `app.dependency_overrides` y capturan cada `(correo, codigo)`, de modo que
  las pruebas leen el OTP en claro del sender sin consultarlo en la BD (donde
  solo vive su hash).
- `ajustar_permiso_qr` + la fixture `con_permiso`: fijan `empresa.permiso_qr`
  con un `UPDATE` directo, cubriendo los tres niveles (1, 2, 3).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest
from sqlalchemy import text

from app.config import settings
from app.main import app
from app.models import Empresa, Usuario
from app.services.email_service import get_email_sender

# Niveles válidos de `empresa.permiso_qr` (CHECK IN (1, 2, 3) en la BD).
NIVELES_PERMISO_QR = (1, 2, 3)


def crear_admin_cliente(
    fabrica,
    empresa: Empresa | None = None,
    nombre: str = "Admin Cliente",
    password: str | None = None,
) -> Usuario:
    """Crea un `ADMIN_CLIENTE` ligado a una empresa usando la `Fabrica`.

    Si no se pasa `empresa`, crea una nueva. Devuelve el `Usuario`; su
    `empresa_id` queda igual a `empresa.id_empresa`, como exige la comprobación
    de autorización de HU-18.
    """
    if empresa is None:
        empresa = fabrica.empresa()
    return fabrica.usuario(
        rol="ADMIN_CLIENTE",
        empresa=empresa,
        nombre=nombre,
        password=password,
    )


@dataclass
class EmailSenderFalso:
    """`EmailSender` falso que captura cada `(correo, codigo)` enviado.

    Satisface el `Protocol` `EmailSender` (`enviar_codigo`). Guarda cada llamada
    en `enviados`, lo que permite a las pruebas recuperar el OTP en claro sin
    leer la columna `codigo_hash` de la BD.
    """

    enviados: list[tuple[str, str]] = field(default_factory=list)

    def enviar_codigo(self, correo: str, codigo: str) -> None:
        self.enviados.append((correo, codigo))

    @property
    def ultimo(self) -> tuple[str, str]:
        """Último `(correo, codigo)` capturado; útil para el flujo típico."""
        return self.enviados[-1]

    def ultimo_codigo(self, correo: str | None = None) -> str:
        """Devuelve el último OTP capturado (opcionalmente filtrando por correo)."""
        if correo is None:
            return self.enviados[-1][1]
        for destino, codigo in reversed(self.enviados):
            if destino == correo:
                return codigo
        raise AssertionError(f"No se capturó ningún OTP para {correo!r}")


@pytest.fixture
def email_falso():
    """Instala un `EmailSenderFalso` vía `app.dependency_overrides`.

    Sustituye `get_email_sender` mientras dure la prueba y lo retira después
    (yield + pop), para no filtrar el override a otras pruebas.
    """
    sender = EmailSenderFalso()
    app.dependency_overrides[get_email_sender] = lambda: sender
    try:
        yield sender
    finally:
        app.dependency_overrides.pop(get_email_sender, None)


def ajustar_permiso_qr(db, empresa: Empresa, permiso: int) -> int:
    """Fija `empresa.permiso_qr` con un `UPDATE` directo (parametrizado).

    Evita el servicio de dominio a propósito: así las pruebas pueden preparar
    cualquiera de los tres niveles (1, 2, 3) sin depender de su validación.
    Devuelve el `permiso` aplicado.
    """
    db.execute(
        text(
            f"UPDATE {settings.db_schema}.empresa "
            "SET permiso_qr = :permiso WHERE id_empresa = :id_empresa"
        ),
        {"permiso": permiso, "id_empresa": empresa.id_empresa},
    )
    db.commit()
    return permiso


@pytest.fixture
def con_permiso(db):
    """Devuelve un ajustador `(empresa, permiso) -> permiso` para las pruebas.

    Envuelve `ajustar_permiso_qr` con la sesión `db`, de modo que un mismo test
    pueda recorrer los tres niveles sobre una o varias empresas.
    """

    def _ajustar(empresa: Empresa, permiso: int) -> int:
        return ajustar_permiso_qr(db, empresa, permiso)

    return _ajustar
