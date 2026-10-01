"""Aviso a seguridad por Telegram.

Si no hay token configurado, el aviso queda registrado en consola
y en el historial de eventos de MySQL (de ahí el panel web).
"""

from __future__ import annotations

import io
import logging
import threading
import time

import requests

from .. import config

log = logging.getLogger(__name__)

_bloqueo = threading.Lock()
_ultimo_envio: float = 0.0
_alerta_pendiente: tuple[str, bytes | None] | None = None
_hilo_cola: threading.Thread | None = None


def configurado() -> bool:
    return bool(config.TELEGRAM_TOKEN and config.TELEGRAM_CHAT)


def _enviar(mensaje: str, snapshot: bytes | None) -> bool:
    token, chat = config.TELEGRAM_TOKEN, config.TELEGRAM_CHAT
    base = f"https://api.telegram.org/bot{token}"
    try:
        if snapshot:
            files = {"photo": ("intruso.jpg", io.BytesIO(snapshot), "image/jpeg")}
            resp = requests.post(
                f"{base}/sendPhoto",
                data={"chat_id": chat, "caption": mensaje},
                files=files,
                timeout=15,
            )
        else:
            resp = requests.post(
                f"{base}/sendMessage",
                data={"chat_id": chat, "text": mensaje},
                timeout=15,
            )
        if resp.status_code != 200:
            log.warning("Telegram respondió %s: %s", resp.status_code, resp.text[:200])
            return False
        return True
    except Exception as exc:
        log.warning("Error enviando a Telegram: %s", exc)
        return False


def _procesar_cola(intervalo_s: float) -> None:
    """Procesa alertas de una en una y conserva solo la más reciente."""
    global _alerta_pendiente, _hilo_cola, _ultimo_envio

    while True:
        with _bloqueo:
            if _alerta_pendiente is None:
                _hilo_cola = None
                return
            mensaje, snapshot = _alerta_pendiente
            _alerta_pendiente = None
            espera = max(0.0, intervalo_s - (time.time() - _ultimo_envio))

        if espera:
            time.sleep(espera)

        if not _enviar(mensaje, snapshot):
            log.warning("La alerta de Telegram no pudo enviarse")
        with _bloqueo:
            _ultimo_envio = time.time()


def enviar_alerta(
    snapshot: bytes | None = None,
    similitud: float = 0.0,
    zona: str | None = None,
    nota: str | None = None,
    mensaje: str | None = None,
    intervalo_min_s: float | None = None,
) -> bool:
    """Encola una alerta sin bloquear el motor de visión.

    Solo se envía una alerta por intervalo. Si llegan varias durante ese
    tiempo, se sustituye la pendiente por la más reciente para evitar una
    cola de fotos obsoletas.
    """
    global _alerta_pendiente, _hilo_cola

    texto = mensaje or "🚨 Persona NO autorizada en zona restringida"
    if mensaje is None:
        if zona:
            texto += f"\nZona: {zona}"
        texto += f"\nSimilitud: {similitud:.2f}"
        if nota:
            texto += f"\nNota: {nota}"

    if not configurado():
        log.warning("[ALERTA] %s", texto.replace("\n", " | "))
        return False

    intervalo_s = (
        config.TELEGRAM_INTERVALO_S
        if intervalo_min_s is None
        else max(0.0, float(intervalo_min_s))
    )

    # Las alertas producidas por una detección pasan explícitamente intervalo
    # cero: deben salir sin esperar a la cola de avisos generales.
    if intervalo_s == 0.0:
        threading.Thread(
            target=_enviar,
            args=(texto, snapshot),
            name="telegram-alerta-inmediata",
            daemon=True,
        ).start()
        return True

    with _bloqueo:
        _alerta_pendiente = (texto, snapshot)
        if _hilo_cola is not None and _hilo_cola.is_alive():
            return True
        _hilo_cola = threading.Thread(
            target=_procesar_cola,
            args=(intervalo_s,),
            name="telegram-alertas",
            daemon=True,
        )
        _hilo_cola.start()
    return True


def probar() -> tuple[bool, str]:
    """Envía un mensaje de prueba. Devuelve (ok, mensaje)."""
    if not configurado():
        return False, "Telegram no configurado (TELEGRAM_TOKEN / TELEGRAM_CHAT vacíos)"
    ok = _enviar("✅ Vigilancia CV conectada. Test de configuración.", None)
    return (True, "Mensaje de prueba enviado") if ok else (False, "Falló el envío")
