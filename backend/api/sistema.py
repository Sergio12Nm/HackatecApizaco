"""Rutas de configuración y diagnóstico del sistema."""

from __future__ import annotations

import platform
import sys
from pathlib import Path

from fastapi import APIRouter

from .. import config
from ..vision import face as face_mod

router = APIRouter(prefix="/api", tags=["sistema"])


@router.get("/config")
def configuracion():
    """Configuración efectiva (sin contraseñas)."""
    return config.resumen()


@router.get("/salud")
def salud():
    """Diagnóstico rápido: modelos disponibles y estado de la base de datos."""
    from ..db import ping

    db_ok, db_msg = ping()
    info = {
        "ok": db_ok,
        "python": sys.version.split()[0],
        "plataforma": f"{platform.system()} {platform.release()}",
        "base_datos": db_msg,
        "reconocimiento_facial": _estado_face(),
        "deteccion_personas": _estado_yolo(),
        "embeddings_registrados": 0,
    }
    if info["reconocimiento_facial"]:
        try:
            info["embeddings_registrados"] = face_mod.numero_embeddings()
        except Exception:
            pass
    return info


def _estado_face() -> str:
    try:
        return "disponible" if face_mod.disponible() else "no disponible"
    except Exception as exc:
        return f"error: {exc}"


def _estado_yolo() -> str:
    from ..vision import detector as det

    try:
        return "disponible" if det.disponible() else "no disponible"
    except Exception as exc:
        return f"error: {exc}"


@router.get("/modelos")
def modelos():
    """Pesos YOLO presentes en la carpeta modelos/."""
    carpeta: Path = config.MODELOS_DIR
    pesos = sorted(p.name for p in carpeta.glob("*.pt"))
    return {
        "carpeta": str(carpeta),
        "pesos_yolo": pesos,
        "yolo_en_uso": Path(config.YOLO_WEIGHTS_RESUELTO).name,
        "modelo_facial": config.FACE_MODEL,
    }
