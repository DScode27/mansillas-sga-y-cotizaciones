from sqlalchemy import BigInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from app.config import settings
from app.db import Base


class Componente(Base):
    """Catalog component evaluated in a chair checklist.

    Maps the existing `componente` table, whose five rows are seeded by the
    schema ('Cilindros', 'Ruedas', 'Bases', 'Asiento / Espaldar', 'Malla').
    The backend only reads this catalog, so no new columns or constraints are
    declared beyond those already present in the table.
    """

    __tablename__ = "componente"
    __table_args__ = {"schema": settings.db_schema}

    id_componente: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
