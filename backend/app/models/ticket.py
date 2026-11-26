from datetime import datetime

from sqlalchemy import BigInteger, DateTime, FetchedValue, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.config import settings
from app.db import Base


class Ticket(Base):
    """Support ticket for a chair.

    `id_usuario` is NULL when the ticket is created through the public QR flow
    (the employee is identified by OTP, not by a logged-in user). The database
    assigns `fecha_creacion` via its `CURRENT_TIMESTAMP` default, so that column
    is marked as fetched from the server and read back with `db.refresh(...)`.
    """

    __tablename__ = "ticket"
    __table_args__ = {"schema": settings.db_schema}

    id_ticket: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    id_silla: Mapped[int] = mapped_column(BigInteger, nullable=False)
    id_usuario: Mapped[int | None] = mapped_column(BigInteger)  # NULL en flujo QR
    asunto: Mapped[str] = mapped_column(String(150), nullable=False)
    descripcion: Mapped[str] = mapped_column(Text, nullable=False)
    estado: Mapped[str] = mapped_column(String(20), nullable=False, default="ABIERTO")
    fecha_creacion: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=FetchedValue()
    )


class ComentarioTicket(Base):
    """Comment attached to a ticket.

    Mapped for completeness of the `mansillas` schema; it is not used by this
    feature. `fecha_creacion` is assigned by the database default.
    """

    __tablename__ = "comentario_ticket"
    __table_args__ = {"schema": settings.db_schema}

    id_comentario: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    id_ticket: Mapped[int] = mapped_column(BigInteger, nullable=False)
    id_usuario: Mapped[int | None] = mapped_column(BigInteger)
    comentario: Mapped[str] = mapped_column(Text, nullable=False)
    fecha_creacion: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=FetchedValue()
    )
