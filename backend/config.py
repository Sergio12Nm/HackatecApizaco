"""
Configuración central del sistema.

Todos los valores se pueden sobreescribir con un archivo `.env`
situado en la raíz del proyecto (o con variables de entorno).
"""

from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------
# Rutas
# ---------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
MODELOS_DIR = BASE_DIR / "modelos"
SQL_DIR = BASE_DIR / "sql"

MODELOS_DIR.mkdir(exist_ok=True)


def _cargar_env(ruta: Path | None = None) -> None:
    """Carga simple de archivo .env (KEY=VALOR, sin dependencias extra)."""
    ruta = ruta or (BASE_DIR / ".env")
    if not ruta.exists():
        return
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, _, valor = linea.partition("=")
        clave = clave.strip()
        valor = valor.strip()
        # comentario al final de la línea: "valor   # comentario"
        if "#" in valor:
            antes, _, _ = valor.partition("#")
            if antes != antes.rstrip() or valor.startswith("#"):
                valor = antes
        valor = valor.strip().strip('"').strip("'")
        if valor:
            os.environ.setdefault(clave, valor)


_cargar_env()


def _get(clave: str, defecto=None):
    return os.environ.get(clave, defecto)


def _get_int(clave: str, defecto: int) -> int:
    try:
        return int(str(_get(clave, defecto)))
    except (TypeError, ValueError):
        return defecto


def _get_float(clave: str, defecto: float) -> float:
    try:
        return float(str(_get(clave, defecto)))
    except (TypeError, ValueError):
        return defecto


def _get_bool(clave: str, defecto: bool) -> bool:
    valor = str(_get(clave, str(defecto))).strip().lower()
    return valor in {"1", "true", "yes", "si", "sí", "on"}


# ---------------------------------------------------------------------
# MySQL
# ---------------------------------------------------------------------
DB_USER = _get("DB_USER", "vigilancia")
DB_PASS = _get("DB_PASS", "vigilancia123")
DB_HOST = _get("DB_HOST", "localhost")
DB_PORT = _get_int("DB_PORT", 3306)
DB_NAME = _get("DB_NAME", "vigilancia_cv")

# ---------------------------------------------------------------------
# Cámara
# ---------------------------------------------------------------------
# Puede ser:
#   - una URL de red  : "http://192.168.1.50:8080/video"  (IP Webcam Android)
#   - un índice local : "0" (webcam de la PC), "1", "2"...
#   - un archivo      : "C:\videos\prueba.mp4"
CAMARA_URL = _get("CAMARA_URL", "http://192.168.1.50:8080/video")
CAMARA_FPS = _get_float("CAMARA_FPS", 10.0)          # fotogramas objetivo por segundo
REINTENTO_CAMARA_S = _get_float("REINTENTO_CAMARA_S", 5.0)

# En Windows el primer read() de una webcam suele fallar mientras el
# dispositivo negocia con Media Foundation. Sin reintentos ni espera, el motor
# abre y cierra la cámara en bucle y el dispositivo acaba bloqueándose.
CAMARA_LECTURA_INTENTOS = _get_int("CAMARA_LECTURA_INTENTOS", 6)
CAMARA_LECTURA_ESPERA_S = _get_float("CAMARA_LECTURA_ESPERA_S", 0.25)
# Si la cámara devuelve este número de fotogramas idénticos seguidos, se
# considera congelada (driver atascado) y se reabre el dispositivo.
CAMARA_CONGELADA_MAX = _get_int("CAMARA_CONGELADA_MAX", 50)
# auto | dshow | msmf. "auto" deja que OpenCV elija.
CAMARA_BACKEND = _get("CAMARA_BACKEND", "auto").lower()
# Si la webcam local abre pero no entrega imagen (o ni abre) este número de
# veces seguidas, el motor prueba automáticamente con otro backend de captura
# (dshow/msmf). Solo aplica a índices locales ("0", "1"...), no a URLs.
CAMARA_BACKEND_REINTENTOS = _get_int("CAMARA_BACKEND_REINTENTOS", 3)

FRAME_WIDTH = _get_int("FRAME_WIDTH", 640)
FRAME_HEIGHT = _get_int("FRAME_HEIGHT", 480)
CALIDAD_JPEG = _get_int("CALIDAD_JPEG", 78)

