from sqlalchemy import BigInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.config import settings
from app.db import Base


class SillaComponente(Base):
    """State of a single chair component (maps the existing
    `silla_componente` table).

    Each row records the evaluated `estado` of one `componente` for one
    `silla`, subject to the table's UNIQUE (id_silla, id_componente)
    constraint and the CHECK on `estado`. No columns are added here: the model
    only maps the existing structure.
    """

    __tablename__ = "silla_componente"
    __table_args__ = {"schema": settings.db_schema}

    id_silla_componente: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    id_silla: Mapped[int] = mapped_column(BigInteger, nullable=False)
    id_componente: Mapped[int] = mapped_column(BigInteger, nullable=False)
    estado: Mapped[str] = mapped_column(String(20), nullable=False)
    observacion: Mapped[str | None] = mapped_column(Text)
