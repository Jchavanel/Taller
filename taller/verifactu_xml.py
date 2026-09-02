"""VeriFactu — Fase 2: generación del XML del registro de facturación y del sobre SOAP.

Construye el mensaje ``RegFactuSistemaFacturacion`` (alta / anulación) según la Orden
HAC/1177/2024 y los esquemas de la AEAT (SuministroLR / SuministroInformacion).

⚠️  VERIFICAR CONTRA LA DOCUMENTACIÓN OFICIAL DE LA AEAT antes de usar en real:
   - URIs de espacio de nombres (``_NS_*``).
   - Orden y obligatoriedad exacta de cada elemento en los XSD.
   - Códigos: TipoFactura, Impuesto (IGIC=03), ClaveRegimen, CalificacionOperacion.
   - Endpoints del servicio web (en ``verifactu_envio.py``).
Todo está aislado aquí para poder ajustarlo sin tocar el resto del programa.
"""
from __future__ import annotations

import datetime as _dt
import xml.etree.ElementTree as ET

from . import __version__, verifactu

# --- espacios de nombres (VERIFICAR) --------------------------------------------
_BASE = ("https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/"
         "aplicaciones/es/aeat/tike/cont/ws/")
_NS_SUM = _BASE + "SuministroInformacion.xsd"
_NS_LR = _BASE + "SuministroLR.xsd"
_NS_SOAP = "http://schemas.xmlsoap.org/soap/envelope/"

_IDVERSION = "1.0"

# Identificación del sistema informático (SIF). VERIFICAR longitudes/valores.
_SIF = {
    "NombreSistemaInformatico": verifactu.SOFTWARE_NOMBRE,
    "IdSistemaInformatico": verifactu.SOFTWARE_ID,      # 2 caracteres según algunos docs
    "Version": __version__,
    "NumeroInstalacion": "1",
    "TipoUsoPosibleSoloVerifactu": "S",
    "TipoUsoPosibleMultiOT": "N",
    "IndicadorMultiplesOT": "N",
}

ET.register_namespace("sum", _NS_SUM)
ET.register_namespace("sum1", _NS_LR)
ET.register_namespace("soapenv", _NS_SOAP)


def _e(parent, ns: str, tag: str, texto: str | None = None):
    el = ET.SubElement(parent, f"{{{ns}}}{tag}")
    if texto is not None:
        el.text = str(texto)
    return el


def _fecha(fecha_iso: str) -> str:
    return _dt.date.fromisoformat(str(fecha_iso)[:10]).strftime("%d-%m-%Y")


# ------------------------------------------------------------- ID de factura
def _id_factura(parent, nif_emisor: str, serie_numero: str, fecha_iso: str, ns=_NS_LR):
    idf = _e(parent, ns, "IDFactura")
    _e(idf, ns, "IDEmisorFactura", nif_emisor)
    _e(idf, ns, "NumSerieFactura", serie_numero)
    _e(idf, ns, "FechaExpedicionFactura", _fecha(fecha_iso))
    return idf


def _sistema_informatico(parent, nombre_razon: str, nif: str):
    si = _e(parent, _NS_LR, "SistemaInformatico")
    _e(si, _NS_SUM, "NombreRazon", nombre_razon)
    _e(si, _NS_SUM, "NIF", nif)
    for k, v in _SIF.items():
        _e(si, _NS_LR, k, v)
    return si


def _desglose(parent, desglose: list[dict], impuesto_codigo: str):
    """desglose: [{'tipo': 7.0, 'base': 100.0, 'cuota': 7.0}]"""
    dg = _e(parent, _NS_LR, "Desglose")
    for d in desglose:
        det = _e(dg, _NS_LR, "DetalleDesglose")
        _e(det, _NS_LR, "Impuesto", impuesto_codigo)          # 03 = IGIC
        _e(det, _NS_LR, "ClaveRegimen", "01")                 # régimen general
        _e(det, _NS_LR, "CalificacionOperacion", "S1")        # sujeta y no exenta
        _e(det, _NS_LR, "TipoImpositivo", f"{float(d['tipo']):.2f}")
        _e(det, _NS_LR, "BaseImponibleOimporteNoSujeto", f"{float(d['base']):.2f}")
        _e(det, _NS_LR, "CuotaRepercutida", f"{float(d['cuota']):.2f}")
    return dg


