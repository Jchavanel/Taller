"""Conexión y esquema de la base de datos SQLite (local, un solo fichero)."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from .paths import db_path

SCHEMA_VERSION = 12

# Columnas añadidas después de la v1. Se aplican con ALTER TABLE sobre bases de datos
# antiguas (los CREATE TABLE IF NOT EXISTS no modifican tablas ya existentes).
_MIGRACIONES = {
    "empresa": [
        ("impuesto_nombre", "TEXT NOT NULL DEFAULT 'IVA'"),
        ("anticipo_pct", "REAL NOT NULL DEFAULT 0"),
        ("cond_presupuesto", "TEXT NOT NULL DEFAULT ''"),
        ("cond_orden", "TEXT NOT NULL DEFAULT ''"),
        ("cond_albaran", "TEXT NOT NULL DEFAULT ''"),
        ("cond_factura", "TEXT NOT NULL DEFAULT ''"),
        ("smtp_host", "TEXT NOT NULL DEFAULT ''"),
        ("smtp_port", "INTEGER NOT NULL DEFAULT 587"),
        ("smtp_seguridad", "TEXT NOT NULL DEFAULT 'starttls'"),
        ("smtp_usuario", "TEXT NOT NULL DEFAULT ''"),
        ("smtp_password", "TEXT NOT NULL DEFAULT ''"),
        ("smtp_remitente", "TEXT NOT NULL DEFAULT ''"),
        ("email_asunto", "TEXT NOT NULL DEFAULT ''"),
        ("email_cuerpo", "TEXT NOT NULL DEFAULT ''"),
        ("resenas_url", "TEXT NOT NULL DEFAULT ''"),
        ("whatsapp_plantilla", "TEXT NOT NULL DEFAULT ''"),
        ("whatsapp_tras_factura", "INTEGER NOT NULL DEFAULT 1"),
        ("whatsapp_prefijo", "TEXT NOT NULL DEFAULT '34'"),
        ("email_gestoria", "TEXT NOT NULL DEFAULT ''"),
        ("whatsapp_plantilla_doc", "TEXT NOT NULL DEFAULT ''"),
        ("verifactu_modo", "TEXT NOT NULL DEFAULT 'desactivado'"),
        ("verifactu_nif_productor", "TEXT NOT NULL DEFAULT ''"),
        ("verifactu_cert_path", "TEXT NOT NULL DEFAULT ''"),
        ("verifactu_cert_password", "TEXT NOT NULL DEFAULT ''"),
    ],
    "registro_facturacion": [
        ("csv", "TEXT NOT NULL DEFAULT ''"),
        ("respuesta", "TEXT NOT NULL DEFAULT ''"),
        ("enviado_en", "TEXT"),
        ("intentos", "INTEGER NOT NULL DEFAULT 0"),
    ],
    "documento": [
        ("fecha_entrada", "TEXT"),
        ("entrega_prevista", "TEXT"),
        ("validez_dias", "INTEGER"),
        ("factura_tipo", "TEXT NOT NULL DEFAULT 'completa'"),
        ("anticipo_pct", "REAL"),
    ],
    "articulo": [
        ("canon_reciclaje", "REAL NOT NULL DEFAULT 0"),
        ("canon_descripcion", "TEXT NOT NULL DEFAULT ''"),
    ],
    "linea": [
        ("es_canon", "INTEGER NOT NULL DEFAULT 0"),
    ],
}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    clave TEXT PRIMARY KEY,
    valor TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS empresa (
    id           INTEGER PRIMARY KEY CHECK (id = 1),
    nombre       TEXT NOT NULL DEFAULT '',
    nif          TEXT NOT NULL DEFAULT '',
    direccion    TEXT NOT NULL DEFAULT '',
    cp           TEXT NOT NULL DEFAULT '',
    poblacion    TEXT NOT NULL DEFAULT '',
    provincia    TEXT NOT NULL DEFAULT '',
    telefono     TEXT NOT NULL DEFAULT '',
    email        TEXT NOT NULL DEFAULT '',
    iban         TEXT NOT NULL DEFAULT '',
    iva_defecto  REAL NOT NULL DEFAULT 21.0,
    logo_path    TEXT NOT NULL DEFAULT '',
    pie_documento TEXT NOT NULL DEFAULT '',
    impuesto_nombre  TEXT NOT NULL DEFAULT 'IVA',
    anticipo_pct     REAL NOT NULL DEFAULT 0,
    cond_presupuesto TEXT NOT NULL DEFAULT '',
    cond_orden       TEXT NOT NULL DEFAULT '',
    cond_albaran     TEXT NOT NULL DEFAULT '',
    cond_factura     TEXT NOT NULL DEFAULT '',
    smtp_host        TEXT NOT NULL DEFAULT '',
    smtp_port        INTEGER NOT NULL DEFAULT 587,
    smtp_seguridad   TEXT NOT NULL DEFAULT 'starttls',
    smtp_usuario     TEXT NOT NULL DEFAULT '',
    smtp_password    TEXT NOT NULL DEFAULT '',
    smtp_remitente   TEXT NOT NULL DEFAULT '',
    email_asunto     TEXT NOT NULL DEFAULT '',
    email_cuerpo     TEXT NOT NULL DEFAULT '',
    resenas_url          TEXT NOT NULL DEFAULT '',
    whatsapp_plantilla   TEXT NOT NULL DEFAULT '',
    whatsapp_tras_factura INTEGER NOT NULL DEFAULT 1,
    whatsapp_prefijo     TEXT NOT NULL DEFAULT '34',
    email_gestoria       TEXT NOT NULL DEFAULT '',
    whatsapp_plantilla_doc TEXT NOT NULL DEFAULT '',
    verifactu_modo         TEXT NOT NULL DEFAULT 'desactivado',
    verifactu_nif_productor TEXT NOT NULL DEFAULT '',
    verifactu_cert_path    TEXT NOT NULL DEFAULT '',
    verifactu_cert_password TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS cliente (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre     TEXT NOT NULL,
    nif        TEXT NOT NULL DEFAULT '',
    direccion  TEXT NOT NULL DEFAULT '',
    cp         TEXT NOT NULL DEFAULT '',
    poblacion  TEXT NOT NULL DEFAULT '',
    provincia  TEXT NOT NULL DEFAULT '',
    telefono   TEXT NOT NULL DEFAULT '',
    email      TEXT NOT NULL DEFAULT '',
    notas      TEXT NOT NULL DEFAULT '',
    creado     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS vehiculo (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente_id  INTEGER NOT NULL REFERENCES cliente(id) ON DELETE CASCADE,
    matricula   TEXT NOT NULL DEFAULT '',
    marca       TEXT NOT NULL DEFAULT '',
    modelo      TEXT NOT NULL DEFAULT '',
    bastidor    TEXT NOT NULL DEFAULT '',
    anio        INTEGER,
    color       TEXT NOT NULL DEFAULT '',
    combustible TEXT NOT NULL DEFAULT '',
    kms         INTEGER,
    notas       TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS articulo (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo      TEXT NOT NULL DEFAULT '',
    descripcion TEXT NOT NULL,
    tipo        TEXT NOT NULL DEFAULT 'material',
    precio      REAL NOT NULL DEFAULT 0,
    iva_pct     REAL NOT NULL DEFAULT 21.0,
    activo      INTEGER NOT NULL DEFAULT 1,
    canon_reciclaje   REAL NOT NULL DEFAULT 0,
    canon_descripcion TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS documento (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo          TEXT NOT NULL,
    numero        TEXT NOT NULL,
    anio          INTEGER NOT NULL,
    secuencia     INTEGER NOT NULL,
    fecha         TEXT NOT NULL,
    cliente_id    INTEGER REFERENCES cliente(id),
    vehiculo_id   INTEGER REFERENCES vehiculo(id),
    kms           INTEGER,
    estado        TEXT NOT NULL DEFAULT 'abierto',
    descuento_pct REAL NOT NULL DEFAULT 0,
    observaciones TEXT NOT NULL DEFAULT '',
    forma_pago    TEXT NOT NULL DEFAULT '',
    origen_id     INTEGER REFERENCES documento(id),
    fecha_entrada    TEXT,
    entrega_prevista TEXT,
    validez_dias     INTEGER,
    factura_tipo     TEXT NOT NULL DEFAULT 'completa',
    anticipo_pct     REAL,
    base          REAL NOT NULL DEFAULT 0,
    cuota_iva     REAL NOT NULL DEFAULT 0,
    total         REAL NOT NULL DEFAULT 0,
    creado        TEXT NOT NULL,
    UNIQUE (tipo, anio, secuencia)
);

CREATE TABLE IF NOT EXISTS linea (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    documento_id  INTEGER NOT NULL REFERENCES documento(id) ON DELETE CASCADE,
    orden         INTEGER NOT NULL DEFAULT 0,
    tipo          TEXT NOT NULL DEFAULT 'material',
    codigo        TEXT NOT NULL DEFAULT '',
    descripcion   TEXT NOT NULL DEFAULT '',
    cantidad      REAL NOT NULL DEFAULT 1,
    precio        REAL NOT NULL DEFAULT 0,
    descuento_pct REAL NOT NULL DEFAULT 0,
    iva_pct       REAL NOT NULL DEFAULT 21.0,
    es_canon      INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS intervencion (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    vehiculo_id   INTEGER NOT NULL REFERENCES vehiculo(id) ON DELETE CASCADE,
    fecha         TEXT NOT NULL,
    kms           INTEGER,
    tipo          TEXT NOT NULL DEFAULT 'reparacion',
    titulo        TEXT NOT NULL DEFAULT '',
    detalle       TEXT NOT NULL DEFAULT '',
    documento_id  INTEGER REFERENCES documento(id) ON DELETE SET NULL,
    prox_fecha    TEXT,
    prox_kms      INTEGER,
    creado        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS numeracion (
    tipo      TEXT NOT NULL,
    anio      INTEGER NOT NULL,
    siguiente INTEGER NOT NULL,
    PRIMARY KEY (tipo, anio)
);

-- VeriFactu: registro de facturación con huella encadenada (RD 1007/2023).
CREATE TABLE IF NOT EXISTS registro_facturacion (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    documento_id     INTEGER REFERENCES documento(id),
    tipo_registro    TEXT NOT NULL,              -- 'alta' | 'anulacion'
    nif_emisor       TEXT NOT NULL,
    serie_numero     TEXT NOT NULL,
    fecha_expedicion TEXT NOT NULL,              -- dd-mm-yyyy
    tipo_factura     TEXT NOT NULL,
    cuota_total      TEXT NOT NULL,
    importe_total    TEXT NOT NULL,
    huella_anterior  TEXT NOT NULL DEFAULT '',
    huella           TEXT NOT NULL,
    timestamp        TEXT NOT NULL,              -- ISO 8601 con huso horario
    software_nombre  TEXT NOT NULL DEFAULT '',
    software_version TEXT NOT NULL DEFAULT '',
    estado_envio     TEXT NOT NULL DEFAULT 'pendiente',
    datos_json       TEXT NOT NULL DEFAULT '{}',
    csv              TEXT NOT NULL DEFAULT '',
    respuesta        TEXT NOT NULL DEFAULT '',
    enviado_en       TEXT,
    intentos         INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_registro_doc ON registro_facturacion(documento_id);

-- VeriFactu: registro de eventos del sistema informático.
CREATE TABLE IF NOT EXISTS evento (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha   TEXT NOT NULL,
    tipo    TEXT NOT NULL,
    detalle TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_vehiculo_cliente ON vehiculo(cliente_id);
CREATE INDEX IF NOT EXISTS idx_intervencion_vehiculo ON intervencion(vehiculo_id, fecha);
CREATE INDEX IF NOT EXISTS idx_documento_tipo ON documento(tipo, anio, secuencia);
CREATE INDEX IF NOT EXISTS idx_documento_cliente ON documento(cliente_id);
CREATE INDEX IF NOT EXISTS idx_linea_documento ON linea(documento_id);
"""


