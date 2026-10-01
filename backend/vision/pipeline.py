"""
Motor de visión: orquesta cámara + YOLO + reconocimiento facial + zonas +
alertas. Corre en un hilo de fondo y publica el último fotograma anotado
para que el frontend (Streamlit) y el stream MJPEG lo consuman.
"""

from __future__ import annotations

import base64
import logging
import os
import threading
import time
from datetime import datetime

import cv2
import numpy as np
import requests

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

_NOMBRE_BACKEND = {
    cv2.CAP_ANY: "auto",
    cv2.CAP_DSHOW: "dshow",
    cv2.CAP_MSMF: "msmf",
}


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
        self._ultimo_hash: int | None = None
        self._repetidos = 0
        # backends de captura a probar, en orden (solo webcam local)
        self._flags_local = self._orden_flags()
        self._flag_idx = 0
        self._fallos_apertura = 0
        self._backend_en_uso: str | None = None
        self._zonas_cache_ts = 0.0
        self._zonas_cache: list[tuple] = []

    # ---------------------------------------------------------------
    # Control del hilo
    # ---------------------------------------------------------------
    def iniciar(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._parar.clear()
        self._set_estado("iniciando")
        self._thread = threading.Thread(target=self._bucle, name="monitor-vision", daemon=True)
        self._thread.start()
        log.info("Motor de visión iniciado")

    def detener(self) -> None:
        self._parar.set()
        if self._thread:
            self._thread.join(timeout=3)
        with self._lock:
            self._conectado = False
            self._estado = "detenido"
            self._detecciones = []
            self._fps = 0.0
        # se suelta el último fotograma: si no, el panel seguiría mostrando una
        # imagen congelada aunque el motor esté apagado
        with self._frame_lock:
            self._frame_jpeg = None
            self._frame_ts = 0.0

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
                "backend_camara": self._backend_en_uso,
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
    @staticmethod
    def _flag_backend():
        """Backend de captura pedido en .env (auto = que decida OpenCV)."""
        return {
            "dshow": cv2.CAP_DSHOW,
            "msmf": cv2.CAP_MSMF,
        }.get(config.CAMARA_BACKEND, cv2.CAP_ANY)

    @classmethod
    def _orden_flags(cls) -> list:
        """El configurado primero; luego los demás como plan B."""
        primero = cls._flag_backend()
        orden = [primero]
        for flag in (cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY):
            if flag not in orden:
                orden.append(flag)
        return orden

    def _abrir_camara(self):
        fuente = config.CAMARA_URL
        local = fuente.isdigit()
        flag = self._flags_local[self._flag_idx] if local else cv2.CAP_ANY
        try:
            if local:
                cap = cv2.VideoCapture(int(fuente), flag)
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

        # El tamaño de buffer de OpenCV solo tiene sentido en fuentes de
        # red/archivo: en la webcam local (DSHOW/MSMF) puede dejar el flujo
        # congelado al cabo de un rato.
        if not local:
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self._backend_en_uso = _NOMBRE_BACKEND.get(flag, str(flag))
        return cap

    def _rotar_backend_si_toca(self) -> None:
        """
        Si la webcam local falla al abrir (o abre sin entregar imagen) varias
        veces seguidas, prueba con otro backend de captura. En Windows un
        dispositivo MSMF invalidado a veces responde con DSHOW y viceversa.
        """
        if not str(config.CAMARA_URL).isdigit():
            return
        if self._fallos_apertura < config.CAMARA_BACKEND_REINTENTOS:
            return
        self._fallos_apertura = 0
        self._flag_idx = (self._flag_idx + 1) % len(self._flags_local)
        log.warning(
            "La cámara %s no responde con %s: se probará con %s",
            config.CAMARA_URL,
            self._backend_en_uso,
            _NOMBRE_BACKEND.get(self._flags_local[self._flag_idx], "?"),
        )

    @staticmethod
    def _liberar(cap) -> None:
        try:
            cap.release()
        except Exception:
            pass

    def _leer(self, cap, intentos: int | None = None):
        """
        Lee un fotograma reintentando.

        En Windows la webcam local abre bien pero el primer read() falla
        mientras Media Foundation negocia el dispositivo. Con un solo intento
        el motor declaraba la cámara desconectada y, al reabrirla
        inmediatamente, el dispositivo se quedaba bloqueado para siempre.
        """
        intentos = intentos or config.CAMARA_LECTURA_INTENTOS
        for i in range(intentos):
            try:
                ok, frame = cap.read()
            except Exception as exc:  # pragma: no cover
                log.error("Fallo leyendo de la cámara: %s", exc)
                return False, None
            if ok and frame is not None:
                return True, frame
            if i < intentos - 1:
                self._parar.wait(config.CAMARA_LECTURA_ESPERA_S)
        return False, None

    def _es_nuevo(self, frame: np.ndarray) -> bool:
        """
        True si el fotograma cambió respecto al anterior.

        Una webcam atascada devuelve el MISMO buffer una y otra vez con
        ok=True: el stream parece "conectado" pero la imagen está congelada
        (y las alertas se repiten sobre la foto vieja). El hash es barato
        porque se muestrea 1 de cada 16 píxeles; el ruido del sensor hace
        casi imposible un falso positivo en una escena real.
        """
        try:
            h = hash(frame[::16, ::16].tobytes())
        except Exception:
            return True
        if h == self._ultimo_hash:
            self._repetidos += 1
        else:
            self._ultimo_hash = h
            self._repetidos = 0
        return self._repetidos == 0

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
                    self._detecciones = []
                self._fallos_apertura += 1
                self._rotar_backend_si_toca()
                self._parar.wait(config.REINTENTO_CAMARA_S)
                continue

            # Espera activa al primer fotograma. Si la cámara abre pero no
            # entrega imagen, NO se reabre al instante: se suelta, se espera y
            # se reintenta, que es lo que evita el bloqueo permanente de la
            # webcam local en Windows.
            ok, frame = self._leer(cap)
            if not ok or frame is None:
                self._set_estado("cámara abierta pero sin imagen, reintentando...")
                with self._lock:
                    self._conectado = False
                    self._detecciones = []
                self._liberar(cap)
                self._fallos_apertura += 1
                self._rotar_backend_si_toca()
                self._parar.wait(config.REINTENTO_CAMARA_S)
                continue

            with self._lock:
                self._conectado = True
            self._set_estado("analizando")
            self._ultimo_ok = time.time()
            self._ultimo_hash = None
            self._repetidos = 0
            self._fallos_apertura = 0
            self._flag_idx = 0
            intervalo = 1.0 / max(0.5, config.CAMARA_FPS)

            while not self._parar.is_set():
                inicio = time.time()

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
                if self._parar.is_set():
                    break

                ok, frame = self._leer(cap)
                if not ok or frame is None:
                    self._set_estado("cámara desconectada, reintentando...")
                    break
                if not self._es_nuevo(frame) and self._repetidos >= config.CAMARA_CONGELADA_MAX:
                    log.warning(
                        "La cámara (%s) devolvió %d fotogramas idénticos: "
                        "se reabre el dispositivo",
                        config.CAMARA_URL, self._repetidos,
                    )
                    self._set_estado("cámara congelada (imagen repetida), reintentando...")
                    break

            self._liberar(cap)
            with self._lock:
                self._conectado = False
                self._detecciones = []
            # respiro entre reconexiones: reabrir en bucle deja el dispositivo
            # bloqueado y la cámara no vuelve nunca
            if not self._parar.is_set():
                self._parar.wait(config.REINTENTO_CAMARA_S)

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
# Fotograma de cortesía
# ---------------------------------------------------------------------
_PLACEHOLDERS: dict[str, bytes] = {}


def fotograma_aviso(mensaje: str, sub: str = "") -> bytes:
    """
    JPEG con un aviso, para que el stream MJPEG nunca se quede en negro
    cuando no hay cámara. Se cachea: solo se dibuja una vez por mensaje.
    """
    clave = f"{mensaje}|{sub}"
    if clave in _PLACEHOLDERS:
        return _PLACEHOLDERS[clave]

    ancho, alto = config.FRAME_WIDTH, config.FRAME_HEIGHT
    frame = np.full((alto, ancho, 3), 32, np.uint8)
    cv2.rectangle(frame, (0, 0), (ancho, 4), (0, 165, 255), -1)
    cv2.putText(frame, "SISTEMA DE VIGILANCIA", (24, 52),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (170, 170, 170), 1, cv2.LINE_AA)
    cv2.putText(frame, mensaje, (24, alto // 2),
                cv2.FONT_HERSHEY_SIMPLEX, 0.75, (60, 60, 255), 2, cv2.LINE_AA)
    if sub:
        cv2.putText(frame, sub, (24, alto // 2 + 34),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1, cv2.LINE_AA)
    cv2.putText(frame, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), (24, alto - 18),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (140, 140, 140), 1, cv2.LINE_AA)

    ok, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
    jpeg = buffer.tobytes() if ok else b""
    if jpeg:
        _PLACEHOLDERS[clave] = jpeg
    return jpeg


# ---------------------------------------------------------------------
# API antigua conservada por compatibilidad
# ---------------------------------------------------------------------
def get_alarm_state() -> bool:
    return monitor.alarma()


def stream_frames(intervalo_s: float = 0.1):
    """
    Generador MJPEG que reemite el último fotograma analizado.

    Si el motor está detenido o la cámara no responde, emite un fotograma de
    aviso con el motivo. Sin esto el navegador se queda en blanco y no se
    puede distinguir "cargando" de "fallando".
    """
    while True:
        jpeg = monitor.fotograma()
        if not jpeg:
            estado = monitor.estado()
            if not estado["activo"]:
                # cv2.putText no dibuja acentos: el texto del recuadro va en ASCII
                jpeg = fotograma_aviso("MOTOR DETENIDO", "Pulsa 'Iniciar motor' en el panel")
            else:
                jpeg = fotograma_aviso("SIN SENAL DE CAMARA", estado["estado"])
        yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"
        time.sleep(intervalo_s)


# ---------------------------------------------------------------------
# Sondeo de fuentes (para probar cámaras sin reiniciar el backend)
# ---------------------------------------------------------------------
def _sondear_cv(fuente: str, flags: list, intentos_lectura: int,
                limite: float, salida: dict) -> None:
    """Abre la fuente con OpenCV y lee hasta conseguir un fotograma."""
    for flag in flags:
        if time.time() > limite:
            break
        nombre = _NOMBRE_BACKEND.get(flag, str(flag))
        if nombre in salida["probados"]:
            continue
        salida["probados"].append(nombre)
        try:
            cap = cv2.VideoCapture(int(fuente), flag) if fuente.isdigit() else cv2.VideoCapture(fuente)
        except Exception as exc:
            salida["detalle"] = f"{nombre}: {exc}"
            continue
        try:
            if not cap.isOpened():
                salida["detalle"] = f"{nombre}: no abre el dispositivo"
                continue
            ok, frame = False, None
            for _ in range(intentos_lectura):
                if time.time() > limite:
                    break
                try:
                    ok, frame = cap.read()
                except Exception:
                    ok, frame = False, None
                if ok and frame is not None:
                    break
                time.sleep(0.2)
            if not (ok and frame is not None):
                salida["detalle"] = f"{nombre}: abre pero no entrega imagen"
                continue
            h, w = frame.shape[:2]
            chica = frame if w <= 320 else cv2.resize(frame, (320, max(1, int(h * 320 / w))))
            _, buf = cv2.imencode(".jpg", chica, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
            salida["ok"] = True
            salida["frames"] = 1
            salida["ancho"] = w
            salida["alto"] = h
            salida["backend"] = nombre
            salida["preview"] = base64.b64encode(buf.tobytes()).decode("ascii")
            salida["detalle"] = f"OK ({w}x{h} por {nombre})"
            return
        finally:
            try:
                cap.release()
            except Exception:
                pass


def probar_fuente(fuente: str, presupuesto_s: float = 12.0,
                  intentos_lectura: int = 5) -> dict:
    """
    Prueba una fuente de video sin tocar el monitor en marcha.

    Acepta un índice local ("0"), una URL http(s)/rtsp o la ruta de un
    archivo. Devuelve un dict con ok, mensaje, tamaño, backend usado y una
    vista previa en base64 para mostrarla en el panel.
    """
    fuente = (fuente or "").strip()
    t0 = time.time()
    res: dict = {"ok": False, "fuente": fuente, "frames": 0, "ancho": 0,
                 "alto": 0, "backend": None, "preview": None,
                 "mensaje": "", "ms": 0, "probados": []}

    def fin(mensaje: str) -> dict:
        res["mensaje"] = mensaje
        res["ms"] = int((time.time() - t0) * 1000)
        res.pop("probados", None)
        return res

    if not fuente:
        return fin("Indica una fuente: 0, una URL o la ruta de un video")
    # Error típico: pegar "192.168.1.50:8080/video" sin el esquema. OpenCV lo
    # tomaría como ruta de archivo y fallaría sin decir por qué.
    if (":" in fuente and "://" not in fuente and not fuente.isdigit()
            and not os.path.exists(fuente)):
        fuente = "http://" + fuente
        res["fuente"] = fuente
    es_url = fuente.lower().startswith(("http://", "https://", "rtsp://"))
    if not fuente.isdigit() and not es_url and not os.path.exists(fuente):
        return fin(f"No existe el archivo: {fuente}")

    # URLs http: primero un chequeo rápido de alcance; si el host ni
    # responde, no tiene sentido bloquear a OpenCV intentando abrir.
    if fuente.lower().startswith(("http://", "https://")):
        try:
            with requests.get(fuente, stream=True, timeout=5) as r:
                if r.status_code >= 400:
                    return fin(f"La URL respondió HTTP {r.status_code} "
                               f"(¿puerto o ruta del stream incorrectos?)")
                try:
                    next(r.iter_content(chunk_size=65536))
                except StopIteration:
                    return fin("La URL conecta pero no envía datos")
        except Exception as exc:
            return fin(f"No se alcanza la URL: {exc}. Revisa que el celular "
                       f"esté en la misma red y la app con el servidor iniciado")

    if fuente.isdigit():
        flags = [Monitor._flag_backend(), cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY]
    else:
        flags = [cv2.CAP_ANY]

    # La apertura con OpenCV puede bloquearse (p. ej. RTSP caído): se hace
    # en un hilo con plazo para no colgar el endpoint.
    limite = t0 + presupuesto_s
    sonda = {"probados": []}
    hilo = threading.Thread(target=_sondear_cv,
                            args=(fuente, flags, intentos_lectura, limite, sonda),
                            daemon=True)
    hilo.start()
    hilo.join(timeout=max(1.0, limite - time.time()))
    if hilo.is_alive():
        return fin(f"Sin respuesta en {int(presupuesto_s)} s "
                   f"(probados: {', '.join(sonda['probados']) or '—'})")
    if sonda.get("ok"):
        res["ok"] = True
        res.update({k: sonda[k] for k in ("frames", "ancho", "alto", "backend", "preview")})
        return fin(sonda.get("detalle", "OK"))
    probados = ", ".join(sonda["probados"]) or "—"
    return fin(f"{sonda.get('detalle', 'sin señal')} (probados: {probados})")
