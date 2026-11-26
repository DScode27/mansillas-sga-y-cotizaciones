from datetime import datetime

from sqlalchemy import BigInteger, DateTime, FetchedValue, String
from sqlalchemy.orm import Mapped, mapped_column

from app.config import settings
from app.db import Base


class AceptacionPrecotizacion(Base):
    """Record of a client accepting a pre-quotation (HU-15).

    Maps the existing `aceptacion_precotizacion` table unchanged. `id_aceptacion`
    is a database identity column and `fecha_aceptacion` has a
    `CURRENT_TIMESTAMP` default, so both are fetched from the server. The
    `id_precotizacion` and `id_codigo` columns are UNIQUE, which prevents a
    duplicate acceptance and the reuse of a code across acceptances. The insert
    fires the `registrar_aceptacion_precotizacion` trigger, which validates the
    consumed code and transitions the pre-quotation to `ACEPTADA`.
    """

    __tablename__ = "aceptacion_precotizacion"
    __table_args__ = {"schema": settings.db_schema}

    id_aceptacion: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, server_default=FetchedValue()
    )
    id_precotizacion: Mapped[int] = mapped_column(
        BigInteger, nullable=False, unique=True
    )
    id_codigo: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    nombre_aceptante: Mapped[str] = mapped_column(String(150), nullable=False)
    cargo_aceptante: Mapped[str] = mapped_column(String(100), nullable=False)
    correo_aceptante: Mapped[str] = mapped_column(String(150), nullable=False)
    fecha_aceptacion: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=FetchedValue()
    )