class Database:
    """Envoltura ligera sobre sqlite3 con clave foránea activada."""

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path is not None else db_path()
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.execute("PRAGMA busy_timeout = 5000")
        self._init_schema()

    def _init_schema(self) -> None:
        self.conn.executescript(_SCHEMA)
        self._migrate()
        # El esquema usa CREATE TABLE IF NOT EXISTS, así que las tablas nuevas de cada
        # versión se crean también al abrir una base de datos antigua. Aquí solo se
        # deja constancia de la versión vigente.
        self.conn.execute(
            "INSERT INTO meta (clave, valor) VALUES ('schema_version', ?) "
            "ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor",
            (str(SCHEMA_VERSION),),
        )
        self.conn.execute("INSERT OR IGNORE INTO empresa (id) VALUES (1)")
        self.conn.commit()

    def _migrate(self) -> None:
        for tabla, columnas in _MIGRACIONES.items():
            existentes = {
                row["name"] for row in self.conn.execute(f"PRAGMA table_info({tabla})")
            }
            for nombre, ddl in columnas:
                if nombre not in existentes:
                    self.conn.execute(
                        f"ALTER TABLE {tabla} ADD COLUMN {nombre} {ddl}"  # noqa: S608
                    )
        self.conn.commit()

    # -- utilidades -------------------------------------------------------
    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        return self.conn.execute(sql, params)

    def query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        return self.conn.execute(sql, params).fetchall()

    def query_one(self, sql: str, params: tuple = ()):
        return self.conn.execute(sql, params).fetchone()

    def commit(self) -> None:
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()
