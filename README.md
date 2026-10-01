# 🎥 Sistema de Videovigilancia con Visión Artificial — Fase 1

Detección de personal **no autorizado** en zonas restringidas usando cámaras de
celular como reemplazo de cámaras de seguridad.

| Componente | Tecnología |
|---|---|
| Cámara | App **IP Webcam** (Android) → stream MJPEG, o webcam de la PC |
| Backend | Python + **FastAPI** (motor de visión en hilo dedicado) |
| Frontend | **Streamlit** (panel web) |
| Detección de personas | **YOLOv8** (Ultralytics) |
| Reconocimiento facial | **InsightFace / ArcFace** (embeddings de 512 dims) |
| Base de datos | **MySQL 8** (WampServer) con PyMySQL + SQLAlchemy |
| Alertas | Alarma sonora del PC + Telegram |

> **No se reentrena ningún modelo.** Cada rostro se convierte en un vector de
> 512 floats guardado en MySQL. En tiempo real se compara por **similitud
> coseno**: registrar una persona nueva es un simple `INSERT`.

---

## 1. Puesta en marcha rápida

```cmd
:: 1) Crear la base de datos (una sola vez)
crear_base_datos.bat

:: 2) Configurar cámara y credenciales
copy .env.example .env
notepad .env

:: 3) Arrancar el backend  (terminal 1)
iniciar_backend.bat

:: 4) Arrancar la interfaz  (terminal 2)
iniciar_frontend.bat
```

| Servicio | URL |
|---|---|
| Interfaz Streamlit | http://localhost:8501 |
| API (documentación) | http://localhost:8000/docs |
| Stream MJPEG directo | http://localhost:8000/api/stream |

### Instalación manual (equivalente)

```cmd
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
mysql -u root -p < sql\schema.sql
uvicorn backend.main:app --host 0.0.0.0 --port 8000
streamlit run frontend\app.py
```

---

## 2. Estructura del proyecto

```
.
├── backend/                     API FastAPI + motor de visión
│   ├── main.py                  aplicación, routers, arranque del monitor
│   ├── config.py                ajustes (cámara, umbrales, MySQL, Telegram)
│   ├── db.py                    engine SQLAlchemy + sesiones
│   ├── models.py                tablas ORM (personas, embeddings, zonas, eventos)
│   ├── schemas.py               esquemas Pydantic
│   ├── utils.py                 decodificación de imágenes y polígonos
│   ├── vision/
│   │   ├── detector.py          YOLOv8 — cajas de personas
│   │   ├── face.py              embeddings ArcFace + similitud coseno + caché
│   │   ├── zone.py              pointPolygonTest (punto de los pies)
│   │   └── pipeline.py          Monitor: hilo que analiza y publica fotogramas
│   ├── alerts/
│   │   ├── telegram.py          aviso a seguridad con foto del intruso
│   │   └── buzzer.py            alarma sonora
│   ├── api/
│   │   ├── personas.py          registro, ampliación, baja, fotos
│   │   ├── zonas.py             alta/edición/baja de polígonos
│   │   ├── eventos.py           historial, snapshots, stream, estado
│   │   └── sistema.py           configuración y diagnóstico
│   └── storage/                 vacío a propósito (las fotos van en MySQL)
├── frontend/                    interfaz Streamlit
│   ├── app.py                   entrada + navegación multipágina
│   ├── cliente.py               cliente HTTP de la API
│   ├── estilo.py                estilos y helpers visuales
│   └── pages/
│       ├── vision.py            panel en vivo + alarma
│       ├── registro.py          alta de personal y registro en caliente
│       ├── personas.py          gestión y activación
│       ├── zonas.py             editor de polígonos con vista previa
│       ├── eventos.py           historial con snapshots
│       └── ajustes.py           diagnóstico, backup y SQL útil
├── sql/schema.sql               creación de BD, usuario y tablas
├── modelos/                     pesos YOLO locales (yolov8n.pt)
├── backups/                     respaldos generados por respaldo.bat
├── .env.example                 plantilla de configuración
├── iniciar_backend.bat
├── iniciar_frontend.bat
├── crear_base_datos.bat
├── respaldo.bat
└── requirements.txt
```

---

## 3. Configuración (`.env`)

