"""
Embeddings faciales (InsightFace / ArcFace) y búsqueda por similitud coseno.

Idea central del proyecto: NO se reentrena ningún modelo. Cada rostro se
convierte en un vector de 512 dimensiones que se guarda en MySQL. En tiempo
real se calcula el embedding del rostro detectado y se compara con todos los
vectores guardados:

    similitud >= UMBRAL_FACIAL  ->  autorizado
    similitud <  UMBRAL_FACIAL  ->  no autorizado / desconocido

Registrar una persona nueva es, por tanto, un simple INSERT.
"""

from __future__ import annotations

import logging
import threading
import time

import numpy as np

from .. import config
from ..db import session_scope
from ..models import EMBEDDING_DIM, Embedding, Persona

log = logging.getLogger(__name__)

_app = None
_lock_app = threading.Lock()


# ---------------------------------------------------------------------
# Carga perezosa del modelo
# ---------------------------------------------------------------------
def _cargar_app():
    global _app
    with _lock_app:
        if _app is None:
            from insightface.app import FaceAnalysis

            log.info("Cargando InsightFace (%s) ...", config.FACE_MODEL)
            app = FaceAnalysis(
                name=config.FACE_MODEL,
                providers=["CPUExecutionProvider"],
            )
            try:
                app.prepare(ctx_id=0, det_size=(640, 640))
            except TypeError:  # firmas distintas entre versiones
                try:
                    app.prepare(ctx_id=0)
                except TypeError:
                    app.prepare()
            _app = app
            log.info("InsightFace listo")
    return _app


def disponible() -> bool:
    """True si el motor de reconocimiento facial puede usarse."""
    try:
        _cargar_app()
        return True
    except Exception as exc:  # pragma: no cover
        log.error("InsightFace no disponible: %s", exc)
        return False


# ---------------------------------------------------------------------
# Generación de embeddings
# ---------------------------------------------------------------------
def _mayor_rostro(faces):
    return max(
        faces,
        key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]),
    )


def _embedding_de_rostro(rostro) -> np.ndarray | None:
    emb = getattr(rostro, "normed_embedding", None)
    if emb is None:
        emb = getattr(rostro, "embedding", None)
    if emb is None:
        return None
    vec = np.asarray(emb, dtype=np.float32).reshape(-1)
    if vec.size != EMBEDDING_DIM:
        log.warning("Embedding con dimensión inesperada: %s (esperado %s)", vec.size, EMBEDDING_DIM)
        return None
    norm = float(np.linalg.norm(vec))
    if norm > 0:
        vec = vec / norm
    return vec


def generar_embedding(frame_bgr: np.ndarray, min_px: int | None = None) -> np.ndarray | None:
    """Devuelve el embedding normalizado del rostro más grande de la imagen."""
    if frame_bgr is None or frame_bgr.size == 0:
        return None
    min_px = config.ROSTRO_MIN_PX if min_px is None else min_px

    app = _cargar_app()
    faces = app.get(frame_bgr)
    if not faces:
        return None

    rostro = _mayor_rostro(faces)
    ancho = float(rostro.bbox[2] - rostro.bbox[0])
    alto = float(rostro.bbox[3] - rostro.bbox[1])
    if min(ancho, alto) < min_px:
        return None
    return _embedding_de_rostro(rostro)


def roi_con_margen(bbox, ancho_frame: int, alto_frame: int, margen: float | None = None):
    """Amplía el recorte de la persona para no cortar el rostro."""
    margen = config.MARGEN_ROI if margen is None else margen
    x1, y1, x2, y2 = bbox
    dx = int((x2 - x1) * margen)
    dy = int((y2 - y1) * margen * 0.5)
    x1 = max(0, x1 - dx)
    y1 = max(0, y1 - dy)
    x2 = min(ancho_frame - 1, x2 + dx)
    y2 = min(alto_frame - 1, y2 + int((y2 - y1) * 0.15))
    return x1, y1, x2, y2


