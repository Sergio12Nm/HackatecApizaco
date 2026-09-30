"""
Sistema de Videovigilancia con Visión Artificial — Fase 1 (MySQL)
Interfaz web (Streamlit).

Uso:  streamlit run frontend/app.py
"""

from __future__ import annotations

import streamlit as st

import estilo

st.set_page_config(
    page_title="Vigilancia CV",
    page_icon="🎥",
    layout="wide",
    initial_sidebar_state="expanded",
)

estilo.aplicar_estilos()

# ---- Barra lateral: estado del sistema (visible en todas las páginas) ----
with st.sidebar:
    st.title("🎥 Vigilancia CV")
    st.caption("Detección de intrusos con IA · Fase 1")

estilo.estado_conexion()

# ---- Navegación multipágina ----
pg = st.navigation(
    [
        st.Page("pages/vision.py", title="Panel de visión", icon="🎥", default=True),
        st.Page("pages/registro.py", title="Registro de personal", icon="👤"),
        st.Page("pages/personas.py", title="Personal autorizado", icon="🗂️"),
        st.Page("pages/zonas.py", title="Zonas restringidas", icon="🔲"),
        st.Page("pages/eventos.py", title="Historial de eventos", icon="📋"),
        st.Page("pages/ajustes.py", title="Ajustes y diagnóstico", icon="⚙️"),
    ]
)

with st.sidebar:
    st.divider()
    st.caption("Backend: FastAPI · Motor: YOLOv8 + ArcFace · Datos: MySQL 8")

pg.run()
