from datetime import datetime

from sqlalchemy import BigInteger, DateTime, FetchedValue, String
from sqlalchemy.orm import Mapped, mapped_column

from app.config import settings
from app.db import Base


class AccesoPrecotizacion(Base):
    """One access to a public pre-quotation link, with parsed browser and OS."""

    __tablename__ = "acceso_precotizacion"
    __table_args__ = {"schema": settings.db_schema}

    id_acceso: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    id_precotizacion: Mapped[int] = mapped_column(BigInteger, nullable=False)
    fecha_acceso: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=FetchedValue()
    )
    ip: Mapped[str | None] = mapped_column(String(45))
    navegador: Mapped[str | None] = mapped_column(String(150))
    sistema_operativo: Mapped[str | None] = mapped_column(String(150))
