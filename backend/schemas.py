"""Esquemas Pydantic (respuestas y validación de la API)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class PersonaOut(BaseModel):
    id: int
    nombre: str
    documento: str | None = None
    cargo: str | None = None
    email: str | None = None
    telefono: str | None = None
    activo: bool = True
    num_embeddings: int = 0


class PersonaUpdate(BaseModel):
    nombre: str = Field(min_length=2, max_length=150)
    documento: str | None = Field(default=None, max_length=50)
    cargo: str | None = Field(default=None, max_length=100)
    email: str | None = Field(default=None, max_length=150)
    telefono: str | None = Field(default=None, max_length=50)


class ZonaOut(BaseModel):
    id: int
    nombre: str
    poligono: list[list[int]]
    camara_id: str = "cam0"


class ZonaCreate(BaseModel):
    nombre: str = Field(min_length=1, max_length=100)
    poligono: list[list[int]] = Field(min_length=3)
    camara_id: str = "cam0"


class EventoOut(BaseModel):
    id: int
    ts: datetime
    persona_id: int | None = None
    nombre: str | None = None
    tipo: str
    zona_id: int | None = None
    zona_nombre: str | None = None
    similitud: float | None = None
    nota: str | None = None
    tiene_snapshot: bool = False


class EstadoMonitor(BaseModel):
    activo: bool
    alarma: bool
    conectado: bool
    fps: float = 0.0
    estado: str = "iniciando"
    fotograma_ts: float | None = None
    detecciones: list[dict] = []
    umbral: float = 0.0
    embeddings: int = 0
    backend_camara: str | None = None
