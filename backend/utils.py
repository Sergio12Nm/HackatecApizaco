"""Utilidades compartidas: codificación de imágenes y conversión de buffers."""

from __future__ import annotations

import json
from typing import Iterable

import cv2
import numpy as np


def bytes_a_imagen(data: bytes, flags: int = cv2.IMREAD_COLOR) -> np.ndarray | None:
    """Decodifica bytes (JPEG/PNG) a un array BGR."""
    if not data:
        return None
    arr = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(arr, flags)
    return img


def imagen_a_jpeg(img: np.ndarray, calidad: int = 85) -> bytes | None:
    ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), int(calidad)])
    return buf.tobytes() if ok else None


def poligono_valido(puntos: Iterable) -> bool:
    """Un polígono necesita al menos 3 puntos [x, y] con enteros."""
    try:
        pts = list(puntos)
    except TypeError:
        return False
    if len(pts) < 3:
        return False
    for p in pts:
        if not isinstance(p, (list, tuple)) or len(p) < 2:
            return False
        float(p[0]), float(p[1])
    return True


def normalizar_poligono(puntos: Iterable) -> list[list[int]]:
    return [[int(round(float(p[0]))), int(round(float(p[1])))] for p in puntos]


def poligono_a_json(puntos: Iterable) -> str:
    return json.dumps(normalizar_poligono(puntos))
