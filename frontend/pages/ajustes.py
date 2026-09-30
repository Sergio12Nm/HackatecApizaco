"""Ajustes, diagnóstico del sistema y mantenimiento."""

from __future__ import annotations

import streamlit as st

import cliente
import estilo

st.title("⚙️ Ajustes y diagnóstico")

if not cliente.backend_conectado():
    estilo.aviso_no_conectado()
    st.stop()

# ---------------------------------------------------------------------
# Diagnóstico
# ---------------------------------------------------------------------
st.subheader("🩺 Estado del sistema")
try:
    salud = cliente.salud()
except cliente.ErrorApi as exc:
    st.error(str(exc))
    st.stop()

def _punto(ok) -> str:
    return "🟢 OK" if ok else "🔴 Error"

if salud["ok"]:
    st.success("Todos los componentes operativos.")
else:
    st.error("Hay componentes con problemas (ver detalle abajo).")

c1, c2, c3 = st.columns(3)
c1.metric("Base de datos", _punto("MySQL" in salud["base_datos"]))
c2.metric("Reconocimiento facial", _punto(salud["reconocimiento_facial"] == "disponible"))
c3.metric("Detección de personas", _punto(salud["deteccion_personas"] == "disponible"))

st.json(salud)

# ---------------------------------------------------------------------
# Base de datos
# ---------------------------------------------------------------------
st.divider()
st.subheader("🗄 Base de datos")
try:
    estado_db = cliente.get_json("/api/db/estado")
    st.info(estado_db["mensaje"])
    stats = estado_db.get("estadisticas") or {}
    if stats:
        d1, d2, d3, d4 = st.columns(4)
        d1.metric("Personas", stats.get("personas", 0))
        d2.metric("Embeddings", stats.get("embeddings", 0))
        d3.metric("Zonas", stats.get("zonas", 0))
        d4.metric("Eventos", stats.get("eventos", 0))
        e1, e2 = st.columns(2)
        e1.metric("Accesos autorizados", stats.get("autorizados", 0))
        e2.metric("Intrusiones", stats.get("no_autorizados", 0))
except cliente.ErrorApi as exc:
    st.error(str(exc))

# ---------------------------------------------------------------------
# Configuración efectiva
# ---------------------------------------------------------------------
st.divider()
st.subheader("🎛 Configuración efectiva")
try:
    cfg = cliente.configuracion()
except cliente.ErrorApi as exc:
    st.error(str(exc))
    st.stop()

st.json(cfg)

st.caption(
    "Para cambiar estos valores edita el archivo `.env` en la raíz del proyecto "
    "y reinicia el backend."
)
with st.expander("Ejemplo de .env"):
    st.code(
        "# Cámara\n"
        'CAMARA_URL=http://192.168.1.50:8080/video\n'
        "# o bien la webcam de la PC:\n"
        "CAMARA_URL=0\n\n"
        "# Reconocimiento facial\n"
        "UMBRAL_FACIAL=0.55\n"
        "FACE_MODEL=buffalo_sc\n\n"
        "# Alertas\n"
        "ALARMA_SONORA=1\n"
        "TELEGRAM_TOKEN=\n"
        "TELEGRAM_CHAT=\n\n"
        "# MySQL\n"
        "DB_USER=vigilancia\n"
        "DB_PASS=vigilancia123\n"
        "DB_HOST=localhost\n"
        "DB_PORT=3306\n"
        "DB_NAME=vigilancia_cv",
        language="dotenv",
    )

# ---------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------
st.divider()
st.subheader("📨 Aviso a seguridad (Telegram)")
if cfg["telegram_configurado"]:
    st.success("Telegram configurado.")
    if st.button("Enviar mensaje de prueba"):
        try:
            resultado = cliente.get_json("/telegram/test")
            (st.success if resultado["ok"] else st.error)(resultado["mensaje"])
        except cliente.ErrorApi as exc:
            st.error(str(exc))
else:
    st.warning(
        "Telegram no está configurado. Las intrusiones siguen quedar "
        "registradas en MySQL y visibles en el panel."
    )
    st.markdown(
        "1. Habla con `@BotFather` en Telegram y crea un bot (te da el token).\n"
        "2. Escríbele algo a tu bot y abre "
        "`https://api.telegram.org/bot<TOKEN>/getUpdates` para obtener tu `chat_id`.\n"
        "3. Pon `TELEGRAM_TOKEN` y `TELEGRAM_CHAT` en `.env` y reinicia el backend."
    )

# ---------------------------------------------------------------------
# Modelos
# ---------------------------------------------------------------------
st.divider()
st.subheader("📦 Modelos")
try:
    modelos = cliente.get_json("/api/modelos")
    st.json(modelos)
except cliente.ErrorApi as exc:
    st.error(str(exc))
st.caption(
    "Los pesos YOLO se descargan solos la primera vez. Si descargas "
    "`yolov8n.pt` u otro peso, déjalo en la carpeta `modelos/`."
)

# ---------------------------------------------------------------------
# Mantenimiento
# ---------------------------------------------------------------------
st.divider()
st.subheader("🧰 Mantenimiento")
with st.expander("Backup de MySQL"):
    st.code(
        r'"C:\wamp64\bin\mysql\mysql8.4.7\bin\mysqldump.exe" -u vigilancia -pvigilancia123 '
        "--single-transaction --routines --triggers --max_allowed_packet=64M "
        "vigilancia_cv > backups\\backup_%DATE:~10,4%%DATE:~4,2%%DATE:~7,2%.sql",
        language="cmd",
    )
    st.caption(
        "Como las fotos y los snapshots viven en LONGBLOB, el dump contiene "
        "absolutamente todo el sistema."
    )

with st.expander("Consultas SQL útiles"):
    st.code(
        "-- Tamaño de cada tabla\n"
        "SELECT table_name, ROUND((data_length+index_length)/1048576,2) AS MB\n"
        "FROM information_schema.tables\n"
        "WHERE table_schema='vigilancia_cv' ORDER BY (data_length+index_length) DESC;\n\n"
        "-- Últimas intrusiones\n"
        "SELECT * FROM eventos WHERE tipo='no_autorizado' ORDER BY timestamp DESC LIMIT 20;\n\n"
        "-- Personas con menos fotos (reconocimiento más débil)\n"
        "SELECT p.id, p.nombre, COUNT(e.id) AS fotos\n"
        "FROM personas p LEFT JOIN embeddings e ON e.persona_id=p.id\n"
        "GROUP BY p.id ORDER BY fotos ASC;",
        language="sql",
    )
