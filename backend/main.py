"""
Sistema de Videovigilancia con Visión Artificial — Fase 1 (MySQL).

Backend FastAPI:
  - registro de personal autorizado (embeddings faciales, sin reentrenar)
  - definición de zonas restringidas
  - motor de visión en tiempo real (YOLOv8 + InsightFace)
  - historial de eventos con snapshots en MySQL
  - alarmas: sonido del PC + Telegram
"""

from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from . import config
from .alerts.telegram import probar as probar_telegram
from .api import eventos as api_eventos
from .api import camara as api_camara
from .api import personas as api_personas
from .api import sistema as api_sistema
from .api import zonas as api_zonas
from .db import init_db, ping
from .vision.pipeline import monitor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    stream=sys.stdout,
)

# En Windows la consola suele usar cp1252 y los acentos se verían rotos.
for _flujo in (sys.stdout, sys.stderr):
    try:
        _flujo.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):  # pragma: no cover
        pass

log = logging.getLogger("vigilancia")


@asynccontextmanager
async def ciclo_vida(app: FastAPI):
    """Arranque: valida MySQL y enciende el motor de visión."""
    ok, mensaje = ping()
    if ok:
        init_db()
        log.info("Base de datos lista -> %s", mensaje)
    else:
        log.error("MySQL no disponible: %s", mensaje)

    monitor.iniciar()
    log.info("API lista. Documentación: /docs")
    try:
        yield
    finally:
        monitor.detener()
        log.info("Motor de visión detenido")


app = FastAPI(
    title="Vigilancia CV — Fase 1 (MySQL)",
    description=(
        "Detección de personal no autorizado en zonas restringidas usando "
        "cámaras de celular. YOLOv8 + embeddings ArcFace + MySQL."
    ),
    version="1.0.0",
    lifespan=ciclo_vida,
)

# El frontend Streamlit corre en otro puerto; se permite el acceso cruzado.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_personas.router)
app.include_router(api_zonas.router)
app.include_router(api_eventos.router)
app.include_router(api_camara.router)
app.include_router(api_sistema.router)


# ---------------------------------------------------------------------
# Raíz: el frontend real es Streamlit (frontend/app.py)
# ---------------------------------------------------------------------
@app.get("/", include_in_schema=False)
def raiz():
    return JSONResponse(
        {
            "proyecto": "Sistema de Videovigilancia CV — Fase 1",
            "api": "/docs",
            "frontend": "streamlit run frontend/app.py  ->  http://localhost:8501",
            "endpoints": {
                "registrar persona": "POST /api/personas",
                "agregar fotos": "POST /api/personas/{id}/embeddings",
                "listar personas": "GET /api/personas",
                "foto persona": "GET /api/personas/{id}/foto",
                "zonas": "GET|POST /api/zonas",
                "eventos": "GET /api/eventos",
                "snapshot": "GET /api/eventos/{id}/snapshot",
                "stream MJPEG": "GET /api/stream",
                "frame actual": "GET /api/frame",
                "probar fuente": "POST /api/camara/probar",
                "cámaras locales": "GET /api/camaras",
                "cambiar fuente": "POST /api/camara/usar",
                "estado monitor": "GET /api/estado",
                "configuración": "GET /api/config",
                "diagnóstico": "GET /api/salud",
            },
        }
    )


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=204)


@app.get("/telegram/test", include_in_schema=False)
def test_telegram():
    ok, mensaje = probar_telegram()
    return {"ok": ok, "mensaje": mensaje}


if __name__ == "__main__":  # pragma: no cover
    uvicorn.run(
        "backend.main:app",
        host=config._get("API_HOST", "0.0.0.0"),
        port=config._get_int("API_PORT", 8000),
        reload=False,
    )
