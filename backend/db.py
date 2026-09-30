"""Motor SQLAlchemy + sesión para MySQL."""

from __future__ import annotations

import logging
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from . import config
from .models import Base

log = logging.getLogger(__name__)

# PyMySQL es 100% python: evita tener que compilar mysqlclient en Windows.
DATABASE_URL = (
    f"mysql+pymysql://{config.DB_USER}:{config.DB_PASS}"
    f"@{config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME}?charset=utf8mb4"
)

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,      # detecta conexiones caídas
    pool_recycle=280,        # recicla antes de que MySQL cierre por wait_timeout
    pool_size=10,
    max_overflow=20,
    pool_timeout=30,
    echo=False,
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def init_db() -> None:
    """Crea las tablas que falten (idempotente)."""
    Base.metadata.create_all(bind=engine)


def get_db():
    """Dependencia de FastAPI."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope():
    """Sesión para usar fuera de FastAPI (hilos del motor de visión)."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def ping() -> tuple[bool, str]:
    """Comprueba la conexión. Devuelve (ok, mensaje)."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True, f"MySQL {config.DB_HOST}:{config.DB_PORT} · base {config.DB_NAME}"
    except Exception as exc:  # pragma: no cover
        return False, f"Error de conexión: {exc}"


def estadisticas() -> dict:
    """Contadores de tablas para el panel de ajustes."""
    from sqlalchemy import func, select

    from .models import Embedding, Evento, Persona, Zona

    with session_scope() as db:
        return {
            "personas": db.scalar(select(func.count()).select_from(Persona)) or 0,
            "embeddings": db.scalar(select(func.count()).select_from(Embedding)) or 0,
            "zonas": db.scalar(select(func.count()).select_from(Zona)) or 0,
            "eventos": db.scalar(select(func.count()).select_from(Evento)) or 0,
            "autorizados": db.scalar(
                select(func.count()).select_from(Evento).where(Evento.tipo == "autorizado")
            )
            or 0,
            "no_autorizados": db.scalar(
                select(func.count()).select_from(Evento).where(Evento.tipo == "no_autorizado")
            )
            or 0,
        }
