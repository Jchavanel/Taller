"""VeriFactu — Fase 2: generación del XML del registro de facturación y del sobre SOAP.

Construye el mensaje ``RegFactuSistemaFacturacion`` (alta / anulación) conforme a los
esquemas oficiales de la AEAT, que se conservan en
``taller/resources/verifactu_xsd/`` (``SuministroLR.xsd`` + ``SuministroInformacion.xsd``
+ ``RespuestaSuministro.xsd``, versión IDVersion 1.0).

Namespaces (según los XSD):
  * ``RegFactuSistemaFacturacion``, ``Cabecera`` y ``RegistroFactura`` van en el espacio
    de ``SuministroLR.xsd`` (prefijo ``sfLR``).
  * Todo lo demás — ``RegistroAlta`` / ``RegistroAnulacion`` y TODOS sus descendientes,
    más los hijos de ``Cabecera`` — va en el espacio de ``SuministroInformacion.xsd``
    (prefijo ``sf``).

⚠️  Todavía PENDIENTE de validar contra el entorno de preproducción de la AEAT:
   códigos de operación IGIC (``ClaveRegimen``, ``CalificacionOperacion``), tratamiento
   de facturas sin destinatario identificado y de rectificativas. Las claves usadas aquí
   son las de una operación de régimen general sujeta y no exenta.
"""
from __future__ import annotations

import datetime as _dt
import xml.etree.ElementTree as ET
from pathlib import Path

from . import __version__, verifactu

# --- espacios de nombres (de los XSD oficiales) --------------------------------
_NS_SUM = ("https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/"
           "aplicaciones/es/aeat/tike/cont/ws/SuministroInformacion.xsd")
_NS_LR = ("https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/"
          "aplicaciones/es/aeat/tike/cont/ws/SuministroLR.xsd")
_NS_SOAP = "http://schemas.xmlsoap.org/soap/envelope/"

_IDVERSION = "1.0"

_XSD_DIR = Path(__file__).with_name("resources") / "verifactu_xsd"

# Identificación del sistema informático (SIF). Va en cada registro.
_SIF = {
    "NombreSistemaInformatico": verifactu.SOFTWARE_NOMBRE,   # máx. 30
    "IdSistemaInformatico": verifactu.SOFTWARE_ID_SIF,       # máx. 2
    "Version": __version__,                                  # máx. 50
    "NumeroInstalacion": "1",                                # máx. 100
    "TipoUsoPosibleSoloVerifactu": "S",
    "TipoUsoPosibleMultiOT": "N",
    "IndicadorMultiplesOT": "N",
}

ET.register_namespace("sf", _NS_SUM)
ET.register_namespace("sfLR", _NS_LR)
ET.register_namespace("soapenv", _NS_SOAP)


def _e(parent, ns: str, tag: str, texto: str | None = None):
    el = ET.SubElement(parent, f"{{{ns}}}{tag}")
    if texto is not None:
        el.text = str(texto)
    return el


def _fecha(fecha_iso: str) -> str:
    return _dt.date.fromisoformat(str(fecha_iso)[:10]).strftime("%d-%m-%Y")


def _iso(fecha_es: str) -> str:
    """dd-mm-yyyy -> yyyy-mm-dd."""
    return _dt.datetime.strptime(fecha_es, "%d-%m-%Y").date().isoformat()


def _num2(x) -> str:
    return f"{float(x or 0):.2f}"


# ---------------------------------------------------------- bloques reutilizables
def _persona(parent, ns: str, tag: str, nombre: str, nif: str):
    """PersonaFisicaJuridica(ES)Type: NombreRazon + NIF (siempre en _NS_SUM)."""
    p = _e(parent, ns, tag)
    _e(p, _NS_SUM, "NombreRazon", (nombre or "")[:120])
    _e(p, _NS_SUM, "NIF", nif)
    return p


def _id_factura(parent, nif_emisor: str, serie_numero: str, fecha_iso: str):
    idf = _e(parent, _NS_SUM, "IDFactura")
    _e(idf, _NS_SUM, "IDEmisorFactura", nif_emisor)
    _e(idf, _NS_SUM, "NumSerieFactura", serie_numero)
    _e(idf, _NS_SUM, "FechaExpedicionFactura", _fecha(fecha_iso))
    return idf


