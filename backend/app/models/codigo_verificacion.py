from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, FetchedValue, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.config import settings
from app.db import Base


class CodigoVerificacion(Base):
    """One-time verification code (OTP) for a pre-quotation or an employee.

    Maps the existing `codigo_verificacion` table unchanged. `id_codigo` is a
    database identity column (fetched from the server). Only a hashed
    representation of the code is stored in `codigo_hash`, never the plain OTP.
    The SQL `CHECK` requires exactly one of `id_precotizacion` / `id_empleado`
    to be non-null; the database enforces it, so it is not replicated here.
    Pre-quotation acceptance (HU-15) sets `id_precotizacion`; the employee OTP
    flow (HU-24) sets `id_empleado`.
    """

    __tablename__ = "codigo_verificacion"
    __table_args__ = {"schema": settings.db_schema}

    id_codigo: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, server_default=FetchedValue()
    )
    id_precotizacion: Mapped[int | None] = mapped_column(BigInteger)
    id_empleado: Mapped[int | None] = mapped_column(BigInteger)
    correo_destino: Mapped[str] = mapped_column(String(150), nullable=False)
    codigo_hash: Mapped[str] = mapped_column(Text, nullable=False)
    fecha_expiracion: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    utilizado: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
