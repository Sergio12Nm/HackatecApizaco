"""Detector de personas con YOLOv8 (Ultralytics).

El modelo se carga de forma perezosa (solo cuando el motor de visión
necesita detectar por primera vez) para que el arranque de la API sea rápido.
"""

from __future__ import annotations

import logging
import threading

import numpy as np

from .. import config

log = logging.getLogger(__name__)

_model = None
_lock = threading.Lock()
_lock_pred = threading.Lock()   # Ultralytics no es thread-safe en predict()


def _cargar():
    global _model
    with _lock:
        if _model is None:
            from ultralytics import YOLO

            log.info("Cargando YOLO desde %s ...", config.YOLO_WEIGHTS_RESUELTO)
            _model = YOLO(config.YOLO_WEIGHTS_RESUELTO)
            log.info("YOLO listo (clase 0 = persona)")
    return _model


def disponible() -> bool:
    try:
        _cargar()
        return True
    except Exception as exc:  # pragma: no cover
        log.error("No se pudo cargar YOLO: %s", exc)
        return False


def detectar_personas(frame: np.ndarray, conf: float | None = None) -> list[tuple[int, int, int, int]]:
    """Devuelve bboxes (x1, y1, x2, y2) de personas detectadas."""
    if frame is None or frame.size == 0:
        return []

    modelo = _cargar()
    with _lock_pred:
        res = modelo.predict(
            frame,
            classes=[0],                       # 0 = persona en COCO
            conf=config.CONFIANZA_YOLO if conf is None else conf,
            verbose=False,
            device="cpu",
        )[0]

    cajas: list[tuple[int, int, int, int]] = []
    if res.boxes is None:
        return cajas
    for b in res.boxes.xyxy.cpu().numpy():
        x1, y1, x2, y2 = (int(round(float(v))) for v in b[:4])
        if x2 > x1 and y2 > y1:
            cajas.append((x1, y1, x2, y2))
    return cajas
