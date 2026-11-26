from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.config import settings
from app.db import Base


class CodigoVerificacion(Base):
    """One-time verification code (OTP) stored as a hash.

    The SQL `CHECK` requires exactly one of `id_precotizacion` / `id_empleado`
    to be non-null; the database enforces it, so it is not replicated here. In
    this feature the row always uses `id_empleado` (with `id_precotizacion`
    left as NULL).
    """

    __tablename__ = "codigo_verificacion"
    __table_args__ = {"schema": settings.db_schema}

    id_codigo: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    id_precotizacion: Mapped[int | None] = mapped_column(BigInteger)
    id_empleado: Mapped[int | None] = mapped_column(BigInteger)
    correo_destino: Mapped[str] = mapped_column(String(150), nullable=False)
    codigo_hash: Mapped[str] = mapped_column(Text, nullable=False)
    fecha_expiracion: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    utilizado: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