# ---------------------------------------------------------------------
# Detección de personas (YOLOv8)
# ---------------------------------------------------------------------
YOLO_WEIGHTS = _get("YOLO_WEIGHTS", "yolov8n.pt")
CONFIANZA_YOLO = _get_float("CONFIANZA_YOLO", 0.40)
# Si el peso está en la carpeta modelos/ se usa esa ruta
_YOLO_PATH = MODELOS_DIR / YOLO_WEIGHTS
YOLO_WEIGHTS_RESUELTO = str(_YOLO_PATH if _YOLO_PATH.exists() else YOLO_WEIGHTS)

# ---------------------------------------------------------------------
# Reconocimiento facial (InsightFace / ArcFace)
# ---------------------------------------------------------------------
FACE_MODEL = _get("FACE_MODEL", "buffalo_sc")
UMBRAL_FACIAL = _get_float("UMBRAL_FACIAL", 0.55)
# Tamaño mínimo del rostro (px) para intentar reconocerlo
ROSTRO_MIN_PX = _get_int("ROSTRO_MIN_PX", 40)
# Margen (%) que se agrega al recorte de la persona antes de buscar rostros
MARGEN_ROI = _get_float("MARGEN_ROI", 0.15)

# ---------------------------------------------------------------------
# Zonas
# ---------------------------------------------------------------------
# Si no hay ninguna zona definida, ¿se evalúa toda la imagen?
DETECTAR_SIN_ZONAS = _get_bool("DETECTAR_SIN_ZONAS", True)
# Segundos entre recargas de zonas desde MySQL
RECARGA_ZONAS_S = _get_float("RECARGA_ZONAS_S", 3.0)

# ---------------------------------------------------------------------
# Alarmas y eventos
# ---------------------------------------------------------------------
ALERTA_SIN_ROSTRO = _get_bool("ALERTA_SIN_ROSTRO", True)
COOLDOWN_AUTORIZADO_S = _get_float("COOLDOWN_AUTORIZADO_S", 30.0)
COOLDOWN_ALARMA_S = _get_float("COOLDOWN_ALARMA_S", 15.0)
ALARMA_SONORA = _get_bool("ALARMA_SONORA", True)
GUARDAR_SNAPSHOT_AUTORIZADO = _get_bool("GUARDAR_SNAPSHOT_AUTORIZADO", False)

TELEGRAM_TOKEN = _get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT = _get("TELEGRAM_CHAT", "")

# ---------------------------------------------------------------------
# Caché de embeddings (evita releer BLOBs en cada fotograma)
# ---------------------------------------------------------------------
CACHE_EMBEDDINGS_S = _get_float("CACHE_EMBEDDINGS_S", 30.0)

# ---------------------------------------------------------------------
# Frontend
# ---------------------------------------------------------------------
API_URL = _get("API_URL", "http://127.0.0.1:8000")
STREAMLIT_HOST = _get("STREAMLIT_HOST", "0.0.0.0")
STREAMLIT_PORT = _get_int("STREAMLIT_PORT", 8501)


def resumen() -> dict:
    """Configuración pública (sin contraseñas) para mostrar en el frontend."""
    return {
        "camara_url": CAMARA_URL,
        "camara_fps": CAMARA_FPS,
        "camara_backend": CAMARA_BACKEND,
        "reintento_camara_s": REINTENTO_CAMARA_S,
        "camara_congelada_max": CAMARA_CONGELADA_MAX,
        "frame_width": FRAME_WIDTH,
        "frame_height": FRAME_HEIGHT,
        "yolo_weights": Path(YOLO_WEIGHTS_RESUELTO).name,
        "confianza_yolo": CONFIANZA_YOLO,
        "face_model": FACE_MODEL,
        "umbral_facial": UMBRAL_FACIAL,
        "detectar_sin_zonas": DETECTAR_SIN_ZONAS,
        "alerta_sin_rostro": ALERTA_SIN_ROSTRO,
        "cooldown_autorizado_s": COOLDOWN_AUTORIZADO_S,
        "cooldown_alarma_s": COOLDOWN_ALARMA_S,
        "alarma_sonora": ALARMA_SONORA,
        "telegram_configurado": bool(TELEGRAM_TOKEN and TELEGRAM_CHAT),
        "db": {
            "host": DB_HOST,
            "puerto": DB_PORT,
            "nombre": DB_NAME,
            "usuario": DB_USER,
        },
    }
