"""VeriFactu — Fase 2: envío de los registros de facturación al servicio web de la AEAT.

Conexión HTTPS con **certificado de cliente** (.p12/.pfx del emisor). En modalidad
VERI\\*FACTU los registros no van firmados con XAdES; basta el certificado para la
conexión TLS. Los registros que no se pueden enviar (sin conexión, sin certificado o
rechazados temporalmente) quedan **en cola** y se reintentan.

⚠️  VERIFICAR CONTRA LA AEAT: endpoints, estructura de la respuesta y códigos de error.
"""
from __future__ import annotations

import datetime as _dt
import os
import ssl
import tempfile
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

from . import email_envio as _mail
from . import verifactu
from .errores import log

# Endpoints del servicio (VERIFICAR).
ENDPOINT = {
    "preproduccion": ("https://prewww1.aeat.es/wlpl/TIKE-CONT/ws/"
                      "SistemaFacturacion/VerifactuSOAP"),
    "produccion": ("https://www1.agenciatributaria.gob.es/wlpl/TIKE-CONT/ws/"
                   "SistemaFacturacion/VerifactuSOAP"),
}
_TIMEOUT = 30
_MAX_LOTE = 1000
_KEYRING = "taller-coches-verifactu"


# ------------------------------------------------------- contraseña del certificado
def guardar_password_cert(password: str) -> str:
    """Devuelve lo que hay que guardar en la BD (llavero si se puede, si no ofuscado)."""
    try:
        import keyring
        keyring.set_password(_KEYRING, "cert", password or "")
        return "keyring:"
    except Exception:  # noqa: BLE001
        return _mail.ofuscar(password)


def _leer_pw(valor_bd: str) -> str:
    if valor_bd == "keyring:":
        try:
            import keyring
            return keyring.get_password(_KEYRING, "cert") or ""
        except Exception:  # noqa: BLE001
            return ""
    return _mail.desofuscar(valor_bd or "")


# ------------------------------------------------------------- certificado / TLS
def _pem_desde_p12(ruta: Path, password: str) -> str:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.serialization import pkcs12

    key, cert, extras = pkcs12.load_key_and_certificates(
        Path(ruta).read_bytes(), (password or "").encode() or None)
    if key is None or cert is None:
        raise ValueError("El fichero no contiene clave privada y certificado.")
    partes = [
        key.private_bytes(serialization.Encoding.PEM,
                          serialization.PrivateFormat.TraditionalOpenSSL,
                          serialization.NoEncryption()).decode(),
        cert.public_bytes(serialization.Encoding.PEM).decode(),
    ]
    for c in extras or []:
        partes.append(c.public_bytes(serialization.Encoding.PEM).decode())
    return "".join(partes)


def contexto_ssl(cert_path: str, cert_password: str) -> ssl.SSLContext:
    pem = _pem_desde_p12(Path(cert_path), cert_password)
    ctx = ssl.create_default_context()
    tmp = tempfile.NamedTemporaryFile("w", suffix=".pem", delete=False)
    try:
        tmp.write(pem)
        tmp.close()
        os.chmod(tmp.name, 0o600)
        ctx.load_cert_chain(tmp.name)
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
    return ctx


def _config(empresa) -> tuple[str, ssl.SSLContext]:
    modo = empresa["verifactu_modo"]
    if modo not in ENDPOINT:
        raise ValueError("VeriFactu no está en modo de envío (preproducción/producción).")
    ruta = (empresa["verifactu_cert_path"] or "").strip()
    if not ruta or not Path(ruta).is_file():
        raise ValueError("Falta el certificado (.p12/.pfx) en Datos de mi taller → VeriFactu.")
    ctx = contexto_ssl(ruta, _leer_pw(empresa["verifactu_cert_password"]))
    return ENDPOINT[modo], ctx


