# 🎥 Sistema de Videovigilancia con Visión Artificial — Fase 1 (MySQL)

Sistema de detección de personal no autorizado en zonas restringidas usando cámaras de celular como reemplazo de cámaras/robots de seguridad en esta primera fase.

> **Nota sobre esta guía:** el proyecto actual usa `frontend/app.py` con
> Streamlit. Este archivo conserva partes del diseño del prototipo HTML para
> referencia técnica; la instalación y el uso actual están documentados en
> `README.md`. Las instrucciones de las secciones 9 y 10 no describen rutas
> activas del proyecto.

**Características principales:**
- ✅ Detección de personas en tiempo real (YOLOv8)
- ✅ Reconocimiento facial por **embeddings** (sin reentrenar modelo)
- ✅ Registro de personas nuevas en caliente (foto + datos)
- ✅ Definición de zonas restringidas (polígonos)
- ✅ Alarma sonora + aviso a seguridad por Telegram
- ✅ Registro histórico de accesos
- ✅ **Base de datos MySQL** (datos + fotos + snapshots en `LONGBLOB`)

---

## 📑 Tabla de contenidos

1. [Arquitectura general](#1-arquitectura-general)
2. [Concepto clave: embeddings sin reentrenamiento](#2-concepto-clave-embeddings-sin-reentrenamiento)
3. [Requisitos](#3-requisitos)
4. [Estructura del proyecto](#4-estructura-del-proyecto)
5. [Instalación de MySQL](#5-instalación-de-mysql)
6. [Base de datos MySQL](#6-base-de-datos-mysql)
7. [Backend — API](#7-backend--api)
8. [Motor de visión](#8-motor-de-visión)
9. [Interfaz de Registro](#9-interfaz-de-registro)
10. [Interfaz de Visión](#10-interfaz-de-visión)
11. [Sistema de alertas](#11-sistema-de-alertas)
12. [Instalación y ejecución](#12-instalación-y-ejecución)
13. [Backup y mantenimiento](#13-backup-y-mantenimiento)
14. [Roadmap](#14-roadmap)
15. [Riesgos y consideraciones](#15-riesgos-y-consideraciones)

---

## 1. Arquitectura general

```
┌─────────────────┐      ┌──────────────────┐      ┌─────────────────┐
│  Cámara celular │─────▶│  Backend (API)   │◀────▶│  MySQL Server   │
│ (IP Webcam/RTSP)│      │  + Motor CV      │      │ (datos + fotos) │
└─────────────────┘      └────────┬─────────┘      └─────────────────┘
                                  │
                       ┌──────────┴───────────┐
                       │                      │
                 ┌─────▼─────┐         ┌──────▼──────┐
                 │ Interfaz  │         │  Interfaz   │
                 │ Registro  │         │   Visión    │
                 │ (web)     │         │  (web)      │
                 └───────────┘         └──────┬──────┘
                                              │
                                       ┌──────▼──────┐
                                       │ Alarma /    │
                                       │ Aviso Seg.  │
                                       └─────────────┘
```

| Componente | Tecnología |
|---|---|
| Cámara | App "IP Webcam" (Android) → stream MJPEG |
| Backend | Python + FastAPI |
| Motor de visión | OpenCV + YOLOv8 (personas) + InsightFace (rostros) |
| Base de datos | **MySQL 8.0+** |
| Driver DB | `mysqlclient` (o `PyMySQL`) |
| Frontend | HTML + JS |
| Notificaciones | Telegram Bot / SMTP |

> 📝 **Todo se guarda en MySQL**, incluidas las fotos de registro y los snapshots de intrusos (`LONGBLOB`). Un solo backup (`mysqldump`) cubre el sistema completo.

---

## 2. Concepto clave: embeddings sin reentrenamiento

Evita "clasificador de N personas" (eso sí requiere reentrenar). Usa **similitud de embeddings**:

1. Cada rostro → vector de **512 dimensiones** (ArcFace/InsightFace).
2. Vectores guardados en MySQL como `BLOB` (2048 bytes cada uno).
3. En tiempo real: embedding nuevo → **similitud coseno** vs todos los de la BD.
   - `similitud > 0.55` → **autorizado**
   - si no → **no autorizado / desconocido**

✅ Registrar persona nueva = **INSERT de un vector**. Cero reentrenamiento.

---

## 3. Requisitos

**Hardware:**
- PC (CPU basta para YOLOv8n + InsightFace; GPU opcional).
- Celular Android con app **IP Webcam** en la misma red WiFi.
- **MySQL Server 8.0+** instalado localmente.

**Software:**
- Python 3.10+
- pip
- MySQL Server (ver sección 5)

**`requirements.txt`:**

```txt
fastapi==0.115.0
uvicorn[standard]==0.30.6
opencv-python==4.10.0.84
ultralytics==8.3.0
insightface==0.7.3
onnxruntime==1.19.2
numpy==1.26.4
pillow==10.4.0
python-multipart==0.0.9
python-telegram-bot==21.5
sqlalchemy==2.0.35
pydantic==2.9.2
jinja2==3.1.4
mysqlclient==2.2.4
# Alternativa si mysqlclient falla al compilar:
# PyMySQL==1.1.1
# cryptography==43.0.1
```

---

## 4. Estructura del proyecto

```
vigilancia_cv/
├── backend/
│   ├── __init__.py
│   ├── main.py               # FastAPI app
│   ├── config.py             # umbrales, tokens, URL MySQL
│   ├── db.py                 # engine + sesión SQLAlchemy
│   ├── models.py             # tablas ORM (MySQL)
│   ├── schemas.py            # pydantic
│   ├── vision/
│   │   ├── __init__.py
│   │   ├── detector.py       # YOLO personas
│   │   ├── face.py           # embeddings + matching
│   │   ├── zone.py           # pointPolygonTest
│   │   └── pipeline.py       # orquesta todo
│   ├── alerts/
│   │   ├── __init__.py
│   │   ├── telegram.py
│   │   └── buzzer.py
│   ├── api/
│   │   ├── __init__.py
│   │   ├── registro.py
│   │   ├── vision.py
│   │   └── zonas.py
│   └── storage/
│       └── (vacío — las fotos van en MySQL)
├── frontend/
│   ├── registro.html
│   └── vision.html
├── sql/
│   └── schema.sql            # script de creación MySQL
├── requirements.txt
└── README.md
```

---

## 5. Instalación de MySQL

### 5.1 Instalar MySQL Server

**Windows:**
1. Descarga **MySQL Installer** desde https://dev.mysql.com/downloads/installer/
2. Selecciona "Server only" (o "Full" si quieres Workbench).
3. Durante la instalación:
   - Tipo: **Development Computer**
   - Puerto: **3306** (por defecto)
   - Autenticación: **Use Strong Password Encryption**
   - Define contraseña de `root` y **guárdala**.
4. Al terminar, verifica que el servicio esté corriendo:
   ```cmd
   sc query MySQL80
   ```

**Linux (Ubuntu/Debian):**
```bash
sudo apt update
sudo apt install mysql-server -y
sudo systemctl enable --now mysql
sudo mysql_secure_installation
```

**macOS (Homebrew):**
```bash
brew install mysql
brew services start mysql
mysql_secure_installation
```

### 5.2 Verificar instalación

```bash
mysql --version
# mysql  Ver 8.0.xx for ...
```

### 5.3 Crear base de datos y usuario

Entra como root:

```bash
mysql -u root -p
```

Ejecuta:

```sql
CREATE DATABASE vigilancia_cv
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

CREATE USER 'vigilancia'@'localhost' IDENTIFIED BY 'CambiaEstaClave123!';
GRANT ALL PRIVILEGES ON vigilancia_cv.* TO 'vigilancia'@'localhost';
FLUSH PRIVILEGES;

-- Verificar
SHOW DATABASES;
SELECT user, host FROM mysql.user WHERE user = 'vigilancia';
EXIT;
```

### 5.4 Ajustes de `my.cnf` / `my.ini` (para permitir fotos grandes)

Localiza el archivo:
- **Windows:** `C:\ProgramData\MySQL\MySQL Server 8.0\my.ini`
- **Linux:** `/etc/mysql/mysql.conf.d/mysqld.cnf`
- **macOS:** `/opt/homebrew/etc/my.cnf`

Añade o edita bajo `[mysqld]`:

```ini
[mysqld]
max_allowed_packet = 64M
innodb_log_file_size = 256M
innodb_buffer_pool_size = 1G
character-set-server = utf8mb4
collation-server = utf8mb4_unicode_ci
```

Reinicia MySQL:

```bash
# Windows
net stop MySQL80 && net start MySQL80

# Linux
sudo systemctl restart mysql

# macOS
brew services restart mysql
```

---

## 6. Base de datos MySQL

### 6.1 Script completo — `sql/schema.sql`

```sql
-- Crear base de datos
CREATE DATABASE IF NOT EXISTS vigilancia_cv
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE vigilancia_cv;

-- ---------------------------------------------------------------
-- Personas autorizadas
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS personas (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    nombre          VARCHAR(150) NOT NULL,
    documento       VARCHAR(50) UNIQUE,
    cargo           VARCHAR(100),
    email           VARCHAR(150),
    telefono        VARCHAR(50),
    fecha_registro  DATETIME DEFAULT CURRENT_TIMESTAMP,
    activo          TINYINT(1) DEFAULT 1
) ENGINE=InnoDB;

-- ---------------------------------------------------------------
-- Embeddings faciales + foto (LONGBLOB)
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS embeddings (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    persona_id  INT NOT NULL,
    vector      BLOB       NOT NULL,   -- float32[512] = 2048 bytes
    foto        LONGBLOB,              -- foto de registro (JPEG)
    foto_mime   VARCHAR(50) DEFAULT 'image/jpeg',
    FOREIGN KEY (persona_id) REFERENCES personas(id) ON DELETE CASCADE,
    INDEX idx_emb_persona (persona_id)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------
-- Zonas restringidas
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS zonas (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    nombre     VARCHAR(100) NOT NULL,
    poligono   TEXT NOT NULL,          -- JSON: [[x1,y1],[x2,y2],...]
    camara_id  VARCHAR(50) DEFAULT 'cam0'
) ENGINE=InnoDB;

-- ---------------------------------------------------------------
-- Eventos / accesos + snapshot (LONGBLOB)
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS eventos (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    timestamp     DATETIME DEFAULT CURRENT_TIMESTAMP,
    persona_id    INT NULL,
    tipo          ENUM('autorizado','no_autorizado') NOT NULL,
    zona_id       INT NULL,
    similitud     FLOAT,
    snapshot      LONGBLOB,            -- imagen del momento (JPEG)
    FOREIGN KEY (persona_id) REFERENCES personas(id) ON DELETE SET NULL,
    FOREIGN KEY (zona_id)    REFERENCES zonas(id)    ON DELETE SET NULL,
    INDEX idx_eventos_ts (timestamp DESC)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------
-- Log de registros (auditoría)
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS logs_registro (
    id                 INT AUTO_INCREMENT PRIMARY KEY,
    persona_id         INT NULL,
    ts                 DATETIME DEFAULT CURRENT_TIMESTAMP,
    embeddings_creados INT,
    mensaje            VARCHAR(255),
    FOREIGN KEY (persona_id) REFERENCES personas(id) ON DELETE SET NULL
) ENGINE=InnoDB;
```

Aplicar el script:

```bash
mysql -u vigilancia -p vigilancia_cv < sql/schema.sql
```

Verificar:

```bash
mysql -u vigilancia -p -e "USE vigilancia_cv; SHOW TABLES; DESCRIBE embeddings;"
```

### 6.2 Modelos ORM — `backend/models.py`

```python
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, ForeignKey,
    LargeBinary, Float, Text, Enum, Index
)
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime

Base = declarative_base()

LONGBLOB_LEN = 2**32 - 1   # 4 GB — SQLAlchemy lo traduce a LONGBLOB en MySQL

class Persona(Base):
    __tablename__ = "personas"
    id = Column(Integer, primary_key=True, autoincrement=True)
    nombre = Column(String(150), nullable=False)
    documento = Column(String(50), unique=True)
    cargo = Column(String(100))
    email = Column(String(150))
    telefono = Column(String(50))
    fecha_registro = Column(DateTime, default=datetime.utcnow)
    activo = Column(Boolean, default=True)

    embeddings = relationship("Embedding", back_populates="persona",
                              cascade="all, delete-orphan")

class Embedding(Base):
    __tablename__ = "embeddings"
    id = Column(Integer, primary_key=True, autoincrement=True)
    persona_id = Column(Integer,
                        ForeignKey("personas.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    vector = Column(LargeBinary, nullable=False)             # 2048 bytes
    foto = Column(LargeBinary(length=LONGBLOB_LEN))          # LONGBLOB
    foto_mime = Column(String(50), default="image/jpeg")

    persona = relationship("Persona", back_populates="embeddings")

class Zona(Base):
    __tablename__ = "zonas"
    id = Column(Integer, primary_key=True, autoincrement=True)
    nombre = Column(String(100), nullable=False)
    poligono = Column(Text, nullable=False)                  # JSON
    camara_id = Column(String(50), default="cam0")

class Evento(Base):
    __tablename__ = "eventos"
    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    persona_id = Column(Integer, ForeignKey("personas.id", ondelete="SET NULL"))
    tipo = Column(Enum("autorizado", "no_autorizado", name="tipo_evento"),
                  nullable=False)
    zona_id = Column(Integer, ForeignKey("zonas.id", ondelete="SET NULL"))
    similitud = Column(Float)
    snapshot = Column(LargeBinary(length=LONGBLOB_LEN))      # LONGBLOB

class LogRegistro(Base):
    __tablename__ = "logs_registro"
    id = Column(Integer, primary_key=True, autoincrement=True)
    persona_id = Column(Integer, ForeignKey("personas.id", ondelete="SET NULL"))
    ts = Column(DateTime, default=datetime.utcnow)
    embeddings_creados = Column(Integer)
    mensaje = Column(String(255))
```

### 6.3 Conexión MySQL — `backend/db.py`

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from .models import Base

# ---------- Configuración MySQL ----------
DB_USER = "vigilancia"
DB_PASS = "CambiaEstaClave123!"
DB_HOST = "localhost"
DB_PORT = 3306
DB_NAME = "vigilancia_cv"

# Opción 1 — mysqlclient (recomendado en producción)
DATABASE_URL = (
    f"mysql+mysqldb://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    "?charset=utf8mb4"
)

# Opción 2 — PyMySQL (más portátil, sin compilador C)
# DATABASE_URL = (
#     f"mysql+pymysql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
#     "?charset=utf8mb4"
# )

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,       # detecta conexiones caídas
    pool_recycle=280,         # recicla antes de wait_timeout
    pool_size=10,
    max_overflow=20,
    echo=False,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

def init_db():
    """Crea las tablas si no existen."""
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

---

## 7. Backend — API

### 7.1 `backend/config.py`

```python
CAMARA_URL      = "http://192.168.1.50:8080/video"  # IP del celular con IP Webcam
UMBRAL_FACIAL   = 0.55           # similitud coseno mínima
YOLO_WEIGHTS    = "yolov8n.pt"
FRAME_WIDTH     = 640
FRAME_HEIGHT    = 480
TELEGRAM_TOKEN  = "TU_TOKEN_AQUI"
TELEGRAM_CHAT   = "TU_CHAT_ID"
```

### 7.2 `backend/main.py`

```python
from fastapi import FastAPI, UploadFile, File, Form, Depends, HTTPException
from fastapi.responses import StreamingResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
import numpy as np, cv2, json
from datetime import datetime

from .db import init_db, get_db
from .models import Persona, Embedding, Zona, Evento, LogRegistro
from .vision.face import generar_embedding, buscar_persona
from .vision.pipeline import stream_frames, get_alarm_state
from .alerts.telegram import enviar_alerta

app = FastAPI(title="Vigilancia CV - MySQL")
init_db()

# ----------------------------------------------------------------
# REGISTRO DE PERSONAS
# ----------------------------------------------------------------
@app.post("/api/personas")
async def registrar_persona(
    nombre: str = Form(...),
    documento: str = Form(...),
    cargo: str = Form(""),
    email: str = Form(""),
    telefono: str = Form(""),
    fotos: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    if db.query(Persona).filter_by(documento=documento).first():
        raise HTTPException(400, "Documento ya registrado")

    persona = Persona(nombre=nombre, documento=documento, cargo=cargo,
                      email=email, telefono=telefono)
    db.add(persona)
    db.commit()
    db.refresh(persona)

    guardadas = 0
    for f in fotos:
        raw = await f.read()
        arr = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
        if arr is None:
            continue
        emb = generar_embedding(arr)
        if emb is None:
            continue

        # Re-codificar a JPEG para almacenamiento consistente
        ok, jpg = cv2.imencode(".jpg", arr, [cv2.IMWRITE_JPEG_QUALITY, 85])
        jpg_bytes = jpg.tobytes() if ok else raw

        db.add(Embedding(
            persona_id=persona.id,
            vector=emb.tobytes(),        # float32[512] → 2048 bytes
            foto=jpg_bytes,              # LONGBLOB
            foto_mime="image/jpeg",
        ))
        guardadas += 1

    db.add(LogRegistro(persona_id=persona.id,
                       embeddings_creados=guardadas,
                       mensaje="Registro vía API"))
    db.commit()

    if guardadas == 0:
        raise HTTPException(400, "Ninguna foto contiene un rostro válido")

    return {"ok": True, "persona_id": persona.id, "embeddings": guardadas}


@app.get("/api/personas")
def listar_personas(db: Session = Depends(get_db)):
    return [
        {"id": p.id, "nombre": p.nombre, "documento": p.documento,
         "cargo": p.cargo, "activo": p.activo,
         "num_embeddings": len(p.embeddings)}
        for p in db.query(Persona).all()
    ]


@app.get("/api/personas/{pid}/foto")
def foto_persona(pid: int, db: Session = Depends(get_db)):
    """Devuelve la primera foto registrada de la persona."""
    emb = (db.query(Embedding)
             .filter(Embedding.persona_id == pid)
             .order_by(Embedding.id.asc())
             .first())
    if not emb or not emb.foto:
        raise HTTPException(404, "Sin foto")
    return Response(content=emb.foto, media_type=emb.foto_mime or "image/jpeg")


@app.delete("/api/personas/{pid}")
def eliminar_persona(pid: int, db: Session = Depends(get_db)):
    p = db.query(Persona).get(pid)
    if not p:
        raise HTTPException(404)
    db.delete(p)
    db.commit()
    return {"ok": True}

# ----------------------------------------------------------------
# ZONAS
# ----------------------------------------------------------------
@app.post("/api/zonas")
def crear_zona(nombre: str = Form(...), poligono: str = Form(...),
               camara_id: str = Form("cam0"), db: Session = Depends(get_db)):
    json.loads(poligono)  # validar JSON
    z = Zona(nombre=nombre, poligono=poligono, camara_id=camara_id)
    db.add(z)
    db.commit()
    db.refresh(z)
    return {"ok": True, "id": z.id}


@app.get("/api/zonas")
def listar_zonas(db: Session = Depends(get_db)):
    return [{"id": z.id, "nombre": z.nombre,
             "poligono": json.loads(z.poligono)}
            for z in db.query(Zona).all()]


@app.delete("/api/zonas/{zid}")
def eliminar_zona(zid: int, db: Session = Depends(get_db)):
    z = db.query(Zona).get(zid)
    if not z:
        raise HTTPException(404)
    db.delete(z)
    db.commit()
    return {"ok": True}

# ----------------------------------------------------------------
# VISIÓN / EVENTOS
# ----------------------------------------------------------------
@app.get("/api/stream")
def stream():
    return StreamingResponse(stream_frames(),
                             media_type="multipart/x-mixed-replace; boundary=frame")


@app.get("/api/eventos")
def eventos(limit: int = 50, db: Session = Depends(get_db)):
    rows = (db.query(Evento)
              .order_by(Evento.timestamp.desc())
              .limit(limit).all())
    return [
        {"id": e.id,
         "ts": e.timestamp.isoformat(),
         "persona_id": e.persona_id,
         "tipo": e.tipo,
         "similitud": e.similitud,
         "tiene_snapshot": e.snapshot is not None}
        for e in rows
    ]


@app.get("/api/eventos/{eid}/snapshot")
def snapshot_evento(eid: int, db: Session = Depends(get_db)):
    ev = db.query(Evento).get(eid)
    if not ev or not ev.snapshot:
        raise HTTPException(404)
    return Response(content=ev.snapshot, media_type="image/jpeg")


@app.get("/api/alarma")
def alarma():
    return {"activa": get_alarm_state()}

# ----------------------------------------------------------------
# FRONTEND
# ----------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def home():
    return open("frontend/vision.html", encoding="utf-8").read()


@app.get("/registro", response_class=HTMLResponse)
def registro_ui():
    return open("frontend/registro.html", encoding="utf-8").read()
```

---

## 8. Motor de visión

### 8.1 `backend/vision/face.py`

```python
import cv2, numpy as np
from insightface.app import FaceAnalysis
from sqlalchemy.orm import Session
from ..db import SessionLocal
from ..models import Embedding, Persona

# Modelo preentrenado — NO se reentrena
_app = FaceAnalysis(name="buffalo_sc", providers=["CPUExecutionProvider"])
_app.prepare(ctx_id=0, det_size=(640, 640))


def generar_embedding(frame_bgr: np.ndarray) -> np.ndarray | None:
    """Devuelve vector float32[512] normalizado del rostro más grande."""
    if frame_bgr is None or frame_bgr.size == 0:
        return None
    faces = _app.get(frame_bgr)
    if not faces:
        return None
    face = max(faces, key=lambda f: (f.bbox[2]-f.bbox[0])*(f.bbox[3]-f.bbox[1]))
    return face.normed_embedding.astype(np.float32)


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b))  # vectores ya normalizados


def buscar_persona(emb: np.ndarray, umbral: float):
    """Compara contra todos los embeddings activos. Devuelve (persona, sim) o (None, sim)."""
    db: Session = SessionLocal()
    try:
        rows = (db.query(Embedding)
                  .join(Persona)
                  .filter(Persona.activo == True)
                  .all())
        if not rows:
            return None, 0.0

        # Búsqueda vectorizada con NumPy
        matriz = np.vstack([np.frombuffer(r.vector, dtype=np.float32) for r in rows])
        sims = matriz @ emb                    # similitud coseno
        idx = int(np.argmax(sims))
        mejor_sim = float(sims[idx])
        if mejor_sim >= umbral:
            return rows[idx].persona, mejor_sim
        return None, mejor_sim
    finally:
        db.close()
```

### 8.2 `backend/vision/detector.py`

```python
from ultralytics import YOLO
import numpy as np
from ..config import YOLO_WEIGHTS

_model = YOLO(YOLO_WEIGHTS)

def detectar_personas(frame: np.ndarray):
    """Devuelve lista de bboxes (x1,y1,x2,y2) de personas."""
    res = _model.predict(frame, classes=[0], verbose=False, conf=0.4)[0]
    return [tuple(map(int, b)) for b in res.boxes.xyxy.cpu().numpy()]
```

### 8.3 `backend/vision/zone.py`

```python
import cv2, numpy as np, json

def punto_en_zona(bbox, poligono_pts):
    """bbox = (x1,y1,x2,y2). Usa el punto de los pies (centro-abajo)."""
    cx = int((bbox[0] + bbox[2]) / 2)
    cy = int(bbox[3])
    return cv2.pointPolygonTest(poligono_pts, (cx, cy), False) >= 0


def cargar_poligono(json_str: str) -> np.ndarray:
    pts = np.array(json.loads(json_str), dtype=np.int32)
    return pts.reshape((-1, 1, 2))
```

### 8.4 `backend/vision/pipeline.py`

```python
import cv2, time, threading
import numpy as np
from datetime import datetime
from .detector import detectar_personas
from .face import generar_embedding, buscar_persona
from .zone import punto_en_zona, cargar_poligono
from ..config import CAMARA_URL, UMBRAL_FACIAL
from ..db import SessionLocal
from ..models import Zona, Evento
from ..alerts.telegram import enviar_alerta
from ..alerts.buzzer import sonar_alarma

_alarm_active = False
_alarm_lock = threading.Lock()


def get_alarm_state():
    return _alarm_active


def _set_alarm(v: bool):
    global _alarm_active
    with _alarm_lock:
        _alarm_active = v


def _zonas_activas():
    db = SessionLocal()
    try:
        return [(z.id, z.nombre, cargar_poligono(z.poligono))
                for z in db.query(Zona).all()]
    finally:
        db.close()


def _guardar_evento(persona_id, tipo, zona_id, sim, snapshot_bytes=None):
    db = SessionLocal()
    try:
        ev = Evento(persona_id=persona_id, tipo=tipo, zona_id=zona_id,
                    similitud=sim, snapshot=snapshot_bytes)
        db.add(ev)
        db.commit()
    finally:
        db.close()


def _cooldown_ok(persona_id, segundos=10):
    """Evita repetir eventos de la misma persona en < N segundos."""
    db = SessionLocal()
    try:
        last = (db.query(Evento)
                  .filter(Evento.persona_id == persona_id)
                  .order_by(Evento.timestamp.desc())
                  .first())
        if last and (datetime.utcnow() - last.timestamp).total_seconds() < segundos:
            return False
        return True
    finally:
        db.close()


def stream_frames():
    cap = cv2.VideoCapture(CAMARA_URL)
    zonas = _zonas_activas()

    while True:
        ok, frame = cap.read()
        if not ok:
            time.sleep(0.5)
            continue

        frame = cv2.resize(frame, (640, 480))
        personas = detectar_personas(frame)

        # Dibuja zonas
        for _, nombre, poly in zonas:
            cv2.polylines(frame, [poly], True, (255, 200, 0), 2)
            cv2.putText(frame, nombre, tuple(poly[0][0]),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 200, 0), 1)

        for bbox in personas:
            en_zona = any(punto_en_zona(bbox, poly) for _, _, poly in zonas)
            if not en_zona:
                cv2.rectangle(frame, (bbox[0], bbox[1]), (bbox[2], bbox[3]),
                              (150, 150, 150), 2)
                continue

            x1, y1, x2, y2 = bbox
            roi = frame[y1:y2, x1:x2]
            emb = generar_embedding(roi)
            persona, sim = (None, 0.0) if emb is None else buscar_persona(emb, UMBRAL_FACIAL)

            if persona is not None:
                color, etiqueta = (0, 255, 0), f"{persona.nombre} ({sim:.2f})"
                if _cooldown_ok(persona.id):
                    _guardar_evento(persona.id, "autorizado",
                                    zonas[0][0] if zonas else None, sim)
                _set_alarm(False)
            else:
                color, etiqueta = (0, 0, 255), f"NO AUTORIZADO ({sim:.2f})"
                ok_jpg, jpg = cv2.imencode(".jpg", frame,
                                           [cv2.IMWRITE_JPEG_QUALITY, 80])
                _guardar_evento(None, "no_autorizado",
                                zonas[0][0] if zonas else None, sim,
                                snapshot_bytes=jpg.tobytes() if ok_jpg else None)
                _set_alarm(True)
                sonar_alarma()
                enviar_alerta(jpg.tobytes() if ok_jpg else None, sim)
                time.sleep(1)   # anti-spam alarma

            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            cv2.putText(frame, etiqueta, (x1, y1 - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

        if _alarm_active:
            cv2.rectangle(frame, (0, 0), (frame.shape[1], 30), (0, 0, 255), -1)
            cv2.putText(frame, "ALARMA: PERSONA NO AUTORIZADA",
                        (10, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                        (255, 255, 255), 2)

        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
        if not ok:
            continue
        yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
               + buf.tobytes() + b"\r\n")
```

---

## 9. Interfaz de Registro

### `frontend/registro.html`

```html
<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8"/>
<title>Registro de Personal Autorizado</title>
<style>
  body{font-family:Arial;max-width:720px;margin:24px auto;padding:16px;background:#f4f6f9}
  h1{color:#1a3d6d}
  label{display:block;margin-top:12px;font-weight:bold}
  input,button{padding:8px;width:100%;box-sizing:border-box;margin-top:4px}
  button{background:#1a3d6d;color:#fff;border:0;cursor:pointer;border-radius:6px}
  button:hover{background:#2a5aa0}
  #msg{margin-top:16px;padding:12px;border-radius:6px;display:none}
  .ok{background:#d4edda;color:#155724}
  .err{background:#f8d7da;color:#721c24}
</style>
</head>
<body>
  <h1>👤 Registro de Personal Autorizado</h1>
  <form id="f">
    <label>Nombre completo*</label><input name="nombre" required>
    <label>Documento / ID*</label><input name="documento" required>
    <label>Cargo</label><input name="cargo">
    <label>Email</label><input type="email" name="email">
    <label>Teléfono</label><input name="telefono">
    <label>Fotos (1 a 5, rostro frontal)*</label>
    <input type="file" name="fotos" accept="image/*" multiple required>
    <button type="submit">Registrar</button>
  </form>
  <div id="msg"></div>
  <p><a href="/">← Ir al panel de visión</a></p>

<script>
document.getElementById('f').addEventListener('submit', async e => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const msg = document.getElementById('msg');
  try {
    const r = await fetch('/api/personas', {method:'POST', body:fd});
    const j = await r.json();
    if (!r.ok) throw new Error(j.detail || 'Error');
    msg.className='ok';
    msg.textContent = `✅ Registrado. Persona ID ${j.persona_id}, embeddings: ${j.embeddings}`;
    msg.style.display='block';
    e.target.reset();
  } catch(err) {
    msg.className='err';
    msg.textContent = '❌ ' + err.message;
    msg.style.display='block';
  }
});
</script>
</body>
</html>
```

---

## 10. Interfaz de Visión

### `frontend/vision.html`

```html
<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8"/>
<title>Panel de Videovigilancia</title>
<style>
  body{font-family:Arial;margin:0;background:#0f172a;color:#e2e8f0}
  header{background:#1e293b;padding:12px 24px;display:flex;justify-content:space-between}
  h1{margin:0;font-size:18px}
  a{color:#60a5fa}
  .grid{display:grid;grid-template-columns:2fr 1fr;gap:16px;padding:16px}
  .card{background:#1e293b;border-radius:8px;padding:12px}
  img.stream{width:100%;border-radius:6px;display:block}
  ul{list-style:none;padding:0;margin:0;max-height:600px;overflow-y:auto}
  li{padding:8px;border-bottom:1px solid #334155;font-size:13px;
     display:flex;align-items:center;gap:8px}
  .auth{color:#22c55e}
  .noauth{color:#ef4444;font-weight:bold}
  .thumb{height:36px;border-radius:4px}
  #alarmBar{background:#ef4444;padding:10px;text-align:center;font-weight:bold;display:none}
</style>
</head>
<body>
  <div id="alarmBar">⚠ ALARMA ACTIVA: INTRUSO DETECTADO</div>
  <header>
    <h1>🎥 Panel de Videovigilancia</h1>
    <nav><a href="/registro">Registrar persona</a></nav>
  </header>

  <div class="grid">
    <div class="card">
      <img class="stream" src="/api/stream" alt="stream en vivo"/>
    </div>
    <div class="card">
      <h3>📋 Últimos eventos</h3>
      <ul id="ev"></ul>
    </div>
  </div>

<script>
async function refrescar(){
  try {
    const r = await fetch('/api/eventos?limit=30');
    const data = await r.json();
    document.getElementById('ev').innerHTML = data.map(e => {
      const cls = e.tipo === 'autorizado' ? 'auth' : 'noauth';
      const ico = e.tipo === 'autorizado' ? '✅' : '🚨';
      const sim = e.similitud != null ? e.similitud.toFixed(2) : '-';
      const thumb = e.tiene_snapshot
        ? `<img class="thumb" src="/api/eventos/${e.id}/snapshot"/>`
        : '';
      return `<li class="${cls}">${thumb}${ico} 
              ${new Date(e.ts).toLocaleTimeString()} — ${e.tipo} 
              (sim=${sim}) ${e.persona_id ? 'ID:'+e.persona_id : ''}</li>`;
    }).join('');
  } catch(_) {}

  try {
    const a = await (await fetch('/api/alarma')).json();
    document.getElementById('alarmBar').style.display = a.activa ? 'block' : 'none';
  } catch(_) {}
}
setInterval(refrescar, 2000);
refrescar();
</script>
</body>
</html>
```

---

## 11. Sistema de alertas

### `backend/alerts/buzzer.py`

```python
import threading, platform, os

def _beep():
    try:
        if platform.system() == "Windows":
            import winsound
            for _ in range(3):
                winsound.Beep(1000, 400)
        elif platform.system() == "Darwin":
            os.system("afplay /System/Library/Sounds/Sosumi.aiff")
        else:
            print("\a", end="", flush=True)
    except Exception:
        pass

def sonar_alarma():
    threading.Thread(target=_beep, daemon=True).start()
```

### `backend/alerts/telegram.py`

```python
import requests, io
from ..config import TELEGRAM_TOKEN, TELEGRAM_CHAT

def enviar_alerta(snapshot_bytes: bytes | None, similitud: float):
    """Envía foto de intruso a Telegram. Si no hay token, imprime en consola."""
    if not TELEGRAM_TOKEN or TELEGRAM_TOKEN.startswith("TU_"):
        print(f"[ALERTA] Intruso detectado (sim={similitud:.2f})")
        return
    try:
        files = None
        if snapshot_bytes:
            files = {"photo": ("intruso.jpg", io.BytesIO(snapshot_bytes), "image/jpeg")}
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto",
            data={"chat_id": TELEGRAM_CHAT,
                  "caption": f"🚨 Persona NO autorizada en zona restringida\n"
                             f"Similitud: {similitud:.2f}"},
            files=files, timeout=10)
    except Exception as e:
        print("Error Telegram:", e)
```

---

## 12. Instalación y ejecución

### 12.1 Preparar el celular

1. Instalar **IP Webcam** en Android (Play Store).
2. Abrir la app → "Iniciar servidor".
3. Anotar la IP (ej. `http://192.168.1.50:8080`).
4. Verificar que PC y celular estén en la **misma red WiFi**.
5. Probar en el navegador del PC: `http://192.168.1.50:8080/video` → debe verse el video.

### 12.2 Preparar MySQL

```bash
# 1. Crear BD y usuario (ver sección 5.3)
mysql -u root -p < sql/schema.sql

# 2. Verificar conexión con el usuario de la app
mysql -u vigilancia -p -e "USE vigilancia_cv; SHOW TABLES;"
```

### 12.3 Preparar el proyecto

```bash
# 1. Estructura
mkdir vigilancia_cv && cd vigilancia_cv
mkdir -p backend/vision backend/alerts backend/api backend/storage frontend sql
touch backend/__init__.py backend/vision/__init__.py
touch backend/alerts/__init__.py backend/api/__init__.py

# 2. Entorno virtual
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 3. Dependencias
pip install -r requirements.txt

# Si mysqlclient falla al compilar en Windows, instala PyMySQL:
# pip install PyMySQL cryptography
# y en backend/db.py usa la URL con mysql+pymysql://

# 4. Ajustar backend/config.py con la IP del celular
#    CAMARA_URL = "http://192.168.1.50:8080/video"

# 5. Ajustar credenciales MySQL en backend/db.py

# 6. Crear tablas (o correr sql/schema.sql manualmente)
python -c "from backend.db import init_db; init_db()"

# 7. Correr el backend
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

### 12.4 Uso

1. Abrir `http://localhost:8501` → panel Streamlit.
2. Registrar personas desde **Registro de personal** (1-5 fotos).
3. Definir zonas desde **Zonas restringidas** o mediante `POST /api/zonas`:

```bash
curl -X POST http://localhost:8000/api/zonas \
  -H "Content-Type: application/json" \
  -d '{"nombre":"Entrada Principal","camara_id":"cam0","poligono":[[100,300],[500,300],[500,470],[100,470]]}'
```

4. Cuando alguien entra a la zona:
   - Reconocido → caja verde + nombre + evento "autorizado".
   - No reconocido → caja roja + **alarma sonora** + **snapshot en MySQL** + **aviso Telegram** + banner rojo en el panel.

### 12.5 Probar sin cámara real (webcam de la PC)

En `backend/vision/pipeline.py`, línea del `cap = cv2.VideoCapture(...)`:

```python
cap = cv2.VideoCapture(0)   # en lugar de CAMARA_URL
```

---

## 13. Backup y mantenimiento

### 13.1 Backup completo (datos + fotos + snapshots)

```bash
# Linux/macOS
mysqldump -u vigilancia -p --single-transaction --routines --triggers \
  vigilancia_cv > backup_$(date +%F_%H%M).sql
```

```cmd
:: Windows
mysqldump -u vigilancia -p --single-transaction --routines --triggers ^
  vigilancia_cv > backup_%date:~-4%%date:~3,2%%date:~0,2%.sql
```

Como las fotos y snapshots viven en `LONGBLOB`, **el dump contiene absolutamente todo**.

### 13.2 Restaurar

```bash
mysql -u vigilancia -p vigilancia_cv < backup_2025-01-01.sql
```

### 13.3 Programar backup automático

**Linux (cron):**
```bash
crontab -e
# Todos los días a las 2 AM
0 2 * * * mysqldump -u vigilancia -p'TuClave' --single-transaction \
  vigilancia_cv > /ruta/backups/vig_$(date +\%F).sql
```

**Windows (Task Scheduler):**
1. Crear tarea básica → diaria 02:00.
2. Acción: iniciar programa `mysqldump.exe`.
3. Argumentos:
   ```
   -u vigilancia -p"TuClave" --single-transaction vigilancia_cv
   -r "C:\backups\vig_%date:~-4%%date:~3,2%%date:~0,2%.sql"
   ```

### 13.4 Mantenimiento periódico

```sql
-- Ver tamaño de la BD
SELECT table_name,
       ROUND(((data_length + index_length) / 1024 / 1024), 2) AS MB
FROM information_schema.tables
WHERE table_schema = 'vigilancia_cv'
ORDER BY (data_length + index_length) DESC;

-- Purgar snapshots de eventos autorizados con más de 90 días (opcional)
UPDATE eventos
SET snapshot = NULL
WHERE tipo = 'autorizado'
  AND timestamp < NOW() - INTERVAL 90 DAY;

-- Eliminar eventos no autorizados con más de 1 año (ajusta a tu política)
DELETE FROM eventos
WHERE tipo = 'no_autorizado'
  AND timestamp < NOW() - INTERVAL 365 DAY;
```

---


## 14. Riesgos y consideraciones

| Riesgo | Mitigación |
|---|---|
| Falsos positivos/negativos | Umbral ajustable (`UMBRAL_FACIAL`) + doble verificación |
| Iluminación pobre | Preprocesado (CLAHE), cámara con IR |
| Suplantación con foto | Anti-spoofing (liveness) — **fase 2** |
| Latencia del celular | Reducir resolución, YOLO-nano, JPEG calidad 75 |
| Privacidad / datos biométricos | Cifrar embeddings, consentimiento firmado, cumplir ley local |
| Persona de espaldas | Alerta "persona no identificada en zona" también |
| Cámara se cae | Retry automático en `stream_frames` |
| BD crece mucho (LONGBLOB) | Purga periódica (sección 13.4) o migrar a disco en fase 2 |
| `mysqlclient` no compila en Windows | Usar `PyMySQL` (ver sección 12.3) |
| Pérdida de conexión MySQL | `pool_pre_ping=True` + `pool_recycle=280` ya configurados |

---

## Notas finales

- **No se reentrena el modelo nunca.** Registrar personas = insertar embeddings nuevos en MySQL.
- El umbral `UMBRAL_FACIAL = 0.55` es un buen punto de partida. Súbelo si hay falsos positivos, bájalo si hay falsos negativos.
- **`max_allowed_packet = 64M`** es obligatorio para permitir subir fotos grandes sin errores.
- Los embeddings biométricos **y las fotos** son **datos personales sensibles** — consulta la normativa de tu país (GDPR, Ley de Protección de Datos, etc.) antes de desplegar.
- Si en el futuro migras a producción con muchas personas, mueve las fotos/snapshots a disco o S3 y deja MySQL solo con metadatos + embeddings. La estructura actual ya lo permite sin rediseño.

---

**Autor:** Proyecto de Videovigilancia CV — Fase 1 (MySQL)
**Licencia:** Uso interno / educativo