| Variable | Por defecto | Descripción |
|---|---|---|
| `CAMARA_URL` | `http://192.168.1.50:8080/video` | IP Webcam, `0` para la webcam de la PC, o ruta a un video |
| `CAMARA_BACKEND` | `auto` | backend OpenCV para webcam local: `auto`, `dshow` o `msmf` |
| `CAMARA_BACKEND_REINTENTOS` | `3` | fallos seguidos antes de probar con otro backend |
| `CAMARA_CONGELADA_MAX` | `50` | fotogramas idénticos seguidos antes de reabrir la cámara |
| `CAMARA_FPS` | `10` | fotogramas analizados por segundo |
| `FRAME_WIDTH` / `FRAME_HEIGHT` | `640` / `480` | resolución de trabajo |
| `YOLO_WEIGHTS` | `yolov8n.pt` | `yolov8n` rápido, `yolov8m` más preciso |
| `CONFIANZA_YOLO` | `0.40` | confianza mínima de YOLO |
| `FACE_MODEL` | `buffalo_sc` | modelo de InsightFace |
| `UMBRAL_FACIAL` | `0.55` | similitud coseno mínima para autorizar |
| `ROSTRO_MIN_PX` | `40` | tamaño mínimo del rostro para intentar reconocerlo |
| `DETECTAR_SIN_ZONAS` | `1` | sin zonas definidas, evalúa toda la imagen |
| `COOLDOWN_AUTORIZADO_S` | `30` | evita repetir el mismo acceso cada fotograma |
| `COOLDOWN_ALARMA_S` | `15` | evita disparar la alarma sin parar |
| `CONFIRMAR_DESCONOCIDO_N` | `6` | fotogramas seguidos con la misma cara desconocida antes de avisar a Telegram |
| `UMBRAL_DUDA` | `0.40` | desde esta similitud el aviso dice a quién se parece |
| `ALERMA_SONORA` | `1` | beep del sistema operativo |
| `ALERTA_SIN_ROSTRO` | `1` | alerta si hay persona en zona sin rostro visible |
| `TELEGRAM_TOKEN` / `TELEGRAM_CHAT` | vacíos | aviso opcional a seguridad |
| `DB_USER` / `DB_PASS` | `vigilancia` / `vigilancia123` | credenciales MySQL |

### Preparar el celular (IP Webcam)

1. Instala **IP Webcam** (Android) y pulsa «Iniciar servidor».
2. Anota la IP, p. ej. `http://192.168.1.50:8080`.
3. Comprueba en el navegador del PC que `http://192.168.1.50:8080/video` muestre video.
4. En el panel ve a **Ajustes → Fuente de video**, escribe la URL, pulsa
   **Probar esta fuente** y luego **Aplicar fuente y reiniciar motor**
   (ya no hace falta editar `.env` ni reiniciar a mano).

> ¿Sin cámara? Usa `CAMARA_URL=0` (webcam del PC) o la ruta a un archivo de video.

### Celular por cable USB (sin depender del WiFi)

**Opción A — Por red USB (recomendada).**
1. Conecta el celular al PC con el cable USB.
2. En Android: Ajustes → Conexiones → *Zona WiFi y conexión* → activa
   **Conexión USB** (tethering). El celular queda fijo en `192.168.42.129`.
3. Inicia el servidor en IP Webcam y usa `http://192.168.42.129:8080/video`
   como fuente. No importa que el WiFi cambie o se caiga.

**Opción B — Como webcam virtual.**
Instala **DroidCam** (o Iriun) en el celular y su programa cliente en el PC;
el celular aparece como una cámara más (normalmente índice `1`). En
**Ajustes → Fuente de video** usa «Detectar cámaras locales» para hallar el
índice y aplícalo.

---

## 4. Cómo funciona

1. El **monitor** (hilo de `pipeline.py`) lee la cámara a `CAMARA_FPS`.
2. **YOLOv8** detecta personas y devuelve cajas.
3. Se evalúa el **punto de los pies** (centro inferior de la caja) contra cada
   polígono de zona con `cv2.pointPolygonTest`.
4. Dentro de la zona se recorta el rostro y **ArcFace** genera un embedding de
   512 dims, normalizado.
5. Se compara con la matriz de embeddings guardados en MySQL (cargada en caché):
   - `similitud >= UMBRAL_FACIAL` → **autorizado** (caja verde + nombre)
   - `similitud <  UMBRAL_FACIAL` → **no autorizado** (caja roja + alarma)
6. Un desconocido solo genera evento y aviso a Telegram si la **misma cara
   persiste `CONFIRMAR_DESCONOCIDO_N` fotogramas seguidos**: así un autorizado
   no dispara alertas por un parpadeo de la similitud. Si se parece a alguien
   (`>= UMBRAL_DUDA`), el aviso dice a quién.
6. Los eventos se guardan en `eventos` con el snapshot JPEG del momento.
7. El frontend consume `/api/frame` (o `/api/stream` para MJPEG).

Caja verde = persona registrada · caja roja = intruso · gris = fuera de zona ·
amarillo = sin rostro detectable.

---

## 5. Base de datos

Todo vive en MySQL: **datos, fotos de registro y snapshots** (`LONGBLOB`).
Un solo `mysqldump` respalda el sistema completo.

| Tabla | Contenido |
|---|---|
| `personas` | datos del personal autorizado |
| `embeddings` | vector 512 floats + foto de registro (`LONGBLOB`) |
| `zonas` | polígonos restringidos (JSON) |
| `eventos` | historial de accesos con snapshot (`LONGBLOB`) |
| `logs_registro` | auditoría de los registros |

