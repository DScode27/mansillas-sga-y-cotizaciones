from datetime import datetime

from sqlalchemy import BigInteger, DateTime, FetchedValue, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.config import settings
from app.db import Base


class Fotografia(Base):
    """Photograph attached to a chair during the survey (HU-10).

    Maps the existing `fotografia` table unchanged. `id_fotografia` is a
    database identity column and `fecha_subida` has a `CURRENT_TIMESTAMP`
    default, so both are fetched from the server rather than set by the
    backend. Only the file path is stored (`ruta_archivo`); the bytes live in
    the configured photo storage.
    """

    __tablename__ = "fotografia"
    __table_args__ = {"schema": settings.db_schema}

    id_fotografia: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, server_default=FetchedValue()
    )
    id_silla: Mapped[int] = mapped_column(BigInteger, nullable=False)
    ruta_archivo: Mapped[str] = mapped_column(Text, nullable=False)
    fecha_subida: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=FetchedValue()
    )
