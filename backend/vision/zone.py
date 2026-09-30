"""Prueba de pertenencia de una persona a una zona restringida."""

from __future__ import annotations

import json

import cv2
import numpy as np


def cargar_poligono(puntos) -> np.ndarray:
    """[[x,y], ...] -> array OpenCV (N,1,2) int32."""
    pts = np.array(puntos, dtype=np.int32).reshape((-1, 1, 2))
    return pts


def cargar_poligono_json(json_str: str) -> np.ndarray:
    return cargar_poligono(json.loads(json_str))


def punto_en_zona(bbox, poligono_pts: np.ndarray) -> bool:
    """
    bbox = (x1, y1, x2, y2). Se usa el punto de los pies (centro-abajo),
    que es lo que realmente indica si alguien *entró* a la zona.
    """
    cx = int((bbox[0] + bbox[2]) / 2)
    cy = int(bbox[3])
    return cv2.pointPolygonTest(poligono_pts, (cx, cy), False) >= 0


def zona_de_bbox(bbox, zonas) -> tuple | None:
    """zonas = [(id, nombre, poligono), ...]. Devuelve la primera que contiene a la persona."""
    for z in zonas:
        if punto_en_zona(bbox, z[2]):
            return z
    return None


def dibujar_zonas(frame, zonas) -> None:
    """Dibuja los polígonos sobre el frame (modifica in-place)."""
    for z in zonas:
        zid, nombre, poly = z[0], z[1], z[2]
        color = (255, 180, 40)
        cv2.polylines(frame, [poly], True, color, 2)
        pts = poly.reshape((-1, 2))
        if len(pts):
            x, y = int(pts[:, 0].min()), int(pts[:, 1].min())
            cv2.putText(
                frame, f"{nombre} (#{zid})", (x, max(18, y - 8)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2,
            )