def probar_conexion(empresa) -> None:
    """Comprueba que el certificado carga y que se llega al servicio. Lanza excepción
    con un mensaje claro si algo falla."""
    endpoint, ctx = _config(empresa)
    req = urllib.request.Request(endpoint, data=b"", method="POST",
                                 headers={"Content-Type": "text/xml; charset=utf-8"})
    try:
        urllib.request.urlopen(req, timeout=_TIMEOUT, context=ctx)
    except urllib.error.HTTPError as e:
        # una respuesta HTTP (aunque sea 500 por cuerpo vacío) significa que la conexión
        # y el certificado son válidos
        if e.code in (400, 500):
            return
        raise RuntimeError(f"El servicio respondió {e.code}: {e.reason}") from e
    except (urllib.error.URLError, ssl.SSLError, OSError) as e:
        raise RuntimeError(f"No se pudo conectar con la AEAT: {e}") from e


# ------------------------------------------------------------- envío
def _sin_ns(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _buscar(elem, nombre: str):
    for e in elem.iter():
        if _sin_ns(e.tag) == nombre:
            return e
    return None


def parsear_respuesta(xml_bytes: bytes) -> dict:
    raiz = ET.fromstring(xml_bytes)
    estado = _buscar(raiz, "EstadoEnvio")
    csv = _buscar(raiz, "CSV")
    lineas = []
    for ln in raiz.iter():
        if _sin_ns(ln.tag) != "RespuestaLinea":
            continue
        num = _buscar(ln, "NumSerieFactura")
        er = _buscar(ln, "EstadoRegistro")
        cod = _buscar(ln, "CodigoErrorRegistro")
        des = _buscar(ln, "DescripcionErrorRegistro")
        lineas.append({
            "numero": num.text if num is not None else "",
            "estado": er.text if er is not None else "",
            "codigo": cod.text if cod is not None else "",
            "descripcion": des.text if des is not None else "",
        })
    return {
        "estado_envio": estado.text if estado is not None else "",
        "csv": csv.text if csv is not None else "",
        "lineas": lineas,
    }


def _anterior_para(repo, reg_row) -> dict | None:
    if not reg_row["huella_anterior"]:
        return None
    prev = repo.db.query_one(
        "SELECT * FROM registro_facturacion WHERE huella = ?", (reg_row["huella_anterior"],))
    if prev is None:
        return None
    from .verifactu_xml import _iso
    return {"nif_emisor": prev["nif_emisor"], "serie_numero": prev["serie_numero"],
            "fecha_iso": _iso(prev["fecha_expedicion"]), "huella": prev["huella"]}


def _elemento_registro(repo, reg_row, empresa):
    from . import verifactu_xml as vx
    anterior = _anterior_para(repo, reg_row)
    if reg_row["tipo_registro"] == "anulacion":
        return vx.registro_anulacion(reg_row, empresa, anterior)
    doc = repo.get_documento(reg_row["documento_id"])
    cli = repo.get_cliente(doc["cliente_id"]) if doc and doc["cliente_id"] else None
    dest = {"nombre": cli["nombre"], "nif": cli["nif"]} if cli and cli["nif"] else None
    lineas = repo.get_lineas(reg_row["documento_id"])
    from . import domain
    calc = [domain.LineaCalc(cantidad=l["cantidad"], precio=l["precio"],
                             descuento_pct=l["descuento_pct"], iva_pct=l["iva_pct"])
            for l in lineas]
    tot = domain.calcular_totales(calc, doc["descuento_pct"])
    desglose = [{"tipo": r, "base": b, "cuota": c}
                for r, (b, c) in sorted(tot.desglose.items())]
    return vx.registro_alta(reg_row, empresa, dest, desglose, anterior)


def enviar_pendientes(repo, limite: int = _MAX_LOTE) -> dict:
    """Envía a la AEAT los registros en cola. Devuelve un resumen."""
    empresa = repo.get_empresa()
    if not verifactu.envia_a_aeat(empresa):
        return {"enviados": 0, "error": "VeriFactu no está en modo de envío."}
    try:
        endpoint, ctx = _config(empresa)
    except ValueError as e:
        return {"enviados": 0, "error": str(e)}

    filas = repo.db.query(
        "SELECT * FROM registro_facturacion WHERE estado_envio IN "
        "('pendiente', 'error_conexion', 'rechazado') ORDER BY id LIMIT ?", (limite,))
    if not filas:
        return {"enviados": 0, "pendientes": 0}

    from . import verifactu_xml as vx
    registros_xml, ids = [], []
    for r in filas:
        try:
            registros_xml.append(_elemento_registro(repo, r, empresa))
            ids.append(r["id"])
        except Exception as e:  # noqa: BLE001
            log().exception("VeriFactu: no se pudo construir el XML del registro %s", r["id"])
            repo.db.execute(
                "UPDATE registro_facturacion SET estado_envio = 'error', respuesta = ? "
                "WHERE id = ?", (f"XML: {e}", r["id"]))
    repo.db.commit()
    if not registros_xml:
        return {"enviados": 0, "error": "No se pudo preparar ningún registro."}

    sobre = vx.sobre_soap(vx.mensaje_regfactu(empresa, registros_xml))
    req = urllib.request.Request(
        endpoint, data=sobre, method="POST",
        headers={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": ""})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT, context=ctx) as resp:
            cuerpo = resp.read()
    except urllib.error.HTTPError as e:
        cuerpo = e.read()
        try:
            datos = parsear_respuesta(cuerpo)
        except ET.ParseError:
            datos = None
        if not datos or not datos.get("lineas"):
            for i in ids:
                repo.db.execute(
                    "UPDATE registro_facturacion SET estado_envio = 'error_conexion', "
                    "intentos = intentos + 1, respuesta = ? WHERE id = ?",
                    (f"HTTP {e.code}", i))
            repo.db.commit()
            return {"enviados": 0, "error": f"La AEAT devolvió HTTP {e.code}."}
    except (urllib.error.URLError, ssl.SSLError, OSError) as e:
        for i in ids:
            repo.db.execute(
                "UPDATE registro_facturacion SET estado_envio = 'error_conexion', "
                "intentos = intentos + 1, respuesta = ? WHERE id = ?", (str(e)[:300], i))
        repo.db.commit()
        return {"enviados": 0, "error": f"Sin conexión con la AEAT: {e}"}

    datos = parsear_respuesta(cuerpo)
    ahora = _dt.datetime.now().astimezone().isoformat(timespec="seconds")
    ok = con_errores = rechazados = 0
    por_numero = {ln["numero"]: ln for ln in datos["lineas"]}
    for i in ids:
        r = repo.db.query_one("SELECT serie_numero FROM registro_facturacion WHERE id = ?", (i,))
        ln = por_numero.get(r["serie_numero"], {})
        er = (ln.get("estado") or "").lower()
        if er.startswith("correct") or er == "aceptado":
            estado, ok = "enviado", ok + 1
        elif "error" in er or er == "aceptadoconerrores":
            estado, con_errores = "aceptado_con_errores", con_errores + 1
        elif "duplicad" in er:
            estado, ok = "enviado", ok + 1
        else:
            estado, rechazados = "rechazado", rechazados + 1
        repo.db.execute(
            "UPDATE registro_facturacion SET estado_envio = ?, csv = ?, enviado_en = ?, "
            "intentos = intentos + 1, respuesta = ? WHERE id = ?",
            (estado, datos.get("csv", ""), ahora,
             f"{ln.get('estado', '')} {ln.get('codigo', '')} {ln.get('descripcion', '')}".strip(),
             i))
    repo.db.commit()
    verifactu.registrar_evento(
        repo.db, "envio_aeat",
        f"{datos.get('estado_envio', '')} · CSV {datos.get('csv', '')[:20]} · "
        f"ok {ok}, con errores {con_errores}, rechazados {rechazados}")
    return {"enviados": ok, "con_errores": con_errores, "rechazados": rechazados,
            "estado_envio": datos.get("estado_envio", ""), "csv": datos.get("csv", "")}


def enviar_uno(repo, registro_id: int) -> dict:
    """Intenta enviar de inmediato un registro recién creado (tras emitir/anular)."""
    empresa = repo.get_empresa()
    if not verifactu.envia_a_aeat(empresa):
        return {}
    return enviar_pendientes(repo)
