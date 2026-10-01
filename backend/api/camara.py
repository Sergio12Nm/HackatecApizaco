"""Prueba y cambio de la fuente de video en caliente (sin reiniciar el backend)."""

from __future__ import annotations

import logging
import os

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from .. import config
from ..vision.pipeline import monitor, probar_fuente

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["camara"])


class FuenteBody(BaseModel):
    fuente: str


@router.get("/camaras")
def listar_camaras(maximo: int = Query(4, ge=1, le=8)):
    """Prueba los índices locales 0..maximo-1 y dice cuáles entregan imagen."""
    return {"camaras": [
        probar_fuente(str(i), presupuesto_s=4.0, intentos_lectura=3)
        for i in range(maximo)
    ]}


@router.post("/camara/probar")
def probar_camara(datos: FuenteBody):
    """Prueba una fuente cualquiera (índice, URL o archivo) y devuelve preview."""
    return probar_fuente(datos.fuente)


def _guardar_fuente_en_env(fuente: str) -> None:
    """Reescribe la línea CAMARA_URL de .env para que el cambio sobreviva."""
    ruta = config.BASE_DIR / ".env"
    linea_nueva = f"CAMARA_URL={fuente}\n"
    if not ruta.exists():
        ruta.write_text(linea_nueva, encoding="utf-8")
        return
    salida, cambiada = [], False
    for ln in ruta.read_text(encoding="utf-8").splitlines(keepends=True):
        cuerpo = ln.strip()
        if (not cambiada and cuerpo and not cuerpo.startswith("#")
                and cuerpo.split("=", 1)[0].strip() == "CAMARA_URL"):
            salida.append(linea_nueva)
            cambiada = True
        else:
            salida.append(ln if ln.endswith("\n") else ln + "\n")
    if not cambiada:
        salida.append(linea_nueva)
    ruta.write_text("".join(salida), encoding="utf-8")


@router.post("/camara/usar")
def usar_fuente(datos: FuenteBody):
    """Cambia la fuente activa del motor sin reiniciar el backend."""
    fuente = (datos.fuente or "").strip()
    if not fuente:
        raise HTTPException(400, "Indica la fuente: 0, una URL o la ruta de un video")
    prueba = probar_fuente(fuente)
    if not prueba["ok"]:
        raise HTTPException(400, f"Esa fuente no entrega imagen: {prueba['mensaje']}")
    fuente = prueba["fuente"]  # ya normalizada (p. ej. con http:// antepuesto)
    _guardar_fuente_en_env(fuente)
    os.environ["CAMARA_URL"] = fuente
    config.CAMARA_URL = fuente
    monitor.detener()
    monitor.iniciar()
    log.info("Fuente de video cambiada a %s (%s)", fuente, prueba.get("backend"))
    return {"ok": True, "fuente": fuente,
            "mensaje": f"Fuente cambiada a {fuente} ({prueba.get('backend')}). Motor reiniciado."}
