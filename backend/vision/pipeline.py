"""
Motor de visión: orquesta cámara + YOLO + reconocimiento facial + zonas +
alertas. Corre en un hilo de fondo y publica el último fotograma anotado
para que el frontend (Streamlit) y el stream MJPEG lo consuman.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime

import cv2
import numpy as np

from .. import config
from ..alerts.buzzer import sonar_alarma
from ..alerts.telegram import enviar_alerta
from ..db import session_scope
from ..models import Evento, Zona
from . import face as face_mod
from .detector import detectar_personas
from .zone import cargar_poligono, dibujar_zonas, punto_en_zona

log = logging.getLogger(__name__)

VERDE = (0, 220, 0)
ROJO = (0, 0, 255)
GRIS = (150, 150, 150)
AMARILLO = (0, 200, 255)


class Monitor:
    """Hilo único de análisis. Un solo lector de cámara para todo el sistema."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._frame_lock = threading.Lock()

        self._thread: threading.Thread | None = None
        self._parar = threading.Event()

        self._frame_jpeg: bytes | None = None
        self._frame_ts: float = 0.0

        self._alarma = False
        self._conectado = False
        self._estado = "detenido"
        self._fps = 0.0
        self._fps_real = 0.0
        self._detecciones: list[dict] = []
        self._ultimo_ok = 0.0

        self._ultimo_autorizado: dict[int, float] = {}
        self._ultima_alarma = 0.0
        self._ultimo_error_rostro = 0.0
        self._zonas_cache_ts = 0.0
        self._zonas_cache: list[tuple] = []

    # ---------------------------------------------------------------
    # Control del hilo
    # ---------------------------------------------------------------
    def iniciar(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._parar.clear()
        self._thread = threading.Thread(target=self._bucle, name="monitor-vision", daemon=True)
        self._thread.start()
        log.info("Motor de visión iniciado")

    def detener(self) -> None:
        self._parar.set()
        if self._thread:
            self._thread.join(timeout=3)
        self._conectado = False
        self._estado = "detenido"

    @property
    def vivo(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    # ---------------------------------------------------------------
    # Estado público
    # ---------------------------------------------------------------
    def fotograma(self) -> bytes | None:
        with self._frame_lock:
            return self._frame_jpeg

    def hay_fotograma(self) -> bool:
        with self._frame_lock:
            return self._frame_jpeg is not None

    def alarma(self) -> bool:
        with self._lock:
            return self._alarma

    def estado(self) -> dict:
        with self._lock:
            return {
                "activo": self.vivo,
                "alarma": self._alarma,
                "conectado": self._conectado,
                "fps": round(self._fps, 2),
                "estado": self._estado,
                "fotograma_ts": self._frame_ts or None,
                "detecciones": list(self._detecciones),
                "umbral": config.UMBRAL_FACIAL,
                "embeddings": face_mod.numero_embeddings(),
            }

    def _set_alarma(self, valor: bool) -> None:
        with self._lock:
            self._alarma = valor

    def _set_estado(self, texto: str) -> None:
        with self._lock:
            cambio = texto != self._estado
            self._estado = texto
        if cambio:
            log.info("Motor de visión: %s", texto)

    def _log_rostro(self, exc: Exception) -> None:
        """Log del error de reconocimiento facial, como máximo una vez cada 30 s."""
        ahora = time.time()
        if ahora - self._ultimo_error_rostro < 30.0:
            return
        self._ultimo_error_rostro = ahora
        log.exception("Error de reconocimiento facial: %s", exc)

    # ---------------------------------------------------------------
    # Cámara
    # ---------------------------------------------------------------
    def _abrir_camara(self):
        fuente = config.CAMARA_URL
        try:
            if fuente.isdigit():
                cap = cv2.VideoCapture(int(fuente))
            else:
                cap = cv2.VideoCapture(fuente)
        except Exception as exc:  # pragma: no cover
            log.error("No se pudo abrir la cámara (%s): %s", fuente, exc)
            return None

        if not cap.isOpened():
            try:
                cap.release()
            except Exception:
                pass
            return None

        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        return cap

    # ---------------------------------------------------------------
    # Zonas
    # ---------------------------------------------------------------
    def _zonas(self, forzar: bool = False) -> list[tuple]:
        ahora = time.time()
        if not forzar and (ahora - self._zonas_cache_ts) < config.RECARGA_ZONAS_S:
            return self._zonas_cache
        try:
            with session_scope() as db:
                filas = [(z.id, z.nombre, cargar_poligono(z.puntos())) for z in db.query(Zona).all()]
            self._zonas_cache = filas
            self._zonas_cache_ts = ahora
        except Exception as exc:
            log.error("No se pudieron cargar las zonas: %s", exc)
        return self._zonas_cache

    # ---------------------------------------------------------------
    # Persistencia de eventos
    # ---------------------------------------------------------------
    @staticmethod
    def _guardar_evento(
        persona_id: int | None,
        tipo: str,
        zona_id: int | None,
        similitud: float | None,
        nota: str | None = None,
        snapshot: bytes | None = None,
    ) -> None:
        try:
            with session_scope() as db:
                db.add(
                    Evento(
                        persona_id=persona_id,
                        tipo=tipo,
                        zona_id=zona_id,
                        similitud=similitud,
                        nota=(nota or None) if nota is None or len(nota) <= 255 else nota[:255],
                        snapshot=snapshot,
                    )
                )
        except Exception as exc:
            log.error("No se pudo guardar el evento: %s", exc)

    # ---------------------------------------------------------------
    # Bucle principal
    # ---------------------------------------------------------------
    def _bucle(self) -> None:
        while not self._parar.is_set():
            cap = self._abrir_camara()
            if cap is None:
                self._set_estado(f"Sin señal de cámara ({config.CAMARA_URL})")
                with self._lock:
                    self._conectado = False
                self._parar.wait(config.REINTENTO_CAMARA_S)
                continue

            with self._lock:
                self._conectado = True
            self._set_estado("analizando")
            self._ultimo_ok = time.time()
            intervalo = 1.0 / max(0.5, config.CAMARA_FPS)

            while not self._parar.is_set():
                inicio = time.time()
                ok, frame = cap.read()
                if not ok or frame is None:
                    self._set_estado("cámara desconectada, reintentando...")
                    break

                try:
                    self._procesar(frame)
                except Exception as exc:  # pragma: no cover
                    log.exception("Error procesando fotograma: %s", exc)

                self._ultimo_ok = time.time()
                self._fps_real = 1.0 / max(1e-6, time.time() - inicio)
                # limita la tasa de análisis
                espera = intervalo - (time.time() - inicio)
                if espera > 0:
                    self._parar.wait(espera)

            try:
                cap.release()
            except Exception:
                pass
            with self._lock:
                self._conectado = False

        self._set_estado("detenido")

    # ---------------------------------------------------------------
    # Análisis de un fotograma
    # ---------------------------------------------------------------
    def _procesar(self, frame: np.ndarray) -> None:
        frame = cv2.resize(frame, (config.FRAME_WIDTH, config.FRAME_HEIGHT))
        zonas = self._zonas()

        dibujar_zonas(frame, zonas)

        cajas = detectar_personas(frame)
        ahora = time.time()
        detecciones: list[dict] = []
        alarma = False
        eventos_nuevos: list[tuple] = []

        for bbox in cajas:
            zona = None
            for z in zonas:
                if punto_en_zona(bbox, z[2]):
                    zona = z
                    break

            if zonas and zona is None:
                # persona detectada pero fuera de toda zona restringida
                cv2.rectangle(frame, (bbox[0], bbox[1]), (bbox[2], bbox[3]), GRIS, 2)
                detecciones.append({
                    "bbox": list(bbox), "estado": "fuera_de_zona",
                    "etiqueta": "Fuera de zona", "similitud": None,
                    "persona_id": None, "nombre": None,
                    "zona_id": None, "zona_nombre": None,
                })
                continue

            if not zonas and not config.DETECTAR_SIN_ZONAS:
                continue

            emb = None
            error_rostro = None
            try:
                emb = face_mod.embedding_de_persona(frame, bbox)
            except Exception as exc:
                error_rostro = str(exc)
                self._log_rostro(exc)

            x1, y1, x2, y2 = bbox

            if emb is None:
                etiqueta = "SIN ROSTRO" if error_rostro is None else "ERROR ROSTRO"
                estado = "sin_rostro" if error_rostro is None else "error_rostro"
                color = AMARILLO
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                cv2.putText(frame, etiqueta, (x1, max(14, y1 - 8)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)
                detecciones.append({
                    "bbox": list(bbox), "estado": estado, "etiqueta": etiqueta,
                    "similitud": 0.0, "persona_id": None, "nombre": None,
                    "zona_id": zona[0] if zona else None,
                    "zona_nombre": zona[1] if zona else None,
                })
                if config.ALERTA_SIN_ROSTRO and (ahora - self._ultima_alarma) > config.COOLDOWN_ALARMA_S:
                    self._ultima_alarma = ahora
                    alarma = True
                    nota = ("Error de reconocimiento facial: " + error_rostro
                            if error_rostro else "Persona en zona sin rostro detectable")
                    eventos_nuevos.append((None, "no_autorizado", zona, 0.0, nota, None))
                continue

            persona_id, nombre, sim = face_mod.buscar_persona(emb, config.UMBRAL_FACIAL)

            if persona_id is not None:
                color = VERDE
                etiqueta = f"{nombre} ({sim:.2f})"
                ultimo = self._ultimo_autorizado.get(persona_id, 0.0)
                if (ahora - ultimo) > config.COOLDOWN_AUTORIZADO_S:
                    self._ultimo_autorizado[persona_id] = ahora
                    snapshot = self._jpeg(frame) if config.GUARDAR_SNAPSHOT_AUTORIZADO else None
                    eventos_nuevos.append((persona_id, "autorizado", zona, sim,
                                           "Acceso autorizado", snapshot))
                estado = "autorizado"
            else:
                color = ROJO
                etiqueta = f"NO AUTORIZADO ({sim:.2f})"
                alarma = True
                if (ahora - self._ultima_alarma) > config.COOLDOWN_ALARMA_S:
                    self._ultima_alarma = ahora
                    snapshot = self._jpeg(frame)
                    eventos_nuevos.append((None, "no_autorizado", zona, sim,
                                           "Rostro desconocido en zona restringida", snapshot))
                    if config.ALARMA_SONORA:
                        sonar_alarma()
                    enviar_alerta(
                        snapshot=snapshot,
                        similitud=sim,
                        zona=zona[1] if zona else None,
                        nota=f"bbox={list(bbox)}",
                    )
                estado = "no_autorizado"

            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            cv2.putText(frame, etiqueta, (x1, max(14, y1 - 8)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)

            detecciones.append({
                "bbox": list(bbox), "estado": estado, "etiqueta": etiqueta,
                "similitud": round(sim, 3), "persona_id": persona_id,
                "nombre": nombre, "zona_id": zona[0] if zona else None,
                "zona_nombre": zona[1] if zona else None,
            })

        if alarma:
            self._pintar_alarma(frame)

        # ---- publicar estado ----
        with self._lock:
            self._detecciones = detecciones
            self._fps = 0.7 * self._fps + 0.3 * self._fps_real
        self._set_alarma(alarma)

        jpeg = self._jpeg(frame)
        if jpeg:
            with self._frame_lock:
                self._frame_jpeg = jpeg
                self._frame_ts = time.time()

        # ---- persistir eventos (fuera del camino crítico de video) ----
        for pid, tipo, zona, sim, nota, snapshot in eventos_nuevos:
            self._guardar_evento(
                pid, tipo, zona[0] if zona else None, sim, nota, snapshot
            )

    # ---------------------------------------------------------------
    @staticmethod
    def _jpeg(frame: np.ndarray) -> bytes | None:
        ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), config.CALIDAD_JPEG])
        return buf.tobytes() if ok else None

    @staticmethod
    def _pintar_alarma(frame: np.ndarray) -> None:
        alto = frame.shape[0]
        overlay = frame.copy()
        cv2.rectangle(overlay, (0, 0), (frame.shape[1], 34), (0, 0, 200), -1)
        cv2.addWeighted(overlay, 0.55, frame, 0.45, 0, frame)
        texto = "ALARMA: PERSONA NO AUTORIZADA"
        (tw, th), _ = cv2.getTextSize(texto, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
        x = max(4, (frame.shape[1] - tw) // 2)
        cv2.putText(frame, texto, (x, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        cv2.putText(
            frame, datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            (6, alto - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1,
        )


#: instancia única compartida por la API
monitor = Monitor()


# ---------------------------------------------------------------------
# API antigua conservada por compatibilidad
# ---------------------------------------------------------------------
def get_alarm_state() -> bool:
    return monitor.alarma()


def stream_frames(intervalo_s: float = 0.1):
    """Generador MJPEG que reemite el último fotograma analizado."""
    while True:
        jpeg = monitor.fotograma()
        if jpeg:
            yield (
                b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"
            )
        time.sleep(intervalo_s)
