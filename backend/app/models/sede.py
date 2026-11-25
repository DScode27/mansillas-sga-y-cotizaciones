from sqlalchemy import BigInteger, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.config import settings
from app.db import Base


class Sede(Base):
    """Branch of a client company where chairs are located."""

    __tablename__ = "sede"
    __table_args__ = {"schema": settings.db_schema}

    id_sede: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    id_empresa: Mapped[int] = mapped_column(
        BigInteger, ForeignKey(f"{settings.db_schema}.empresa.id_empresa"), nullable=False
    )
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    direccion: Mapped[str | None] = mapped_column(String(250))
    ciudad: Mapped[str | None] = mapped_column(String(100))