def _encadenamiento(parent, anterior: dict | None):
    enc = _e(parent, _NS_LR, "Encadenamiento")
    if not anterior:
        _e(enc, _NS_LR, "PrimerRegistro", "S")
    else:
        ra = _e(enc, _NS_LR, "RegistroAnterior")
        _e(ra, _NS_LR, "IDEmisorFactura", anterior["nif_emisor"])
        _e(ra, _NS_LR, "NumSerieFactura", anterior["serie_numero"])
        _e(ra, _NS_LR, "FechaExpedicionFactura", _fecha(anterior["fecha_iso"]))
        _e(ra, _NS_LR, "Huella", anterior["huella"])
    return enc


# ------------------------------------------------------------- registro de alta
def registro_alta(reg_row, empresa, destinatario, desglose, anterior) -> ET.Element:
    """``reg_row``: fila de registro_facturacion. Devuelve el elemento RegistroAlta."""
    nif_emisor = reg_row["nif_emisor"]
    ra = ET.Element(f"{{{_NS_LR}}}RegistroAlta")
    _e(ra, _NS_LR, "IDVersion", _IDVERSION)
    _id_factura(ra, nif_emisor, reg_row["serie_numero"], _iso(reg_row["fecha_expedicion"]))
    _e(ra, _NS_LR, "NombreRazonEmisor", empresa["nombre"])
    _e(ra, _NS_LR, "TipoFactura", reg_row["tipo_factura"])
    _e(ra, _NS_LR, "DescripcionOperacion",
       "Reparación y mantenimiento de vehículos")
    if destinatario and destinatario.get("nif"):
        dests = _e(ra, _NS_LR, "Destinatarios")
        idd = _e(dests, _NS_LR, "IDDestinatario")
        _e(idd, _NS_SUM, "NombreRazon", destinatario["nombre"])
        _e(idd, _NS_SUM, "NIF", destinatario["nif"])
    else:
        _e(ra, _NS_LR, "FacturaSinIdentifDestinatarioArt61d", "S")
    _desglose(ra, desglose, "03")
    _e(ra, _NS_LR, "CuotaTotal", reg_row["cuota_total"])
    _e(ra, _NS_LR, "ImporteTotal", reg_row["importe_total"])
    _encadenamiento(ra, anterior)
    _sistema_informatico(ra, empresa["nombre"], nif_emisor)
    _e(ra, _NS_LR, "FechaHoraHusoGenRegistro", reg_row["timestamp"])
    _e(ra, _NS_LR, "TipoHuella", "01")                        # 01 = SHA-256
    _e(ra, _NS_LR, "Huella", reg_row["huella"])
    return ra


def registro_anulacion(reg_row, empresa, anterior) -> ET.Element:
    nif_emisor = reg_row["nif_emisor"]
    ran = ET.Element(f"{{{_NS_LR}}}RegistroAnulacion")
    _e(ran, _NS_LR, "IDVersion", _IDVERSION)
    _id_factura(ran, nif_emisor, reg_row["serie_numero"], _iso(reg_row["fecha_expedicion"]))
    _sistema_informatico(ran, empresa["nombre"], nif_emisor)
    _e(ran, _NS_LR, "FechaHoraHusoGenRegistro", reg_row["timestamp"])
    _e(ran, _NS_LR, "TipoHuella", "01")
    _e(ran, _NS_LR, "Huella", reg_row["huella"])
    _encadenamiento_anul(ran, anterior)
    return ran


def _encadenamiento_anul(parent, anterior):
    enc = _e(parent, _NS_LR, "Encadenamiento")
    if not anterior:
        _e(enc, _NS_LR, "PrimerRegistro", "S")
    else:
        ra = _e(enc, _NS_LR, "RegistroAnterior")
        _e(ra, _NS_LR, "IDEmisorFactura", anterior["nif_emisor"])
        _e(ra, _NS_LR, "NumSerieFactura", anterior["serie_numero"])
        _e(ra, _NS_LR, "FechaExpedicionFactura", _fecha(anterior["fecha_iso"]))
        _e(ra, _NS_LR, "Huella", anterior["huella"])


def _iso(fecha_es: str) -> str:
    """dd-mm-yyyy -> yyyy-mm-dd (para volver a formatearla)."""
    d = _dt.datetime.strptime(fecha_es, "%d-%m-%Y").date()
    return d.isoformat()


# ------------------------------------------------------------- mensaje completo
def mensaje_regfactu(empresa, registros: list[ET.Element]) -> ET.Element:
    raiz = ET.Element(f"{{{_NS_LR}}}RegFactuSistemaFacturacion")
    cab = _e(raiz, _NS_LR, "Cabecera")
    obl = _e(cab, _NS_SUM, "ObligadoEmision")
    _e(obl, _NS_SUM, "NombreRazon", empresa["nombre"])
    _e(obl, _NS_SUM, "NIF", (empresa["verifactu_nif_productor"] or empresa["nif"]))
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
