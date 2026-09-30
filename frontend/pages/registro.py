"""Registro de personal autorizado (nuevo o amplifying existing)."""

from __future__ import annotations

import streamlit as st

import cliente
import estilo

st.title("👤 Registro de personal autorizado")
st.caption(
    "Se extrae un embedding de 512 dimensiones de cada foto y se guarda en MySQL. "
    "No se reentrena ningún modelo: registrar = insertar un vector."
)

if not cliente.backend_conectado():
    estilo.aviso_no_conectado()
    st.stop()

modo = st.radio(
    "Operación",
    ["➕ Persona nueva", "➕ Fotos adicionales (registro en caliente)"],
    horizontal=True,
)

# ---------------------------------------------------------------------
# Persona nueva
# ---------------------------------------------------------------------
if modo.startswith("➕ Persona"):
    with st.form("form_persona", clear_on_submit=False):
        st.subheader("Datos de la persona")
        col1, col2 = st.columns(2)
        with col1:
            nombre = st.text_input("Nombre completo *", placeholder="Ej.: Ana Torres")
            cargo = st.text_input("Cargo", placeholder="Ej.: Operadora de planta")
            telefono = st.text_input("Teléfono", placeholder="Ej.: 300 123 4567")
        with col2:
            documento = st.text_input("Documento / ID *", placeholder="Ej.: CC 12345678")
            email = st.text_input("Email", placeholder="Ej.: ana@empresa.com")

        st.subheader("Fotos del rostro")
        st.caption(
            "Entre 1 y 5 fotos **frontales**, con buena luz y sin filtros. "
            "Cuantas más fotos, más robusto el reconocimiento."
        )
        fotos = st.file_uploader(
            "Selecciona las fotos",
            type=["jpg", "jpeg", "png", "webp"],
            accept_multiple_files=True,
            key="fotos_nueva",
        )

        if fotos:
            columnas = st.columns(min(len(fotos), 5))
            for i, foto in enumerate(fotos[:5]):
                with columnas[i]:
                    st.image(foto, caption=foto.name, width="stretch")

        enviado = st.form_submit_button("💾 Registrar persona", type="primary")

    if enviado:
        if not nombre.strip():
            st.error("El nombre es obligatorio.")
        elif len(nombre.strip()) < 2:
            st.error("El nombre es demasiado corto.")
        elif not fotos:
            st.error("Selecciona al menos una foto con el rostro visible.")
        else:
            with st.spinner("Procesando rostros y guardando embeddings en MySQL..."):
                try:
                    resultado = cliente.registrar_persona(
                        nombre.strip(),
                        documento.strip(),
                        cargo.strip(),
                        email.strip(),
                        telefono.strip(),
                        fotos,
                    )
                    st.success(f"✅ {resultado['mensaje']} (ID {resultado['persona_id']})")
                    st.balloon()
                except cliente.ErrorApi as exc:
                    st.error(f"❌ {exc}")

# ---------------------------------------------------------------------
# Ampliación de una persona existente
# ---------------------------------------------------------------------
else:
    try:
        personas = cliente.listar_personas()
    except cliente.ErrorApi as exc:
        st.error(str(exc))
        st.stop()

    if not personas:
        st.info("Todavía no hay personas registradas.")
        st.stop()

    mapa = {f"{p['id']} · {p['nombre']}": p["id"] for p in personas}
    seleccion = st.selectbox("Persona a ampliar", list(mapa.keys()))
    persona_id = mapa[seleccion]
    persona = next(p for p in personas if p["id"] == persona_id)

    c1, c2, c3 = st.columns(3)
    c1.metric("Embeddings actuales", persona["num_embeddings"])
    c2.metric("Estado", "Activo" if persona["activo"] else "Inactivo")
    c3.metric("Registrado", (persona.get("cargo") or "—"))

    st.markdown("---")
    fotos = st.file_uploader(
        "Nuevas fotos",
        type=["jpg", "jpeg", "png", "webp"],
        accept_multiple_files=True,
        key="fotos_extra",
    )

    if st.button("➕ Agregar embeddings", type="primary", disabled=not fotos):
        with st.spinner("Generando embeddings..."):
            try:
                resultado = cliente.agregar_embeddings(persona_id, fotos)
                st.success(f"✅ {resultado['mensaje']}")
                st.rerun()
            except cliente.ErrorApi as exc:
                st.error(f"❌ {exc}")