### Ajustes recomendados en `my.ini`

En WampServer: `C:\wamp64\bin\mysql\mysql8.4.7\my.ini`, bajo `[mysqld]`:

```ini
[mysqld]
max_allowed_packet = 64M
innodb_buffer_pool_size = 1G
character-set-server = utf8mb4
collation-server = utf8mb4_unicode_ci
```

Reinicia el servicio MySQL desde el icono de WampServer.

### Respaldo y restauración

```cmd
respaldo.bat
```

```cmd
:: restaurar
"C:\wamp64\bin\mysql\mysql8.4.7\bin\mysql.exe" -u vigilancia -pvigilancia123 ^
    vigilancia_cv < backups\vigilancia_20260101_0200.sql
```

Para purgar eventos antiguos, usa la página **Ajustes** del panel o:

```sql
DELETE FROM eventos WHERE timestamp < NOW() - INTERVAL 90 DAY;
```

---

## 6. API principal

| Método | Ruta | Descripción |
|---|---|---|
| `POST` | `/api/personas` | registra persona + embeddings (multipart `fotos[]`) |
| `POST` | `/api/personas/{id}/embeddings` | registro en caliente: más fotos |
| `PUT` | `/api/personas/{id}` | actualiza los datos de una persona |
| `GET` | `/api/personas` | lista el personal autorizado |
| `PATCH` | `/api/personas/{id}/activo` | activa/desactiva sin borrar |
| `DELETE` | `/api/personas/{id}` | elimina persona y embeddings |
| `GET` | `/api/personas/{id}/foto` | foto de registro (`image/jpeg`) |
| `POST` | `/api/zonas` | crea una zona (JSON `poligono`) |
| `PUT` | `/api/zonas/{id}` | actualiza la zona |
| `GET` | `/api/eventos` | historial (`limit`, `tipo`) |
| `GET` | `/api/eventos/{id}/snapshot` | foto del evento |
| `GET` | `/api/stream` | stream MJPEG |
| `GET` | `/api/frame` | último fotograma anotado |
| `GET` | `/api/estado` | estado del motor y detecciones |
| `POST` | `/api/monitor/{start\|stop\|reiniciar-cache}` | control del motor |
| `GET` | `/api/salud` | diagnóstico (BD, InsightFace, YOLO) |

Ejemplo:

```bash
curl -X POST http://localhost:8000/api/personas ^
  -F "nombre=Ana Torres" -F "documento=CC123" ^
  -F "fotos=@ana1.jpg" -F "fotos=@ana2.jpg"

curl -X POST http://localhost:8000/api/zonas ^
  -H "Content-Type: application/json" ^
  -d "{\"nombre\":\"Entrada\",\"poligono\":[[100,300],[540,300],[540,470],[100,470]]}"
```

---

## 7. Configurar Telegram

1. Habla con `@BotFather` en Telegram y crea un bot → obtienes el **token**.
2. Escríbele algo a tu bot.
3. Abre `https://api.telegram.org/bot<TOKEN>/getUpdates` y copia el `chat_id`.
4. Pon `TELEGRAM_TOKEN` y `TELEGRAM_CHAT` en `.env`, reinicia el backend y
   prueba con el botón **«Enviar mensaje de prueba»** en *Ajustes*.

---

## 8. Ajustar la detección

| Síntoma | Ajuste |
|---|---|
| Reconoce a desconocidos | sube `UMBRAL_FACIAL` a `0.62`–`0.68` |
| No reconoce a los suyos | baja `UMBRAL_FACIAL` a `0.45`–`0.50` |
| Falla con poca luz | sube `FACE_MODEL` a `buffalo_l` |
| Reconocimiento débil | registra 3-5 fotos por persona |
| Video lento | baja `CAMARA_FPS` a `5` y `FRAME_WIDTH` a `480` |
| No detecta la entrada a la zona | revisa el polígono: debe cubrir los pies |

---

## 9. Riesgos y consideraciones

| Riesgo | Mitigación |
|---|---|
| Falsos positivos/negativos | umbral ajustable + varias fotos por persona |
| Suplantación con foto | anti-spoofing (liveness) — fuera de alcance en esta fase |
| Persona de espaldas | evento «sin rostro detectable» (configurable) |
| Cámara se cae | reintento automático con espera configurable |
| Base de datos crece (`LONGBLOB`) | purga periódica de eventos antiguos |
| Privacidad / datos biométricos | fotos y vectores son datos sensibles: aplica la normativa local, obtén consentimiento escrito y restringe el acceso |
| Pérdida de conexión MySQL | `pool_pre_ping` + `pool_recycle` en `backend/db.py` |

---

**Licencia:** uso interno / educativo.
Los modelos preentrenados (YOLOv8, ArcFace) tienen sus propias licencias
(uso no comercial en el caso de InsightFace).
