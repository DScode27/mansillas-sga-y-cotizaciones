import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, FetchedValue, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.config import settings
from app.db import Base


class Silla(Base):
    """Chair registered during a visit.

    `numero_qr` and `codigo_qr` are assigned by the database (`secuencia_qr`
    sequence plus the `generar_codigo_qr` trigger), and `token_publico` by its
    `gen_random_uuid()` column default. The backend never computes them, so
    those columns are marked as fetched from the server.
    """

    __tablename__ = "silla"
    __table_args__ = {"schema": settings.db_schema}

    id_silla: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    id_empresa: Mapped[int] = mapped_column(BigInteger, nullable=False)
    id_visita: Mapped[int] = mapped_column(BigInteger, nullable=False)
    id_sede: Mapped[int] = mapped_column(BigInteger, nullable=False)
    id_departamento: Mapped[int] = mapped_column(BigInteger, nullable=False)
    id_empleado: Mapped[int] = mapped_column(BigInteger, nullable=False)
    cargo: Mapped[str] = mapped_column(String(100), nullable=False)
    numero_qr: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=FetchedValue()
    )
    codigo_qr: Mapped[str] = mapped_column(String(30), nullable=False, unique=True)
    token_publico: Mapped[uuid.UUID] = mapped_column(
        Uuid, nullable=False, unique=True, server_default=FetchedValue()
    )
    serial_antiguo: Mapped[str | None] = mapped_column(String(100))
    observaciones: Mapped[str | None] = mapped_column(Text)
    estado: Mapped[str] = mapped_column(String(25), nullable=False, default="REGISTRADA")
    fecha_registro: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=FetchedValue()
    )