def _id_factura_anulada(parent, nif_emisor: str, serie_numero: str, fecha_iso: str):
    idf = _e(parent, _NS_SUM, "IDFactura")
    _e(idf, _NS_SUM, "IDEmisorFacturaAnulada", nif_emisor)
    _e(idf, _NS_SUM, "NumSerieFacturaAnulada", serie_numero)
    _e(idf, _NS_SUM, "FechaExpedicionFacturaAnulada", _fecha(fecha_iso))
    return idf


def _sistema_informatico(parent, nombre_razon: str, nif: str):
    si = _e(parent, _NS_SUM, "SistemaInformatico")
    _e(si, _NS_SUM, "NombreRazon", (nombre_razon or "")[:120])
    _e(si, _NS_SUM, "NIF", nif)
    for k, v in _SIF.items():
        _e(si, _NS_SUM, k, v)
    return si


def _encadenamiento(parent, anterior: dict | None):
    enc = _e(parent, _NS_SUM, "Encadenamiento")
    if not anterior:
        _e(enc, _NS_SUM, "PrimerRegistro", "S")
    else:
        ra = _e(enc, _NS_SUM, "RegistroAnterior")
        _e(ra, _NS_SUM, "IDEmisorFactura", anterior["nif_emisor"])
        _e(ra, _NS_SUM, "NumSerieFactura", anterior["serie_numero"])
        _e(ra, _NS_SUM, "FechaExpedicionFactura", _fecha(anterior["fecha_iso"]))
        _e(ra, _NS_SUM, "Huella", anterior["huella"])
    return enc


def _desglose(parent, desglose: list[dict], impuesto_codigo: str = "03"):
    """desglose: [{'tipo': 7.0, 'base': 100.0, 'cuota': 7.0}, …]  (máx. 12 líneas)."""
    dg = _e(parent, _NS_SUM, "Desglose")
    for d in desglose[:12]:
        det = _e(dg, _NS_SUM, "DetalleDesglose")
        _e(det, _NS_SUM, "Impuesto", impuesto_codigo)          # 03 = IGIC
        _e(det, _NS_SUM, "ClaveRegimen", "01")                 # régimen general
        _e(det, _NS_SUM, "CalificacionOperacion", "S1")        # sujeta y no exenta
        _e(det, _NS_SUM, "TipoImpositivo", _num2(d["tipo"]))
        _e(det, _NS_SUM, "BaseImponibleOimporteNoSujeto", _num2(d["base"]))
        _e(det, _NS_SUM, "CuotaRepercutida", _num2(d["cuota"]))
    return dg


# ------------------------------------------------------------- registro de alta
def registro_alta(reg_row, empresa, destinatario, desglose, anterior) -> ET.Element:
    """``reg_row``: fila (o dict) de ``registro_facturacion``. Devuelve ``RegistroAlta``."""
    nif_emisor = reg_row["nif_emisor"]
    ra = ET.Element(f"{{{_NS_SUM}}}RegistroAlta")
    _e(ra, _NS_SUM, "IDVersion", _IDVERSION)
    _id_factura(ra, nif_emisor, reg_row["serie_numero"],
                _iso(reg_row["fecha_expedicion"]))
    _e(ra, _NS_SUM, "NombreRazonEmisor", (empresa["nombre"] or "")[:120])
    _e(ra, _NS_SUM, "TipoFactura", reg_row["tipo_factura"])
    _e(ra, _NS_SUM, "DescripcionOperacion",
       "Reparación y mantenimiento de vehículos")
    if not (destinatario and destinatario.get("nif")):
        _e(ra, _NS_SUM, "FacturaSinIdentifDestinatarioArt61d", "S")
    else:
        dests = _e(ra, _NS_SUM, "Destinatarios")
        _persona(dests, _NS_SUM, "IDDestinatario",
                 destinatario["nombre"], destinatario["nif"])
    _desglose(ra, desglose)
    _e(ra, _NS_SUM, "CuotaTotal", _num2(reg_row["cuota_total"]))
    _e(ra, _NS_SUM, "ImporteTotal", _num2(reg_row["importe_total"]))
    _encadenamiento(ra, anterior)
    _sistema_informatico(ra, empresa["nombre"], nif_emisor)
    _e(ra, _NS_SUM, "FechaHoraHusoGenRegistro", reg_row["timestamp"])
    _e(ra, _NS_SUM, "TipoHuella", "01")                        # 01 = SHA-256
    _e(ra, _NS_SUM, "Huella", reg_row["huella"])
    return ra


