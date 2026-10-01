"""Panel de visión en vivo: stream, detecciones y alarma."""

from __future__ import annotations

import io
import time

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from PIL import Image

import cliente
import estilo

st.title("Panel de visión en vivo")
st.caption(
    "YOLOv8 detecta personas · ArcFace compara embeddings contra MySQL · "
    "caja verde = autorizado, caja roja = no autorizado."
)

if not cliente.backend_conectado():
    estilo.aviso_no_conectado()
    st.stop()

# ---------------------------------------------------------------------
# Controles
# ---------------------------------------------------------------------
c1, c2, c3, c4 = st.columns(4)
with c1:
    if st.button("Iniciar motor", width="stretch", type="primary"):
        cliente.control_monitor("start")
        st.rerun()
with c2:
    if st.button("Detener motor", width="stretch"):
        cliente.control_monitor("stop")
        st.rerun()
with c3:
    if st.button("Recargar embeddings", width="stretch"):
        cliente.control_monitor("reiniciar-cache")
        st.toast("Embeddings recargados desde MySQL")
        st.rerun()
with c4:
    st.link_button("Stream MJPEG directo", f"{cliente.API_URL}/api/stream")

# El iframe va fuera del fragmento: si estuviera dentro, Streamlit lo recrearía
# cada segundo y la imagen parpadearía.
embeber = st.toggle("Ver el stream MJPEG aquí (en vivo)", value=False)
if embeber:
    components.html(
        f'<img src="{cliente.API_URL}/api/stream" style="width:100%;border-radius:8px;" />',
        height=420,
    )
    st.caption(
        "Si el recuadro sale en negro, el navegador no alcanza al backend. "
        f"Abre el stream directamente en otra pestaña: {cliente.API_URL}/api/stream"
    )


@st.fragment(run_every=1.0)
def panel_en_vivo() -> None:
    datos = cliente.estado_monitor()

    if datos.get("alarma"):
        estilo.banner_alarma(True)

    izquierda, derecha = st.columns([2.1, 1])

    with izquierda:
        jpeg = cliente.fotograma_actual()
        if jpeg:
            st.image(Image.open(io.BytesIO(jpeg)), width="stretch")
            if not datos.get("conectado"):
                # Hay imagen guardada pero la cámara no responde: es la última
                # que llegó, no video en vivo. Sin este aviso parece "conectado".
                hace = max(0.0, time.time() - float(datos.get("fotograma_ts") or 0.0))
                st.caption(f"⏸ Imagen congelada: la cámara no responde desde hace {hace:.0f} s.")
            with st.expander("Guardar fotograma actual"):
                estilo.descarga("captura.jpg", jpeg, "image/jpeg")
        else:
            _sin_fotograma(datos)

    with derecha:
        st.subheader("Estado del motor")
        st.metric("Fotogramas por segundo", f"{datos.get('fps', 0):.1f}")
        st.metric("Embeddings en base", datos.get("embeddings", 0))
        st.metric("Umbral facial", f"{datos.get('umbral', 0):.2f}")

        activo = datos.get("activo", True)
        icono = "🟢" if datos.get("conectado") else ("🔴" if activo else "⚪")
        st.markdown(f"**{icono} Cámara:** {datos.get('estado', '—')}")
        if datos.get("backend_camara"):
            st.caption(f"Backend de captura: {datos['backend_camara']}")

        if not activo and st.button("Encender el motor", type="primary", width="stretch"):
            cliente.control_monitor("start")
            st.rerun()

        detecciones = datos.get("detecciones") or []
        st.subheader("Detecciones en este fotograma")
        if not detecciones:
            st.info("Ninguna persona visible.")
        else:
            filas = []
            for d in detecciones:
                filas.append({
                    "Estado": f"{estilo.ICONO_ESTADO.get(d['estado'], '•')} {d.get('etiqueta', '')}",
                    "Zona": d.get("zona_nombre") or "—",
                    "Similitud": d.get("similitud"),
                    "Caja": str(d.get("bbox")),
                })
            st.dataframe(pd.DataFrame(filas), width="stretch", hide_index=True)


