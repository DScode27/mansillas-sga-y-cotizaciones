from datetime import datetime

from sqlalchemy import BigInteger, DateTime, FetchedValue, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.config import settings
from app.db import Base


class SesionUsuario(Base):
    """Server-side session for internal users and client administrators (HU-25).

    Only the SHA-256 hash of the signed token is stored, so a leaked database
    dump cannot be replayed as a valid session.
    """

    __tablename__ = "sesion_usuario"
    __table_args__ = {"schema": settings.db_schema}

    id_sesion: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    id_usuario: Mapped[int] = mapped_column(BigInteger, nullable=False)
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    fecha_inicio: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=FetchedValue()
    )
    ultima_actividad: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=FetchedValue()
    )
    fecha_expiracion: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    fecha_cierre: Mapped[datetime | None] = mapped_column(DateTime)
