-- =====================================================================
--  Sistema de Videovigilancia con Visión Artificial — Fase 1 (MySQL)
--  Script de creación de base de datos
--
--  Uso (desde la raíz del proyecto):
--     mysql -u root -p < sql\schema.sql
--
--  Nota: el usuario/clave de la aplicación se crean aquí. Si cambias la
--  clave, actualiza también backend\config.py (o el .env).
-- =====================================================================

-- ---------------------------------------------------------------------
-- Base de datos
-- ---------------------------------------------------------------------
CREATE DATABASE IF NOT EXISTS vigilancia_cv
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------
-- Usuario de la aplicación
-- ---------------------------------------------------------------------
CREATE USER IF NOT EXISTS 'vigilancia'@'localhost'
    IDENTIFIED BY 'vigilancia123';
CREATE USER IF NOT EXISTS 'vigilancia'@'127.0.0.1'
    IDENTIFIED BY 'vigilancia123';

GRANT ALL PRIVILEGES ON vigilancia_cv.* TO 'vigilancia'@'localhost';
GRANT ALL PRIVILEGES ON vigilancia_cv.* TO 'vigilancia'@'127.0.0.1';
FLUSH PRIVILEGES;

USE vigilancia_cv;

-- ---------------------------------------------------------------------
-- Personas autorizadas
-- ---------------------------------------------------------------------
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

-- ---------------------------------------------------------------------
-- Embeddings faciales + foto de registro (LONGBLOB)
-- 512 float32 = 2048 bytes por vector (ArcFace / InsightFace)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS embeddings (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    persona_id  INT NOT NULL,
    vector      BLOB       NOT NULL,
    foto        LONGBLOB,
    foto_mime   VARCHAR(50) DEFAULT 'image/jpeg',
    FOREIGN KEY (persona_id) REFERENCES personas(id) ON DELETE CASCADE,
    INDEX idx_emb_persona (persona_id)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- Zonas restringidas (polígonos)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS zonas (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    nombre     VARCHAR(100) NOT NULL,
    poligono   TEXT NOT NULL,
    camara_id  VARCHAR(50) DEFAULT 'cam0',
    creado     DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- Eventos / accesos + snapshot del intruso (LONGBLOB)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS eventos (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    timestamp     DATETIME DEFAULT CURRENT_TIMESTAMP,
    persona_id    INT NULL,
    tipo          ENUM('autorizado','no_autorizado') NOT NULL,
    zona_id       INT NULL,
    similitud     FLOAT,
    nota          VARCHAR(255),
    snapshot      LONGBLOB,
    FOREIGN KEY (persona_id) REFERENCES personas(id) ON DELETE SET NULL,
    FOREIGN KEY (zona_id)    REFERENCES zonas(id)    ON DELETE SET NULL,
    INDEX idx_eventos_ts (timestamp DESC),
    INDEX idx_eventos_tipo (tipo)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- Auditoría de registros
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS logs_registro (
    id                 INT AUTO_INCREMENT PRIMARY KEY,
    persona_id         INT NULL,
    ts                 DATETIME DEFAULT CURRENT_TIMESTAMP,
    embeddings_creados INT,
    mensaje            VARCHAR(255),
    FOREIGN KEY (persona_id) REFERENCES personas(id) ON DELETE SET NULL
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- Verificación
-- ---------------------------------------------------------------------
SELECT table_name, table_rows
FROM information_schema.tables
WHERE table_schema = 'vigilancia_cv'
ORDER BY table_name;