def _sin_fotograma(datos: dict) -> None:
    """Explica por qué no hay imagen, en vez de dejar el panel vacío."""
    estado = str(datos.get("estado", ""))
    if not datos.get("activo", True):
        st.error("⏹ El motor de visión está **detenido**, por eso no hay imagen.")
        if st.button("▶ Encender el motor ahora", type="primary", width="stretch"):
            cliente.control_monitor("start")
            st.toast("Motor encendido")
            st.rerun()
        return

    if "abierta pero sin imagen" in estado or "congelada" in estado:
        st.warning(f"📷 **{estado}**")
        st.markdown(
            """
Windows abre la webcam pero el dispositivo no entrega imagen. Casi siempre
es una de estas causas:

1. **Otra app tiene la cámara**: cierra Teams, Zoom, el navegador o la app
   *Cámara* de Windows (el acceso a la webcam es exclusivo).
2. **USB dormido o flojo**: desconecta y vuelve a conectar la cámara.
3. **Driver atascado**: el backend ya prueba solo con otro backend de
   captura (`dshow`/`msmf`); mira en el panel el valor de
   *Backend de captura* para ver cuál está intentando.
4. Si nada funciona, pon `CAMARA_BACKEND=dshow` en `.env` y **reinicia
   el backend**.
"""
        )
        return

    st.warning(f"📷 El motor está activo pero la cámara no entrega imagen: **{estado}**")
    cfg = cliente.configuracion()
    reintento = float(cfg.get("reintento_camara_s", 5))
    st.markdown(
        f"""
La fuente configurada es `{cfg.get('camara_url')}`.

**Opción 1 — Celular (IP Webcam)**
1. Instala *IP Webcam* en Android y pulsa «Iniciar servidor».
2. Anota la IP, por ejemplo `http://192.168.1.50:8080/video`.
3. Ponla en `.env`: `CAMARA_URL=http://192.168.1.50:8080/video`
4. Reinicia el backend.

**Opción 2 — Webcam de la PC**
1. Pon `CAMARA_URL=0` en `.env`.
2. Reinicia el backend.

> El motor reintenta la conexión cada {reintento:.0f} s: si enciendes la
> cámara, la imagen vuelve sola.
"""
    )


panel_en_vivo()

# ---------------------------------------------------------------------
# Últimos eventos (se actualiza con el mismo fragmento para no recargar todo)
# ---------------------------------------------------------------------
st.divider()
st.subheader("Últimos eventos")


@st.fragment(run_every=2.0)
def ultimos_eventos() -> None:
    try:
        eventos = cliente.listar_eventos(limit=15)
    except cliente.ErrorApi as exc:
        st.error(str(exc))
        return

    if not eventos:
        st.info("Todavía no hay eventos registrados.")
        return

    filas = [
        {
            "Hora": estilo.formatear_ts(e["ts"]),
            "Tipo": "Autorizado" if e["tipo"] == "autorizado" else "No autorizado",
            "Persona": e.get("nombre") or (f"ID {e['persona_id']}" if e.get("persona_id") else "Desconocido"),
            "Zona": e.get("zona_nombre") or "—",
            "Similitud": round(e["similitud"], 3) if e.get("similitud") is not None else None,
            "Nota": e.get("nota") or "",
            "ID": e["id"],
        }
        for e in eventos
    ]
    st.dataframe(pd.DataFrame(filas), width="stretch", hide_index=True)

    ultimo = next((e for e in eventos if e["tipo"] == "no_autorizado"), None)
    if ultimo:
        with st.expander(f"Snapshot del evento #{ultimo['id']}"):
            foto = cliente.snapshot_evento(ultimo["id"])
            if foto:
                st.image(Image.open(io.BytesIO(foto)), width="stretch")
                estilo.descarga(f"evento_{ultimo['id']}.jpg", foto, "image/jpeg")
            else:
                st.caption("Este evento no tiene snapshot almacenado.")


ultimos_eventos()
