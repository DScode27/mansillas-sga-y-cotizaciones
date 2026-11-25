from sqlalchemy import BigInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from app.config import settings
from app.db import Base


class Empresa(Base):
    """Client company that owns sedes, empleados and chairs."""

    __tablename__ = "empresa"
    __table_args__ = {"schema": settings.db_schema}

    id_empresa: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    nit: Mapped[str] = mapped_column(String(30), nullable=False, unique=True)
    correo: Mapped[str | None] = mapped_column(String(150))
    telefono: Mapped[str | None] = mapped_column(String(30))
