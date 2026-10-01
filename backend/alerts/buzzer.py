"""Alarma sonora genérica del sistema operativo."""

from __future__ import annotations

import logging
import os
import platform
import threading

log = logging.getLogger(__name__)

_bloqueo = threading.Lock()
_ultimo_beep: float = 0.0


def _sonar_windows(repeticiones: int = 3) -> None:
    import winsound

    for _ in range(repeticiones):
        winsound.Beep(1100, 400)


def _sonar_macos() -> None:
    os.system("afplay /System/Library/Sounds/Sosumi.aiff")


def _sonar_linux() -> None:
    print("\a", end="", flush=True)


def sonar_alarma(intervalo_min_s: float = 2.0) -> None:
    """Dispara la alarma en segundo plano, sin bloquear el bucle de visión."""
    import time

    global _ultimo_beep
    ahora = time.time()
    with _bloqueo:
        if ahora - _ultimo_beep < intervalo_min_s:
            return
        _ultimo_beep = ahora

    def _worker() -> None:
        try:
            sistema = platform.system()
            if sistema == "Windows":
                _sonar_windows()
            elif sistema == "Darwin":
                _sonar_macos()
            else:
                _sonar_linux()
        except Exception as exc:  # pragma: no cover
            log.debug("No se pudo reproducir la alarma: %s", exc)

    threading.Thread(target=_worker, daemon=True).start()
