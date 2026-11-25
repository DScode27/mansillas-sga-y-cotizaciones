from sqlalchemy import BigInteger, Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.config import settings
from app.db import Base


class Usuario(Base):
    """Internal Mansillas user or client administrator/employee account."""

    __tablename__ = "usuario"
    __table_args__ = {"schema": settings.db_schema}

    id_usuario: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    id_empresa: Mapped[int | None] = mapped_column(BigInteger)
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    correo: Mapped[str] = mapped_column(String(150), nullable=False, unique=True)
    password_hash: Mapped[str | None] = mapped_column(Text)
    rol: Mapped[str] = mapped_column(String(30), nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
