"""Helpers de interfaz compartidos por todas las páginas."""

from __future__ import annotations

import io
from datetime import datetime

import streamlit as st

CSS = """
<style>
  .v-card {background:#111c2e; border:1px solid #1e3a5f; border-radius:10px;
           padding:14px 16px; margin-bottom:10px;}
  .v-alarma {background:#7f1d1d; color:#fff; padding:14px; border-radius:10px;
             font-weight:700; text-align:center; font-size:18px; margin-bottom:12px;
             animation: parpadeo 1s infinite;}
  .v-ok {background:#14532d; color:#dcfce7; padding:12px; border-radius:8px; font-weight:600;}
  .v-ok-alerta {background:#4a1d1d; color:#fee2e2; padding:12px; border-radius:8px; font-weight:600;}
  @keyframes parpadeo {0%,100%{opacity:1} 50%{opacity:.55}}
  div[data-testid="stMetricValue"] {font-size: 1.3rem;}
  .stTabs [data-baseweb="tab"] {font-weight:600;}
</style>
"""


def aplicar_estilos() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def banner_alarma(activa: bool) -> None:
    if activa:
        st.markdown(
            '<div class="v-alarma">⚠ ALARMA ACTIVA — PERSONA NO AUTORIZADA EN ZONA RESTRINGIDA ⚠</div>',
            unsafe_allow_html=True,
        )


def estado_conexion() -> None:
    """Indicador en la barra lateral."""
    import cliente

    if cliente.backend_conectado():
        st.sidebar.success("Backend conectado", icon="✅")
    else:
        st.sidebar.error("Backend no disponible", icon="⛔")
        st.sidebar.caption(f"API: {cliente.API_URL}")
        st.sidebar.code("uvicorn backend.main:app --port 8000", language="powershell")


def bytes_a_imagen(datos: bytes) -> io.BytesIO:
    return io.BytesIO(datos)


def formatear_ts(ts: str | None) -> str:
    if not ts:
        return "-"
    try:
        return datetime.fromisoformat(ts).strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return ts


def descarga(nombre: str, datos: bytes, mime: str, etiqueta: str = "⬇ Descargar"):
    st.download_button(etiqueta, data=datos, file_name=nombre, mime=mime)


def aviso_no_conectado() -> None:
    import cliente

    st.error("No hay conexión con el backend. Arranca la API en otra terminal:")
    st.code(
        ".venv\\Scripts\\activate\nuvicorn backend.main:app --host 0.0.0.0 --port 8000",
        language="powershell",
    )
    st.caption(f"URL configurada: {cliente.API_URL}")


ICONO_ESTADO = {
    "autorizado": "✅",
    "no_autorizado": "🚨",
    "sin_rostro": "😐",
    "error_rostro": "⚠️",
    "fuera_de_zona": "➖",
}
