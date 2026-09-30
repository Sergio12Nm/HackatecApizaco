"""Historial de eventos y snapshots."""

from __future__ import annotations

import io

import pandas as pd
import streamlit as st
from PIL import Image

import cliente
import estilo

st.title("📋 Historial de eventos")
st.caption("Cada acceso a una zona queda registrado en MySQL con su snapshot.")

if not cliente.backend_conectado():
    estilo.aviso_no_conectado()
    st.stop()

# ---------------------------------------------------------------------
# Filtros
# ---------------------------------------------------------------------
c1, c2, c3, c4 = st.columns([2, 2, 1, 1])
tipo = c1.selectbox("Tipo", ["Todos", "Autorizado", "No autorizado"])
limite = c2.slider("Eventos a mostrar", 10, 300, 50, 10)
if c3.button("🔄 Actualizar", width="stretch"):
    st.rerun()
dias = c4.number_input("Purgar > (días)", 1, 3650, 90, 30, help="Elimina eventos antiguos")

param_tipo = {"Autorizado": "autorizado", "No autorizado": "no_autorizado"}.get(tipo)

try:
    eventos = cliente.listar_eventos(limit=limite, tipo=param_tipo)
except cliente.ErrorApi as exc:
    st.error(str(exc))
    st.stop()

if not eventos:
    st.info("No hay eventos con esos filtros.")
    st.stop()

tabla = pd.DataFrame(
    [
        {
            "ID": e["id"],
            "Fecha y hora": estilo.formatear_ts(e["ts"]),
            "Tipo": "✅ Autorizado" if e["tipo"] == "autorizado" else "🚨 No autorizado",
            "Persona": e.get("nombre") or "Desconocido",
            "Zona": e.get("zona_nombre") or "—",
            "Similitud": round(e["similitud"], 3) if e.get("similitud") is not None else None,
            "Nota": e.get("nota") or "",
            "Foto": "🖼" if e.get("tiene_snapshot") else "—",
        }
        for e in eventos
    ]
)

sel = st.dataframe(
    tabla,
    hide_index=True,
    width="stretch",
    on_select="rerun",
    selection_mode="single-row",
)

# Detalle del evento seleccionado
seleccion = sel.selection.rows if hasattr(sel, "selection") else []
if seleccion:
    evento = eventos[seleccion[0]]
    st.divider()
    st.subheader(f"Detalle del evento #{evento['id']}")

    col_a, col_b = st.columns([2, 1])
    with col_a:
        foto = cliente.snapshot_evento(evento["id"])
        if foto:
            st.image(Image.open(io.BytesIO(foto)), width="stretch")
            estilo.descarga(f"evento_{evento['id']}.jpg", foto, "image/jpeg")
        else:
            st.caption("Este evento no tiene snapshot "
                       "(los autorizados solo lo guardan si se activa la opción).")
    with col_b:
        st.json(evento, expanded=True)
        if st.button("🗑 Eliminar evento", key="del_evento"):
            try:
                cliente.borrar_evento(evento["id"])
                st.rerun()
            except cliente.ErrorApi as exc:
                st.error(str(exc))

st.divider()
if st.button("🧹 Purgar eventos antiguos", type="secondary"):
    try:
        resultado = cliente.purgar_eventos(int(dias))
        st.success(f"Se eliminaron {resultado['borrados']} evento(s) anteriores a {dias} días.")
        st.rerun()
    except cliente.ErrorApi as exc:
        st.error(str(exc))