# --------------------------------------------------------- registro de anulación
def registro_anulacion(reg_row, empresa, anterior) -> ET.Element:
    nif_emisor = reg_row["nif_emisor"]
    ran = ET.Element(f"{{{_NS_SUM}}}RegistroAnulacion")
    _e(ran, _NS_SUM, "IDVersion", _IDVERSION)
    _id_factura_anulada(ran, nif_emisor, reg_row["serie_numero"],
                        _iso(reg_row["fecha_expedicion"]))
    _encadenamiento(ran, anterior)
    _sistema_informatico(ran, empresa["nombre"], nif_emisor)
    _e(ran, _NS_SUM, "FechaHoraHusoGenRegistro", reg_row["timestamp"])
    _e(ran, _NS_SUM, "TipoHuella", "01")
    _e(ran, _NS_SUM, "Huella", reg_row["huella"])
    return ran


# ------------------------------------------------------------- mensaje completo
def mensaje_regfactu(empresa, registros: list[ET.Element]) -> ET.Element:
    raiz = ET.Element(f"{{{_NS_LR}}}RegFactuSistemaFacturacion")
    cab = _e(raiz, _NS_LR, "Cabecera")
    nif = (empresa["verifactu_nif_productor"] or empresa["nif"] or "").strip().upper()
    _persona(cab, _NS_SUM, "ObligadoEmision", empresa["nombre"], nif)
    for reg in registros:
        rf = _e(raiz, _NS_LR, "RegistroFactura")
        rf.append(reg)
    return raiz


def sobre_soap(cuerpo: ET.Element) -> bytes:
    env = ET.Element(f"{{{_NS_SOAP}}}Envelope")
    _e(env, _NS_SOAP, "Header")
    body = _e(env, _NS_SOAP, "Body")
    body.append(cuerpo)
    return b'<?xml version="1.0" encoding="UTF-8"?>' + ET.tostring(env, encoding="utf-8")


def xml_str(elemento: ET.Element) -> str:
    return ET.tostring(elemento, encoding="unicode")


def bonito(elemento: ET.Element) -> str:
    """XML indentado y legible (para el diálogo de diagnóstico)."""
    copia = ET.fromstring(ET.tostring(elemento, encoding="utf-8"))
    ET.indent(copia, space="  ")
    return ET.tostring(copia, encoding="unicode")


# ------------------------------------------------------------- validación XSD
def validar(mensaje) -> list[str] | None:
    """Valida un ``RegFactuSistemaFacturacion`` (Element o bytes) contra los XSD locales.

    Devuelve ``[]`` si es válido, la lista de errores si no, o ``None`` si la
    biblioteca ``xmlschema`` no está instalada.
    """
    try:
        import xmlschema
    except ImportError:
        return None
    try:
        esquema = xmlschema.XMLSchema(
            str(_XSD_DIR / "SuministroLR.xsd"),
            locations={"http://www.w3.org/2000/09/xmldsig#":
                       str(_XSD_DIR / "xmldsig-core-schema.xsd")},
        )
        if isinstance(mensaje, (bytes, bytearray, str)):
            doc = ET.fromstring(mensaje)
        else:
            doc = ET.fromstring(ET.tostring(mensaje, encoding="utf-8"))
        return [f"{e.reason} (en {e.path})" for e in esquema.iter_errors(doc)]
    except Exception as e:  # noqa: BLE001
        return [f"No se pudo validar contra el XSD: {e}"]
