"""Gestión del personal autorizado."""

from __future__ import annotations

import io

import pandas as pd
import streamlit as st
from PIL import Image

import cliente
import estilo

st.title("Personal autorizado")
st.caption("Personas cuyos embeddings están en MySQL y por tanto se consideran autorizadas.")

if not cliente.backend_conectado():
    estilo.aviso_no_conectado()
    st.stop()

solo_activas = st.checkbox("Mostrar solo activas", value=False)

try:
    personas = cliente.listar_personas(solo_activas=solo_activas)
except cliente.ErrorApi as exc:
    st.error(str(exc))
    st.stop()

if not personas:
    st.info("No hay personas registradas. Ve a **Registro de personal**.")
    st.stop()

tabla = pd.DataFrame(
    [
        {
            "ID": p["id"],
            "Nombre": p["nombre"],
            "Documento": p.get("documento") or "—",
            "Cargo": p.get("cargo") or "—",
            "Email": p.get("email") or "—",
            "Embeddings": p["num_embeddings"],
            "Activo": "Sí" if p["activo"] else "No",
        }
        for p in personas
    ]
)

st.dataframe(tabla, hide_index=True, width="stretch")

st.divider()
seleccion = st.selectbox(
    "Administrar persona",
    [f"{p['id']} · {p['nombre']}" for p in personas],
)
persona_id = int(seleccion.split(" · ")[0])
persona = next(p for p in personas if p["id"] == persona_id)

col_foto, col_datos = st.columns([1, 2])
with col_foto:
    st.subheader("Foto registrada")
    foto = cliente.foto_persona(persona_id)
    if foto:
        st.image(Image.open(io.BytesIO(foto)), width="stretch")
        estilo.descarga(f"persona_{persona_id}.jpg", foto, "image/jpeg")
    else:
        st.caption("Sin foto almacenada.")

with col_datos:
    st.subheader("Acciones")
    st.markdown(f"**Estado actual:** {'Activo' if persona['activo'] else 'Inactivo'}")

    c1, c2 = st.columns(2)
    if c1.button("Alternar activo/inactivo", width="stretch"):
        try:
            cliente.cambiar_activo(persona_id, not persona["activo"])
            st.rerun()
        except cliente.ErrorApi as exc:
            st.error(str(exc))

    confirmar = c2.checkbox("Confirmar borrado")
    if c2.button("🗑 Eliminar persona", width="stretch", disabled=not confirmar,
                 type="secondary"):
        try:
            cliente.eliminar_persona(persona_id)
            st.success("Persona eliminada (y sus embeddings, por cascada).")
            st.rerun()
        except cliente.ErrorApi as exc:
            st.error(str(exc))

    st.caption(
        "Desactivar mantiene el historial pero la persona deja de ser reconocida. "
        "Al activar o desactivar se recarga la caché de embeddings automáticamente."
    )
