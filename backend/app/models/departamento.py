from sqlalchemy import BigInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from app.config import settings
from app.db import Base


class Departamento(Base):
    """Area or department of a sede that a chair belongs to."""

    __tablename__ = "departamento"
    __table_args__ = {"schema": settings.db_schema}

    id_departamento: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    id_empresa: Mapped[int] = mapped_column(BigInteger, nullable=False)
    id_sede: Mapped[int] = mapped_column(BigInteger, nullable=False)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
