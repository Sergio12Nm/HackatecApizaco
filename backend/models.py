"""
Modelos ORM (SQLAlchemy) — MySQL.

Todo el contenido sensible (fotos de registro y snapshots) vive en MySQL
como LONGBLOB, de modo que un único `mysqldump` respalda el sistema entero.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    func,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

# Las marcas de tiempo usan la hora local del servidor, igual que
# CURRENT_TIMESTAMP de MySQL. Así el backend, la base de datos y el
# frontend muestran siempre la misma hora.
ahora_local = datetime.now

# SQLAlchemy traduce length > 2**24-1 a LONGBLOB en MySQL
LONGBLOB_LEN = 2**32 - 1

#: Dimensión del embedding ArcFace de InsightFace (buffalo_*)
EMBEDDING_DIM = 512
#: bytes por vector: 512 float32
EMBEDDING_BYTES = EMBEDDING_DIM * 4


class Persona(Base):
    __tablename__ = "personas"

    id = Column(Integer, primary_key=True, autoincrement=True)
    nombre = Column(String(150), nullable=False)
    documento = Column(String(50), unique=True)
    cargo = Column(String(100))
    email = Column(String(150))
    telefono = Column(String(50))
    fecha_registro = Column(DateTime, server_default=func.now(), default=ahora_local)
    activo = Column(Boolean, default=True, nullable=False)

    embeddings = relationship(
        "Embedding",
        back_populates="persona",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Persona {self.id} {self.nombre}>"


class Embedding(Base):
    """Vector facial + foto original usada para generarlo."""

    __tablename__ = "embeddings"
    __table_args__ = (Index("idx_emb_persona", "persona_id"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    persona_id = Column(
        Integer, ForeignKey("personas.id", ondelete="CASCADE"), nullable=False
    )
    vector = Column(LargeBinary(length=EMBEDDING_BYTES), nullable=False)
    foto = Column(LargeBinary(length=LONGBLOB_LEN))
    foto_mime = Column(String(50), default="image/jpeg")

    persona = relationship("Persona", back_populates="embeddings")


class Zona(Base):
    __tablename__ = "zonas"

    id = Column(Integer, primary_key=True, autoincrement=True)
    nombre = Column(String(100), nullable=False)
    poligono = Column(Text, nullable=False)          # JSON: [[x,y], [x,y], ...]
    camara_id = Column(String(50), default="cam0")
    creado = Column(DateTime, server_default=func.now(), default=ahora_local)

    def puntos(self) -> list[list[int]]:
        import json

        try:
            data = json.loads(self.poligono)
            return [[int(p[0]), int(p[1])] for p in data]
        except Exception:  # pragma: no cover
            return []


class Evento(Base):
    __tablename__ = "eventos"
    __table_args__ = (
        Index("idx_eventos_ts", "timestamp"),
        Index("idx_eventos_tipo", "tipo"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, server_default=func.now(), default=ahora_local, index=True)
    persona_id = Column(Integer, ForeignKey("personas.id", ondelete="SET NULL"))
    tipo = Column(Enum("autorizado", "no_autorizado", name="tipo_evento"), nullable=False)
    zona_id = Column(Integer, ForeignKey("zonas.id", ondelete="SET NULL"))
    similitud = Column(Float)
    nota = Column(String(255))
    snapshot = Column(LargeBinary(length=LONGBLOB_LEN))


class LogRegistro(Base):
    __tablename__ = "logs_registro"

    id = Column(Integer, primary_key=True, autoincrement=True)
    persona_id = Column(Integer, ForeignKey("personas.id", ondelete="SET NULL"))
    ts = Column(DateTime, server_default=func.now(), default=ahora_local)
    embeddings_creados = Column(Integer)
    mensaje = Column(String(255))
