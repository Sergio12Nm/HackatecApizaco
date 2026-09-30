"""Definición y edición de zonas restringidas (polígonos)."""

from __future__ import annotations

import io
import json

import numpy as np
import pandas as pd
import streamlit as st
from PIL import Image, ImageDraw

import cliente
import estilo

st.title("🔲 Zonas restringidas")
st.caption(
    "Se evalúa el punto de los pies (centro inferior de la caja de la persona). "
    "Si está dentro del polígono, se intenta reconocer el rostro."
)

if not cliente.backend_conectado():
    estilo.aviso_no_conectado()
    st.stop()

cfg = cliente.configuracion()
ANCHO = cfg["frame_width"]
ALTO = cfg["frame_height"]

# ---------------------------------------------------------------------
# Imagen de referencia
# ---------------------------------------------------------------------
with st.expander("🖼 Imagen de referencia para dibujar", expanded=False):
    st.caption("Se usa el fotograma actual de la cámara. Si no hay cámara, sube una imagen.")
    subida = st.file_uploader("Sube una imagen de referencia", type=["jpg", "jpeg", "png"],
                              key="ref_imagen")

if subida is not None:
    img_ref = Image.open(io.BytesIO(subida.getvalue())).convert("RGB")
else:
    jpeg = cliente.fotograma_actual()
    if jpeg:
        img_ref = Image.open(io.BytesIO(jpeg)).convert("RGB")
    else:
        img_ref = Image.new("RGB", (ANCHO, ALTO), (18, 24, 38))
        st.info("Sin cámara: dibuja sobre el lienzo en blanco (o sube una imagen).")

ANCHO, ALTO = img_ref.size


def cargar_en_editor(coordenadas, nombre: str = "", zona_id: int | None = None) -> None:
    """Pide volcar un polígono en el editor de la siguiente pasada."""
    poligono = [[int(x), int(y)] for x, y in coordenadas][:12]
    st.session_state["zona_pendiente"] = {
        "tipo": "⬟ Polígono libre",
        "n": max(3, len(poligono)),
        "df": pd.DataFrame(poligono, columns=["x", "y"]),
        "nombre": nombre,
        "id": zona_id,
    }


# ---------------------------------------------------------------------
# Editor de zona
# ---------------------------------------------------------------------
st.subheader("✏️ Definir zona")

# Una zona puede llegar desde "Editar" o desde el pegador de JSON. Como los widgets
# ya se crearon en esta pasada, la carga se aplaza a la siguiente con st.rerun().
pendiente = st.session_state.pop("zona_pendiente", None)
if pendiente:
    st.session_state["tipo_zona"] = pendiente["tipo"]
    st.session_state["num_vertices"] = pendiente["n"]
    st.session_state[f"puntos_{pendiente['n']}"] = pendiente["df"]
    st.session_state["nombre_zona"] = pendiente["nombre"]
    st.session_state["zona_version"] = st.session_state.get("zona_version", 0) + 1
    st.session_state["zona_en_edicion"] = pendiente["id"]

tipo = st.radio(
    "Tipo de zona",
    ["▭ Rectángulo", "⬟ Polígono libre"],
    horizontal=True,
    label_visibility="collapsed",
    key="tipo_zona",
)

