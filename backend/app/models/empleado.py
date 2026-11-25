from sqlalchemy import BigInteger, Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.config import settings
from app.db import Base


class Empleado(Base):
    """Client employee; the source of a chair's empresa, sede, departamento and cargo."""

    __tablename__ = "empleado"
    __table_args__ = {"schema": settings.db_schema}

    id_empleado: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    id_empresa: Mapped[int] = mapped_column(BigInteger, nullable=False)
    id_sede: Mapped[int] = mapped_column(BigInteger, nullable=False)
    id_departamento: Mapped[int] = mapped_column(BigInteger, nullable=False)
    id_usuario: Mapped[int | None] = mapped_column(BigInteger)
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    documento: Mapped[str | None] = mapped_column(String(30))
    correo: Mapped[str | None] = mapped_column(String(150))
    cargo: Mapped[str] = mapped_column(String(100), nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
