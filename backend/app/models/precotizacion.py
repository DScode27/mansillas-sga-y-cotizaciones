import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, FetchedValue, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.config import settings
from app.db import Base


class Precotizacion(Base):
    """Reference-only mapping of the pre-quotation table owned by another teammate.

    This module reads `id_precotizacion` (and `id_empresa`) for access logging and
    never inserts or updates rows here.
    """

    __tablename__ = "precotizacion"
    __table_args__ = {"schema": settings.db_schema}

    id_precotizacion: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    id_empresa: Mapped[int] = mapped_column(BigInteger, nullable=False)
    id_visita: Mapped[int] = mapped_column(BigInteger, nullable=False)
    token: Mapped[uuid.UUID] = mapped_column(
        Uuid, nullable=False, unique=True, server_default=FetchedValue()
    )
    estado: Mapped[str] = mapped_column(String(20), nullable=False, default="BORRADOR")
    correo_cliente: Mapped[str | None] = mapped_column(String(150))
    fecha_envio: Mapped[datetime | None] = mapped_column(DateTime)
    fecha_aceptacion: Mapped[datetime | None] = mapped_column(DateTime)
    creada_por: Mapped[int] = mapped_column(BigInteger, nullable=False)
    observaciones: Mapped[str | None] = mapped_column(Text)
    fecha_creacion: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=FetchedValue()
    )