if tipo.startswith("▭"):
    c1, c2 = st.columns(2)
    x1 = c1.slider("x inicial", 0, ANCHO, max(0, ANCHO // 5))
    x2 = c2.slider("x final", 0, ANCHO, ANCHO - 1)
    y1 = c1.slider("y inicial", 0, ALTO, int(ALTO * 0.6))
    y2 = c2.slider("y final", 0, ALTO, ALTO - 1)
    puntos = [
        [min(x1, x2), min(y1, y2)],
        [max(x1, x2), min(y1, y2)],
        [max(x1, x2), max(y1, y2)],
        [min(x1, x2), max(y1, y2)],
    ]
else:
    st.session_state.setdefault("num_vertices", 4)
    n = st.number_input("Número de vértices", 3, 12, step=1, key="num_vertices")
    clave = f"puntos_{n}"
    if clave not in st.session_state:
        paso_x, paso_y = ANCHO / (n + 1), ALTO / (n + 1)
        st.session_state[clave] = pd.DataFrame(
            {
                "x": [int((i + 1) * paso_x) for i in range(n)],
                "y": [int((i + 1) * paso_y) for i in range(n)],
            }
        )
    editado = st.data_editor(
        st.session_state[clave],
        num_rows="dynamic",
        width="stretch",
        hide_index=True,
        key=f"editor_{clave}_{st.session_state.get('zona_version', 0)}",
        column_config={
            "x": st.column_config.NumberColumn("x", min_value=0, max_value=ANCHO, step=1),
            "y": st.column_config.NumberColumn("y", min_value=0, max_value=ALTO, step=1),
        },
    )
    puntos = [[int(p["x"]), int(p["y"])] for _, p in editado.iterrows()]
    st.session_state[clave] = editado

# ---------------------------------------------------------------------
# Vista previa
# ---------------------------------------------------------------------
previa = img_ref.copy()
lienzo = ImageDraw.Draw(previa)
if len(puntos) >= 3:
    poligono = [tuple(p) for p in puntos]
    lienzo.polygon(poligono, outline=(255, 180, 40), width=3)
    lienzo.line(poligono + [poligono[0]], fill=(255, 180, 40), width=3)
    for i, (x, y) in enumerate(poligono):
        lienzo.ellipse([x - 5, y - 5, x + 5, y + 5], fill=(255, 180, 40))
        lienzo.text((x + 7, y - 12), str(i + 1), fill=(255, 255, 255))
else:
    st.warning("Necesitas al menos 3 puntos para cerrar el polígono.")

st.image(previa, width="stretch")

# ---------------------------------------------------------------------
# Guardar
# ---------------------------------------------------------------------
col_izq, col_der, _ = st.columns([2, 2, 4])
nombre = col_izq.text_input("Nombre de la zona", placeholder="Ej.: Entrada principal",
                            key="nombre_zona")
camara_id = col_der.text_input("ID de cámara", value="cam0")

if st.session_state.get("zona_en_edicion"):
    st.caption(f"✏️ Editando la zona #{st.session_state['zona_en_edicion']}. "
               "Usa «Actualizar zona existente» para guardarla.")

if col_izq.button("💾 Crear zona", type="primary", disabled=len(puntos) < 3):
    try:
        resultado = cliente.crear_zona(nombre.strip() or "Zona sin nombre", puntos, camara_id)
        st.success(f"✅ {resultado['mensaje']}")
        st.rerun()
    except cliente.ErrorApi as exc:
        st.error(f"❌ {exc}")

with st.expander("🧩 Pegar polígono como JSON"):
    texto = st.text_area("JSON", value=json.dumps(puntos), height=120)
    if st.button("Usar este JSON"):
        try:
            datos = json.loads(texto)
            if not isinstance(datos, list) or len(datos) < 3:
                raise ValueError("se esperan al menos 3 pares [x, y]")
            cargar_en_editor(datos)
            st.rerun()
        except Exception as exc:
            st.error(f"JSON inválido: {exc}")

# ---------------------------------------------------------------------
# Zonas existentes
# ---------------------------------------------------------------------
st.divider()
st.subheader("📐 Zonas guardadas")

try:
    zonas = cliente.listar_zonas()
except cliente.ErrorApi as exc:
    st.error(str(exc))
    st.stop()

if not zonas:
    st.info("No hay zonas definidas. Mientras no exista ninguna, "
            f"se evalúa toda la imagen (DETECTAR_SIN_ZONAS = "
            f"{'sí' if cfg['detectar_sin_zonas'] else 'no'}).")
else:
    for z in zonas:
        with st.container(border=True):
            cols = st.columns([3, 3, 1, 1])
            cols[0].markdown(f"**#{z['id']} · {z['nombre']}**")
            cols[1].markdown(f"`{z['poligono']}`")
            if cols[2].button("✏️ Editar", key=f"edit_{z['id']}", width="stretch"):
                cargar_en_editor(z["poligono"], z["nombre"], z["id"])
                st.rerun()
            if cols[3].button("🗑", key=f"del_{z['id']}", width="stretch"):
                try:
                    cliente.eliminar_zona(z["id"])
                    st.session_state.pop("zona_en_edicion", None)
                    st.rerun()
                except cliente.ErrorApi as exc:
                    st.error(f"❌ {exc}")

    with st.expander("Actualizar zona existente"):
        zid = st.selectbox("Zona", [z["id"] for z in zonas],
                           format_func=lambda i: f"#{i} · {next(z['nombre'] for z in zonas if z['id'] == i)}")
        nuevo_nombre = st.text_input("Nuevo nombre",
                                     value=next(z["nombre"] for z in zonas if z["id"] == zid))
        json_edit = st.text_area(
            "Polígono (JSON)",
            value=json.dumps(next(z["poligono"] for z in zonas if z["id"] == zid)),
        )
        if st.button("💾 Actualizar zona"):
            try:
                datos = json.loads(json_edit)
                if not isinstance(datos, list) or len(datos) < 3:
                    raise ValueError("se esperan al menos 3 pares [x, y]")
                cliente.actualizar_zona(zid, nuevo_nombre, datos)
                st.success("Zona actualizada.")
                st.rerun()
            except Exception as exc:
                st.error(f"❌ {exc}")
