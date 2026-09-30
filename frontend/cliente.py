"""
Cliente HTTP hacia la API del backend.

Todo el frontend(Streamlit) habla con FastAPI a través de este módulo,
de modo que la base de datos y el motor de visión quedan encapsulados
en un solo proceso.
"""

from __future__ import annotations

import os
from typing import Any

import requests
import streamlit as st

API_URL = os.environ.get("API_URL", "http://127.0.0.1:8000").rstrip("/")
TIMEOUT = 20.0

_session = requests.Session()


class ErrorApi(Exception):
    """Error legible para mostrar en la interfaz."""


def _url(ruta: str) -> str:
    return f"{API_URL}/{ruta.lstrip('/')}"


def _manejar(respuesta: requests.Response) -> Any:
    if respuesta.status_code >= 400:
        detalle: Any
        try:
            cuerpo = respuesta.json()
            detalle = cuerpo.get("detail", cuerpo)
            if isinstance(detalle, list):  # errores de validación de pydantic
                detalle = "; ".join(
                    f"{e.get('loc', ['?'])[-1]}: {e.get('msg', '')}" for e in detalle
                )
        except Exception:
            detalle = respuesta.text[:300] or f"HTTP {respuesta.status_code}"
        raise ErrorApi(str(detalle))
    if respuesta.headers.get("content-type", "").startswith("application/json"):
        return respuesta.json()
    return respuesta.content


# ---------------------------------------------------------------------
# Genéricos
# ---------------------------------------------------------------------
def get_json(ruta: str, params: dict | None = None) -> Any:
    try:
        r = _session.get(_url(ruta), params=params, timeout=TIMEOUT)
    except requests.RequestException as exc:
        raise ErrorApi(f"No se pudo conectar con el backend ({API_URL}): {exc}") from exc
    return _manejar(r)


def get_bytes(ruta: str, params: dict | None = None) -> bytes | None:
    try:
        r = _session.get(_url(ruta), params=params, timeout=TIMEOUT)
    except requests.RequestException:
        return None
    if r.status_code != 200:
        return None
    return r.content


def post_json(ruta: str, datos: dict | None = None) -> Any:
    try:
        r = _session.post(_url(ruta), json=datos or {}, timeout=TIMEOUT)
    except requests.RequestException as exc:
        raise ErrorApi(f"No se pudo conectar con el backend: {exc}") from exc
    return _manejar(r)


def post_form(ruta: str, datos: dict, archivos: dict | None = None) -> Any:
    try:
        r = _session.post(_url(ruta), data=datos, files=archivos, timeout=120)
    except requests.RequestException as exc:
        raise ErrorApi(f"No se pudo conectar con el backend: {exc}") from exc
    return _manejar(r)


def patch(ruta: str, params: dict) -> Any:
    try:
        r = _session.patch(_url(ruta), params=params, timeout=TIMEOUT)
    except requests.RequestException as exc:
        raise ErrorApi(f"No se pudo conectar con el backend: {exc}") from exc
    return _manejar(r)


def put(ruta: str, datos: dict) -> Any:
    try:
        r = _session.put(_url(ruta), json=datos, timeout=TIMEOUT)
    except requests.RequestException as exc:
        raise ErrorApi(f"No se pudo conectar con el backend: {exc}") from exc
    return _manejar(r)


def delete(ruta: str) -> Any:
    try:
        r = _session.delete(_url(ruta), timeout=TIMEOUT)
    except requests.RequestException as exc:
        raise ErrorApi(f"No se pudo conectar con el backend: {exc}") from exc
    return _manejar(r)


# ---------------------------------------------------------------------
# Endpoints de la aplicación
# ---------------------------------------------------------------------
def salud() -> dict:
    return get_json("/api/salud")


def configuracion() -> dict:
    return get_json("/api/config")


def estado_monitor() -> dict:
    return get_json("/api/estado")


def alarma() -> dict:
    return get_json("/api/alarma")


def fotograma_actual() -> bytes | None:
    return get_bytes("/api/frame")


def control_monitor(accion: str) -> dict:
    return post_json(f"/api/monitor/{accion}")


def listar_personas(solo_activas: bool = False) -> list[dict]:
    return get_json("/api/personas", {"solo_activas": solo_activas})


def registrar_persona(
    nombre: str,
    documento: str,
    cargo: str,
    email: str,
    telefono: str,
    fotos,
) -> dict:
    archivos = [
        ("fotos", (f.name, f.getvalue(), "image/jpeg")) for f in fotos
    ]
    return post_form(
        "/api/personas",
        {
            "nombre": nombre,
            "documento": documento,
            "cargo": cargo,
            "email": email,
            "telefono": telefono,
        },
        archivos,
    )


def agregar_embeddings(persona_id: int, fotos) -> dict:
    archivos = [("fotos", (f.name, f.getvalue(), "image/jpeg")) for f in fotos]
    return post_form(f"/api/personas/{persona_id}/embeddings", {}, archivos)


def cambiar_activo(persona_id: int, activo: bool) -> dict:
    return patch(f"/api/personas/{persona_id}/activo", {"activo": str(activo).lower()})


def eliminar_persona(persona_id: int) -> dict:
    return delete(f"/api/personas/{persona_id}")


def foto_persona(persona_id: int, indice: int = 0) -> bytes | None:
    return get_bytes(f"/api/personas/{persona_id}/foto", {"indice": indice})


def listar_zonas() -> list[dict]:
    return get_json("/api/zonas")


def crear_zona(nombre: str, poligono: list[list[int]], camara_id: str = "cam0") -> dict:
    return post_json("/api/zonas", {"nombre": nombre, "poligono": poligono, "camara_id": camara_id})


def actualizar_zona(zid: int, nombre: str, poligono: list[list[int]], camara_id: str = "cam0") -> dict:
    return put(f"/api/zonas/{zid}", {"id": zid, "nombre": nombre, "poligono": poligono, "camara_id": camara_id})


def eliminar_zona(zid: int) -> dict:
    return delete(f"/api/zonas/{zid}")


def listar_eventos(limit: int = 50, tipo: str | None = None) -> list[dict]:
    params: dict = {"limit": limit}
    if tipo:
        params["tipo"] = tipo
    return get_json("/api/eventos", params)


def snapshot_evento(eid: int) -> bytes | None:
    return get_bytes(f"/api/eventos/{eid}/snapshot")


def borrar_evento(eid: int) -> dict:
    return delete(f"/api/eventos/{eid}")


def purgar_eventos(dias: int = 90) -> dict:
    return post_json("/api/eventos/purgar", {"dias": dias})


# ---------------------------------------------------------------------
# Utilidades de estado
# ---------------------------------------------------------------------
def backend_conectado() -> bool:
    try:
        r = _session.get(_url("/api/config"), timeout=3)
        return r.status_code == 200
    except requests.RequestException:
        return False


@st.cache_data(ttl=5, show_spinner=False)
def _config_cache() -> dict:
    return configuracion()


def config_cache() -> dict | None:
    try:
        return _config_cache()
    except ErrorApi:
        _config_cache.clear()
        return None
