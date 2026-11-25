"""Seed minimal development data (task 1.6).

Inserts one empresa, one sede, one departamento, one empleado and two users
(COMERCIAL_MANSILLAS and TECNICO) so the API can be exercised locally.

Usage (from `backend/`):
    uv run python database/seed_dev.py
"""

from pathlib import Path
import sys

from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import SessionLocal  # noqa: E402
from app.models import (  # noqa: E402
    Departamento,
    Empleado,
    Empresa,
    Sede,
    Usuario,
)

EMPRESA_NIT = "900123456-1"
CORREO_COMERCIAL = "comercial@mansillas.test"
CORREO_TECNICO = "tecnico@mansillas.test"


def main() -> None:
    with SessionLocal() as db:
        empresa = db.scalar(select(Empresa).where(Empresa.nit == EMPRESA_NIT))
        if empresa is None:
            empresa = Empresa(
                nombre="Cliente Demo SAS",
                nit=EMPRESA_NIT,
                correo="contacto@cliente-demo.test",
            )
            db.add(empresa)
            db.flush()

        sede = db.scalar(
            select(Sede).where(
                Sede.id_empresa == empresa.id_empresa,
                Sede.nombre == "Sede Principal",
            )
        )
        if sede is None:
            sede = Sede(
                id_empresa=empresa.id_empresa,
                nombre="Sede Principal",
                direccion="Calle 1 # 2-3",
                ciudad="Bogotá",
            )
            db.add(sede)
            db.flush()

        departamento = db.scalar(
            select(Departamento).where(
                Departamento.id_empresa == empresa.id_empresa,
                Departamento.id_sede == sede.id_sede,
                Departamento.nombre == "Contabilidad",
            )
        )
        if departamento is None:
            departamento = Departamento(
                id_empresa=empresa.id_empresa,
                id_sede=sede.id_sede,
                nombre="Contabilidad",
            )
            db.add(departamento)
            db.flush()

        empleado = db.scalar(
            select(Empleado).where(
                Empleado.id_empresa == empresa.id_empresa,
                Empleado.documento == "1000000001",
            )
        )
        if empleado is None:
            db.add(
                Empleado(
                    id_empresa=empresa.id_empresa,
                    id_sede=sede.id_sede,
                    id_departamento=departamento.id_departamento,
                    nombre="Ana Pérez",
                    documento="1000000001",
                    correo="ana.perez@cliente-demo.test",
                    cargo="Analista",
                )
            )

        if db.scalar(select(Usuario).where(Usuario.correo == CORREO_COMERCIAL)) is None:
            db.add(
                Usuario(
                    nombre="Comercial Mansillas",
                    correo=CORREO_COMERCIAL,
                    rol="COMERCIAL_MANSILLAS",
                )
            )
        if db.scalar(select(Usuario).where(Usuario.correo == CORREO_TECNICO)) is None:
            db.add(
                Usuario(
                    nombre="Técnico Mansillas",
                    correo=CORREO_TECNICO,
                    rol="TECNICO",
                )
            )

        db.commit()

        comercial = db.scalar(select(Usuario).where(Usuario.correo == CORREO_COMERCIAL))
        tecnico = db.scalar(select(Usuario).where(Usuario.correo == CORREO_TECNICO))
        print("Datos de desarrollo listos")
        print(f"empresa={empresa.id_empresa} sede={sede.id_sede} departamento={departamento.id_departamento}")
        print(f"comercial (id={comercial.id_usuario}): {CORREO_COMERCIAL}")
        print(f"tecnico   (id={tecnico.id_usuario}): {CORREO_TECNICO}")


if __name__ == "__main__":
    main()