def embedding_de_persona(frame, bbox, min_px: int | None = None) -> np.ndarray | None:
    """Rostro dentro del bbox de una persona; si no hay, busca en toda la imagen."""
    min_px = config.ROSTRO_MIN_PX if min_px is None else min_px
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = roi_con_margen(bbox, w, h)
    emb = generar_embedding(frame[y1:y2, x1:x2], min_px=min_px)
    if emb is None and min_px > 0:
        # segundo intento con un mínimo de tamaño más permisivo
        emb = generar_embedding(frame[y1:y2, x1:x2], min_px=max(8, min_px // 2))
    return emb


# ---------------------------------------------------------------------
# Comparación por similitud coseno
# ---------------------------------------------------------------------
_cache_lock = threading.Lock()
_cache_matriz: np.ndarray | None = None
_cache_ids: list[int] = []
_cache_ts: float = 0.0
_cache_log_ultimo: int = -1


def invalidar_cache() -> None:
    """Fuerza la recarga de embeddings (tras registrar una persona)."""
    global _cache_ts
    with _cache_lock:
        _cache_ts = 0.0
    log.info("Caché de embeddings invalidada")


def _cargar_cache(forzar: bool = False) -> np.ndarray:
    """Matriz (N, 512) con los embeddings de las personas activas."""
    global _cache_matriz, _cache_ids, _cache_ts, _cache_log_ultimo

    with _cache_lock:
        fresca = (time.time() - _cache_ts) < config.CACHE_EMBEDDINGS_S
        if _cache_matriz is not None and fresca and not forzar:
            return _cache_matriz

        filas = []
        ids = []
        with session_scope() as db:
            consulta = (
                db.query(Embedding, Persona)
                .join(Persona, Embedding.persona_id == Persona.id)
                .filter(Persona.activo.is_(True))
                .all()
            )
            for emb, persona in consulta:
                try:
                    vec = np.frombuffer(emb.vector, dtype=np.float32)
                except Exception:
                    continue
                if vec.size != EMBEDDING_DIM:
                    continue
                filas.append(vec)
                ids.append(persona.id)

        if filas:
            matriz = np.vstack(filas).astype(np.float32)
            # normalización por fila (por si algún vector llegó sin normalizar)
            norms = np.linalg.norm(matriz, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            matriz = matriz / norms
        else:
            matriz = np.zeros((0, EMBEDDING_DIM), dtype=np.float32)

        _cache_matriz = matriz
        _cache_ids = ids
        _cache_ts = time.time()
        # solo se avisa cuando el número de personas cambia: si no, el TTL
        # llenaría el log cada CACHE_EMBEDDINGS_S sin decir nada nuevo
        if matriz.shape[0] != _cache_log_ultimo:
            _cache_log_ultimo = matriz.shape[0]
            log.info("Caché de embeddings: %d vectores", matriz.shape[0])
        return matriz


def numero_embeddings() -> int:
    return _cargar_cache().shape[0]


def mejor_coincidencia(emb: np.ndarray, forzar: bool = False):
    """
    (persona_id, nombre, similitud) del registrado más parecido, SIN umbral.
    Sirve para mensajes del tipo "parecido a Juan (0.47)" cuando no se autoriza.
    """
    matriz = _cargar_cache(forzar=forzar)
    if matriz.shape[0] == 0 or emb is None:
        return None, None, 0.0

    vec = np.asarray(emb, dtype=np.float32).reshape(-1)
    n = float(np.linalg.norm(vec))
    if n > 0:
        vec = vec / n

    similitudes = matriz @ vec
    idx = int(np.argmax(similitudes))
    mejor = float(similitudes[idx])

    pid = _cache_ids[idx]
    with session_scope() as db:
        persona = db.get(Persona, pid)
        if persona is None:
            return None, None, mejor
        return persona.id, persona.nombre, mejor


def buscar_persona(emb: np.ndarray, umbral: float | None = None, forzar: bool = False):
    """
    Compara el embedding contra todos los vectors activos.
    Devuelve (persona_id, nombre, similitud) — persona_id=None si no supera el umbral.
    """
    umbral = config.UMBRAL_FACIAL if umbral is None else umbral
    persona_id, nombre, mejor = mejor_coincidencia(emb, forzar=forzar)
    if persona_id is None or mejor < umbral:
        return None, None, mejor

    with session_scope() as db:
        persona = db.get(Persona, persona_id)
        if persona is None or not persona.activo:
            return None, None, mejor
        return persona.id, persona.nombre, mejor


def nombre_de_persona(persona_id: int | None) -> str | None:
    if not persona_id:
        return None
    with session_scope() as db:
        p = db.get(Persona, persona_id)
        return p.nombre if p else None
