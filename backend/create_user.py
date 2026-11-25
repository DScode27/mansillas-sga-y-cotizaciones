"""Utilidad de bootstrap para crear un usuario con contraseña hasheada.

La gestión de usuarios por UI es HU-20 (tarea 6). Mientras tanto, este script
permite crear el primer usuario interno para probar el login (tarea 2).

Uso (desde backend/, con el venv):
    .venv/bin/python3.14 create_user.py \
        --nombre "Admin" --correo admin@mansillas.com \
        --password "Secreta123" --rol COMERCIAL_MANSILLAS

Para roles de cliente (ADMIN_CLIENTE/EMPLEADO_CLIENTE) pasar --empresa <id>.
"""

from __future__ import annotations

import argparse

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.db import get_engine
from app.security import hash_password

_ROLES = (
    "COMERCIAL_MANSILLAS",
    "TECNICO",
    "ADMIN_CLIENTE",
    "EMPLEADO_CLIENTE",
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Crear un usuario de MansillasSIC")
    parser.add_argument("--nombre", required=True)
    parser.add_argument("--correo", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--rol", required=True, choices=_ROLES)
    parser.add_argument(
        "--empresa",
        type=int,
        default=None,
        help="id_empresa (obligatorio para roles de cliente)",
    )
    parser.add_argument(
        "--reset-password",
        action="store_true",
        help="si el correo ya existe, actualiza su contraseña en vez de fallar",
    )
    args = parser.parse_args()

    es_cliente = args.rol in ("ADMIN_CLIENTE", "EMPLEADO_CLIENTE")
    if es_cliente and args.empresa is None:
        parser.error("Los roles de cliente requieren --empresa")
    if not es_cliente and args.empresa is not None:
        parser.error("Los roles internos no llevan --empresa (debe ser NULL)")

    engine = get_engine()
    password_hash = hash_password(args.password)

    if args.reset_password:
        with engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    UPDATE usuario
                       SET password_hash = :password_hash,
                           nombre = :nombre,
                           activo = TRUE
                     WHERE correo = :correo
                 RETURNING id_usuario
                    """
                ),
                {
                    "correo": args.correo,
                    "nombre": args.nombre,
                    "password_hash": password_hash,
                },
            ).scalar_one_or_none()
        if row is None:
            print(f"No existe ningún usuario con correo {args.correo}.")
            raise SystemExit(1)
        print(f"Contraseña actualizada: id_usuario={row}, correo={args.correo}")
        return

    try:
        with engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    INSERT INTO usuario (id_empresa, nombre, correo, password_hash, rol)
                    VALUES (:id_empresa, :nombre, :correo, :password_hash, :rol)
                    RETURNING id_usuario
                    """
                ),
                {
                    "id_empresa": args.empresa,
                    "nombre": args.nombre,
                    "correo": args.correo,
                    "password_hash": password_hash,
                    "rol": args.rol,
                },
            ).scalar_one()
    except IntegrityError:
        print(
            f"Ya existe un usuario con correo {args.correo}. "
            "Usa --reset-password para cambiarle la contraseña."
        )
        raise SystemExit(1)
    print(f"Usuario creado: id_usuario={row}, correo={args.correo}, rol={args.rol}")


if __name__ == "__main__":
    main()
