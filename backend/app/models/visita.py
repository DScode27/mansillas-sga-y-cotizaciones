from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.config import settings
from app.db import Base


class Visita(Base):
    """Scheduled visit where a technician registers the chairs of one sede."""

    __tablename__ = "visita"
    __table_args__ = {"schema": settings.db_schema}

    id_visita: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    id_empresa: Mapped[int] = mapped_column(BigInteger, nullable=False)
    id_sede: Mapped[int] = mapped_column(BigInteger, nullable=False)
    id_comercial: Mapped[int] = mapped_column(BigInteger, nullable=False)
    id_tecnico: Mapped[int] = mapped_column(BigInteger, nullable=False)
    fecha_programada: Mapped[datetime | None] = mapped_column(DateTime)
    cantidad_estimada: Mapped[int] = mapped_column(Integer, nullable=False)
    estado: Mapped[str] = mapped_column(String(20), nullable=False, default="PROGRAMADA")
    observaciones: Mapped[str | None] = mapped_column(Text)
