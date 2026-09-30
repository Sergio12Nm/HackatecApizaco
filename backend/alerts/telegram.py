"""Aviso a seguridad por Telegram.

Si no hay token configurado, el aviso queda registrado en consola
y en el historial de eventos de MySQL (de ahí el panel web).
"""

from __future__ import annotations

import io
import logging
import threading

import requests

from .. import config

log = logging.getLogger(__name__)

_bloqueo = threading.Lock()
_ultimo_envio: float = 0.0


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


def enviar_alerta(
    snapshot: bytes | None = None,
    similitud: float = 0.0,
    zona: str | None = None,
    nota: str | None = None,
    intervalo_min_s: float = 10.0,
) -> bool:
    """Envía la foto del intruso a Telegram. Nunca bloquea más de 15 s."""
    global _ultimo_envio
    import time

    texto = "🚨 Persona NO autorizada en zona restringida"
    if zona:
        texto += f"\nZona: {zona}"
    texto += f"\nSimilitud: {similitud:.2f}"
    if nota:
        texto += f"\nNota: {nota}"

    if not configurado():
        log.warning("[ALERTA] %s", texto.replace("\n", " | "))
        return False

    ahora = time.time()
    with _bloqueo:
        if ahora - _ultimo_envio < intervalo_min_s:
            return False
        _ultimo_envio = ahora

    resultado: dict = {}

    def _worker() -> None:
        resultado["ok"] = _enviar(texto, snapshot)

    threading.Thread(target=_worker, daemon=True).start()
    return True


def probar() -> tuple[bool, str]:
    """Envía un mensaje de prueba. Devuelve (ok, mensaje)."""
    if not configurado():
        return False, "Telegram no configurado (TELEGRAM_TOKEN / TELEGRAM_CHAT vacíos)"
    ok = _enviar("✅ Vigilancia CV conectada. Test de configuración.", None)
    return (True, "Mensaje de prueba enviado") if ok else (False, "Falló el envío")
