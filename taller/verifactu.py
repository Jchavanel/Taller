"""VeriFactu — Fase 1: registro de facturación local con huella encadenada.

Reglamento antifraude: RD 1007/2023 + Orden HAC/1177/2024. Modalidad prevista:
**VERI\\*FACTU** (envío a la AEAT), aunque esta fase no envía nada: solo genera y
encadena los registros en local y añade el QR y la leyenda a la factura.

Se activa en *Datos de mi taller → VeriFactu*. Mientras el modo sea ``desactivado``
(por defecto) no se genera ningún registro ni QR: el programa funciona como hasta ahora.

⚠️  La composición exacta de la huella, los tipos de factura y las URL de cotejo están
    fijados en la especificación técnica de la AEAT. Antes de pasar a producción
    (Fases 2 y 3) hay que **validar cada campo contra la documentación vigente y el
    entorno de preproducción de la AEAT**. Las funciones de este módulo están aisladas y
    documentadas para poder ajustarlas.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
from urllib.parse import urlencode

from . import __version__

# Identificación del sistema informático (va en cada registro).
SOFTWARE_NOMBRE = "Taller de Coches"
SOFTWARE_ID = "TALLERCOCHES"          # identificador del sistema informático
SOFTWARE_VERSION = __version__

#   desactivado  → nada
#   local        → registro + huella encadenada + QR, sin enviar (Fase 1; antes 'verifactu')
#   preproduccion→ además, envío al entorno de PRUEBAS de la AEAT (Fase 2)
#   produccion   → envío al entorno REAL de la AEAT (Fase 3)
MODOS = ("desactivado", "local", "preproduccion", "produccion")
_MODOS_ACTIVOS = {"local", "preproduccion", "produccion", "verifactu"}
_MODOS_ENVIO = {"preproduccion", "produccion"}

# URL del servicio de cotejo de la AEAT para el QR (producción).
_URL_COTEJO = "https://www2.agenciatributaria.gob.es/wlpl/TIKE-CONT/ValidarQR"
_URL_COTEJO_PRE = "https://prewww2.aeat.es/wlpl/TIKE-CONT/ValidarQR"

LEYENDA = "VERI*FACTU — Factura verificable en la sede electrónica de la AEAT"


# --------------------------------------------------------------------- utilidades
def _modo(empresa_row) -> str:
    try:
        return empresa_row["verifactu_modo"] or "desactivado"
    except (KeyError, TypeError):
        return "desactivado"


def activo(empresa_row) -> bool:
    return _modo(empresa_row) in _MODOS_ACTIVOS


def envia_a_aeat(empresa_row) -> bool:
    return _modo(empresa_row) in _MODOS_ENVIO


def es_preproduccion(empresa_row) -> bool:
    return _modo(empresa_row) == "preproduccion"


def _dec2(x) -> str:
    """Número con 2 decimales y punto, como exige el registro (p. ej. '437.66')."""
    return f"{float(x or 0):.2f}"


def _fecha_es(fecha_iso: str) -> str:
    d = _dt.date.fromisoformat(str(fecha_iso)[:10])
    return d.strftime("%d-%m-%Y")


def _ahora_iso() -> str:
    """Marca de tiempo ISO 8601 con huso horario, p. ej. 2026-06-01T12:34:56+02:00."""
    return _dt.datetime.now().astimezone().isoformat(timespec="seconds")


def tipo_factura(doc_row) -> str:
    """Código de tipo de factura de la AEAT. De momento todas son F1 (factura completa)."""
    return "F1"


# --------------------------------------------------------------------- la huella
def huella_alta(campos: dict, huella_anterior: str) -> str:
    """SHA-256 (hex, mayúsculas) de la cadena del registro de ALTA.

    Orden de campos según la especificación de la AEAT (Orden HAC/1177/2024, Anexo).
    """
    cadena = "&".join([
        f"IDEmisorFactura={campos['nif_emisor']}",
        f"NumSerieFactura={campos['serie_numero']}",
        f"FechaExpedicionFactura={campos['fecha_expedicion']}",
        f"TipoFactura={campos['tipo_factura']}",
        f"CuotaTotal={campos['cuota_total']}",
        f"ImporteTotal={campos['importe_total']}",
        f"Huella={huella_anterior}",
        f"FechaHoraHusoGenRegistro={campos['timestamp']}",
    ])
    return hashlib.sha256(cadena.encode("utf-8")).hexdigest().upper()


def huella_anulacion(campos: dict, huella_anterior: str) -> str:
    cadena = "&".join([
        f"IDEmisorFacturaAnulada={campos['nif_emisor']}",
        f"NumSerieFacturaAnulada={campos['serie_numero']}",
        f"FechaExpedicionFacturaAnulada={campos['fecha_expedicion']}",
        f"Huella={huella_anterior}",
        f"FechaHoraHusoGenRegistro={campos['timestamp']}",
    ])
    return hashlib.sha256(cadena.encode("utf-8")).hexdigest().upper()


# --------------------------------------------------------------- QR y leyenda
def url_qr(nif_emisor: str, serie_numero: str, fecha_iso: str, importe_total,
          pre: bool = False) -> str:
    base = _URL_COTEJO_PRE if pre else _URL_COTEJO
    params = urlencode({
        "nif": nif_emisor,
        "numserie": serie_numero,
        "fecha": _fecha_es(fecha_iso),
        "importe": _dec2(importe_total),
    })
    return f"{base}?{params}"


# --------------------------------------------------------------- registro de eventos
def registrar_evento(db, tipo: str, detalle: str = "") -> None:
    try:
        db.execute("INSERT INTO evento (fecha, tipo, detalle) VALUES (?, ?, ?)",
                   (_ahora_iso(), tipo, detalle))
        db.commit()
    except Exception:  # noqa: BLE001 - el registro de eventos nunca debe romper la app
        pass


# --------------------------------------------------------------- alta / anulación
def _ultima_huella(db) -> str:
    row = db.query_one("SELECT huella FROM registro_facturacion ORDER BY id DESC LIMIT 1")
    return row["huella"] if row else ""


def _campos_desde_documento(doc_row, nif_emisor: str) -> dict:
    return {
        "nif_emisor": nif_emisor,
        "serie_numero": doc_row["numero"],
        "fecha_expedicion": _fecha_es(doc_row["fecha"]),
        "tipo_factura": tipo_factura(doc_row),
        "cuota_total": _dec2(doc_row["cuota_iva"]),
        "importe_total": _dec2(doc_row["total"]),
        "timestamp": _ahora_iso(),
    }


def registrar_alta(repo, documento_id: int) -> dict | None:
    """Crea el registro de facturación de ALTA de una factura. No-op si VeriFactu no
    está activo o el documento no es una factura."""
    empresa = repo.get_empresa()
    if not activo(empresa):
        return None
    doc = repo.get_documento(documento_id)
    if doc is None or doc["tipo"] != "factura":
        return None
    if repo.db.query_one(
        "SELECT id FROM registro_facturacion WHERE documento_id = ? AND tipo_registro = 'alta'",
        (documento_id,),
    ):
        return None  # ya registrada

    nif = (empresa["verifactu_nif_productor"] or empresa["nif"] or "").strip().upper()
    campos = _campos_desde_documento(doc, nif)
    anterior = _ultima_huella(repo.db)
    huella = huella_alta(campos, anterior)

    datos = dict(campos)
    datos.update({"software_id": SOFTWARE_ID, "software_version": SOFTWARE_VERSION})
    repo.db.execute(
        "INSERT INTO registro_facturacion (documento_id, tipo_registro, nif_emisor, "
        "serie_numero, fecha_expedicion, tipo_factura, cuota_total, importe_total, "
        "huella_anterior, huella, timestamp, software_nombre, software_version, datos_json) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (documento_id, "alta", nif, campos["serie_numero"], campos["fecha_expedicion"],
         campos["tipo_factura"], campos["cuota_total"], campos["importe_total"],
         anterior, huella, campos["timestamp"], SOFTWARE_NOMBRE, SOFTWARE_VERSION,
         json.dumps(datos, ensure_ascii=False)),
    )
    repo.db.commit()
    registrar_evento(repo.db, "registro_alta", f"{campos['serie_numero']}  {huella[:16]}…")
    return {**campos, "huella": huella, "huella_anterior": anterior}


def registrar_anulacion(repo, documento_id: int) -> dict | None:
    empresa = repo.get_empresa()
    if not activo(empresa):
        return None
    doc = repo.get_documento(documento_id)
    if doc is None or doc["tipo"] != "factura":
        return None
    if repo.db.query_one(
        "SELECT id FROM registro_facturacion WHERE documento_id = ? AND tipo_registro = 'anulacion'",
        (documento_id,),
    ):
        return None

    nif = (empresa["verifactu_nif_productor"] or empresa["nif"] or "").strip().upper()
    campos = _campos_desde_documento(doc, nif)
    anterior = _ultima_huella(repo.db)
    huella = huella_anulacion(campos, anterior)
    repo.db.execute(
        "INSERT INTO registro_facturacion (documento_id, tipo_registro, nif_emisor, "
        "serie_numero, fecha_expedicion, tipo_factura, cuota_total, importe_total, "
        "huella_anterior, huella, timestamp, software_nombre, software_version, datos_json) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (documento_id, "anulacion", nif, campos["serie_numero"], campos["fecha_expedicion"],
         campos["tipo_factura"], campos["cuota_total"], campos["importe_total"],
         anterior, huella, campos["timestamp"], SOFTWARE_NOMBRE, SOFTWARE_VERSION, "{}"),
    )
    repo.db.commit()
    registrar_evento(repo.db, "registro_anulacion", f"{campos['serie_numero']}  {huella[:16]}…")
    return {**campos, "huella": huella, "huella_anterior": anterior}


def registro_de_documento(repo, documento_id: int):
    """Registro de ALTA de una factura (para pintar el QR), o None."""
    return repo.db.query_one(
        "SELECT * FROM registro_facturacion WHERE documento_id = ? AND tipo_registro = 'alta'",
        (documento_id,),
    )


# --------------------------------------------------------------- integridad
def verificar_cadena(db) -> list[str]:
    """Recalcula toda la cadena de huellas. Devuelve la lista de problemas (vacía = OK)."""
    problemas: list[str] = []
    anterior = ""
    filas = db.query("SELECT * FROM registro_facturacion ORDER BY id")
    for r in filas:
        campos = {
            "nif_emisor": r["nif_emisor"], "serie_numero": r["serie_numero"],
            "fecha_expedicion": r["fecha_expedicion"], "tipo_factura": r["tipo_factura"],
            "cuota_total": r["cuota_total"], "importe_total": r["importe_total"],
            "timestamp": r["timestamp"],
        }
        calc = (huella_alta if r["tipo_registro"] == "alta" else huella_anulacion)(
            campos, r["huella_anterior"])
        if r["huella_anterior"] != anterior:
            problemas.append(
                f"Registro {r['id']} ({r['serie_numero']}): la huella anterior no encadena.")
        if calc != r["huella"]:
            problemas.append(
                f"Registro {r['id']} ({r['serie_numero']}): la huella no coincide "
                "(el registro pudo alterarse).")
        anterior = r["huella"]
    return problemas
