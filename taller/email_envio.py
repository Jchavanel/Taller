"""Envío de documentos por correo electrónico mediante SMTP.

La configuración (servidor, puerto, usuario, contraseña, plantillas) se guarda en la
tabla ``empresa``. La contraseña se guarda ofuscada en base64: NO es cifrado real, solo
evita que aparezca en claro a simple vista. La base de datos es local y de un solo
usuario, igual que el resto de la aplicación.
"""
from __future__ import annotations

import base64
import json
import mimetypes
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr, parseaddr
from pathlib import Path

from . import domain
from .paths import data_dir

_PREFIJO = "b64:"
_MARCA_KEYRING = "keyring:"
_SERVICIO_KEYRING = "taller-coches-smtp"


def _keyring():
    """Devuelve el módulo keyring si está disponible y operativo, si no None."""
    try:
        import keyring
        from keyring.errors import KeyringError  # noqa: F401

        # comprobar que hay un backend real (no el 'fail' o 'null')
        bk = keyring.get_keyring().__class__.__name__.lower()
        if "fail" in bk or "null" in bk:
            return None
        return keyring
    except Exception:  # noqa: BLE001
        return None


def guardar_password(usuario: str, password: str) -> str:
    """Guarda la contraseña. Devuelve lo que hay que almacenar en la BD.

    Usa el llavero del sistema operativo si está disponible (más seguro); si no,
    guarda la contraseña ofuscada en base64 en la propia BD.
    """
    kr = _keyring()
    if kr and usuario:
        try:
            kr.set_password(_SERVICIO_KEYRING, usuario, password or "")
            return _MARCA_KEYRING
        except Exception:  # noqa: BLE001
            pass
    return ofuscar(password)


def leer_password(valor_bd: str, usuario: str) -> str:
    if valor_bd == _MARCA_KEYRING:
        kr = _keyring()
        if kr and usuario:
            try:
                return kr.get_password(_SERVICIO_KEYRING, usuario) or ""
            except Exception:  # noqa: BLE001
                return ""
        return ""
    return desofuscar(valor_bd)


def password_en_llavero() -> bool:
    return _keyring() is not None

SEGURIDAD = {
    "starttls": "STARTTLS (puerto 587, recomendado)",
    "ssl": "SSL/TLS (puerto 465)",
    "ninguna": "Sin cifrado (no recomendado)",
}

# Ajustes típicos de proveedores conocidos.
PRESETS_INTEGRADOS = {
    "Gmail": {"smtp_host": "smtp.gmail.com", "smtp_port": 587, "smtp_seguridad": "starttls"},
    "Outlook / Office 365": {"smtp_host": "smtp.office365.com", "smtp_port": 587,
                             "smtp_seguridad": "starttls"},
    "Yahoo": {"smtp_host": "smtp.mail.yahoo.com", "smtp_port": 465, "smtp_seguridad": "ssl"},
    "iCloud": {"smtp_host": "smtp.mail.me.com", "smtp_port": 587, "smtp_seguridad": "starttls"},
    "Zoho": {"smtp_host": "smtp.zoho.eu", "smtp_port": 465, "smtp_seguridad": "ssl"},
    "IONOS / 1&1": {"smtp_host": "smtp.ionos.es", "smtp_port": 587,
                    "smtp_seguridad": "starttls"},
    "OVH": {"smtp_host": "ssl0.ovh.net", "smtp_port": 587, "smtp_seguridad": "starttls"},
}

_ARCHIVO_PRESETS = "proveedores_correo.json"


def _ruta_presets() -> Path:
    return data_dir() / _ARCHIVO_PRESETS


def cargar_presets_usuario() -> dict:
    """Proveedores SMTP que ha añadido el usuario (guardados en la carpeta de datos)."""
    p = _ruta_presets()
    if not p.is_file():
        return {}
    try:
        datos = json.loads(p.read_text(encoding="utf-8"))
        return {k: v for k, v in datos.items() if isinstance(v, dict)}
    except (json.JSONDecodeError, OSError):
        return {}


def guardar_preset_usuario(nombre: str, host: str, port: int, seguridad: str) -> None:
    nombre = nombre.strip()
    if not nombre or not host.strip():
        raise ValueError("El proveedor necesita un nombre y un servidor SMTP.")
    presets = cargar_presets_usuario()
    presets[nombre] = {"smtp_host": host.strip(), "smtp_port": int(port),
                       "smtp_seguridad": seguridad}
    _ruta_presets().write_text(json.dumps(presets, indent=2, ensure_ascii=False),
                               encoding="utf-8")


def eliminar_preset_usuario(nombre: str) -> None:
    presets = cargar_presets_usuario()
    if presets.pop(nombre, None) is not None:
        _ruta_presets().write_text(json.dumps(presets, indent=2, ensure_ascii=False),
                                   encoding="utf-8")


def todos_los_presets() -> dict:
    """Proveedores integrados + los añadidos por el usuario."""
    return {**PRESETS_INTEGRADOS, **cargar_presets_usuario()}


# Compatibilidad
PRESETS = PRESETS_INTEGRADOS

ASUNTO_DEFECTO = "{tipo} {numero} - {taller}"
CUERPO_DEFECTO = (
    "Estimado/a cliente:\n\n"
    "Adjuntamos el documento {tipo} {numero}"
    " correspondiente a su vehículo {matricula}.\n\n"
    "Para cualquier consulta, no dude en contactar con nosotros.\n\n"
    "Un saludo,\n{taller}\n{telefono}"
)


def ofuscar(texto: str) -> str:
    if not texto or texto.startswith(_PREFIJO):
        return texto
    return _PREFIJO + base64.b64encode(texto.encode("utf-8")).decode("ascii")


def desofuscar(texto: str) -> str:
    if not texto or not texto.startswith(_PREFIJO):
        return texto or ""
    try:
        return base64.b64decode(texto[len(_PREFIJO):]).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return ""


@dataclass
class ConfigCorreo:
    host: str = ""
    port: int = 587
    seguridad: str = "starttls"
    usuario: str = ""
    password: str = ""
    remitente: str = ""
    nombre_remitente: str = ""
    asunto: str = ASUNTO_DEFECTO
    cuerpo: str = CUERPO_DEFECTO

    @classmethod
    def desde_empresa(cls, row) -> "ConfigCorreo":
        return cls(
            host=row["smtp_host"] or "",
            port=int(row["smtp_port"] or 587),
            seguridad=row["smtp_seguridad"] or "starttls",
            usuario=row["smtp_usuario"] or "",
            password=leer_password(row["smtp_password"] or "", row["smtp_usuario"] or ""),
            remitente=(row["smtp_remitente"] or row["smtp_usuario"] or "").strip(),
            nombre_remitente=row["nombre"] or "",
            asunto=row["email_asunto"] or ASUNTO_DEFECTO,
            cuerpo=row["email_cuerpo"] or CUERPO_DEFECTO,
        )

    @property
    def configurado(self) -> bool:
        return bool(self.host and self.usuario and self.remitente)


def contexto_documento(doc_row, cliente_row, vehiculo_row, empresa_row) -> dict:
    """Valores para sustituir en las plantillas de asunto y cuerpo."""
    return {
        "tipo": domain.TIPO_NOMBRE.get(doc_row["tipo"], doc_row["tipo"]),
        "numero": doc_row["numero"],
        "fecha": doc_row["fecha"],
        "cliente": (cliente_row["nombre"] if cliente_row else "").strip(),
        "matricula": (vehiculo_row["matricula"] if vehiculo_row else "").strip() or "-",
        "total": domain.formato_moneda(doc_row["total"]),
        "taller": (empresa_row["nombre"] if empresa_row else "").strip(),
        "telefono": (empresa_row["telefono"] if empresa_row else "").strip(),
    }


def aplicar_plantilla(plantilla: str, contexto: dict) -> str:
    try:
        return plantilla.format(**contexto)
    except (KeyError, IndexError, ValueError):
        # Si la plantilla tiene un marcador desconocido, se devuelve tal cual.
        return plantilla


def construir_mensaje(config: ConfigCorreo, destinatarios: list[str], asunto: str,
                      cuerpo: str, adjuntos: list[Path]) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = formataddr((config.nombre_remitente or "", config.remitente))
    msg["To"] = ", ".join(destinatarios)
    msg["Subject"] = asunto
    msg.set_content(cuerpo)
    for ruta in adjuntos:
        ruta = Path(ruta)
        tipo, _ = mimetypes.guess_type(ruta.name)
        maintype, subtype = (tipo or "application/octet-stream").split("/", 1)
        msg.add_attachment(ruta.read_bytes(), maintype=maintype, subtype=subtype,
                           filename=ruta.name)
    return msg


def _conectar(config: ConfigCorreo, timeout: float = 20.0):
    if config.seguridad == "ssl":
        srv = smtplib.SMTP_SSL(config.host, config.port, timeout=timeout,
                               context=ssl.create_default_context())
    else:
        srv = smtplib.SMTP(config.host, config.port, timeout=timeout)
        srv.ehlo()
        if config.seguridad == "starttls":
            srv.starttls(context=ssl.create_default_context())
            srv.ehlo()
    if config.usuario:
        srv.login(config.usuario, config.password)
    return srv


def probar_conexion(config: ConfigCorreo) -> None:
    """Conecta y autentica. Lanza una excepción con un mensaje claro si algo falla."""
    if not config.host:
        raise ValueError("Falta el servidor SMTP.")
    try:
        srv = _conectar(config)
        srv.quit()
    except smtplib.SMTPAuthenticationError:
        raise RuntimeError(
            "Usuario o contraseña rechazados por el servidor. Con Gmail u Outlook "
            "suele hacer falta una «contraseña de aplicación», no la del correo.")
    except (smtplib.SMTPException, OSError, ssl.SSLError) as e:
        raise RuntimeError(f"No se pudo conectar con {config.host}:{config.port}. {e}")


def enviar(config: ConfigCorreo, destinatarios: list[str], asunto: str, cuerpo: str,
           adjuntos: list[Path]) -> None:
    destinatarios = [d.strip() for d in destinatarios if d.strip()]
    if not destinatarios:
        raise ValueError("Indica al menos un destinatario.")
    for d in destinatarios:
        if "@" not in parseaddr(d)[1]:
            raise ValueError(f"Dirección de correo no válida: {d}")
    if not config.configurado:
        raise ValueError("El correo no está configurado (Archivo → Configurar correo).")

    msg = construir_mensaje(config, destinatarios, asunto, cuerpo, adjuntos)
    try:
        srv = _conectar(config)
        try:
            srv.send_message(msg)
        finally:
            srv.quit()
    except smtplib.SMTPAuthenticationError:
        raise RuntimeError(
            "Usuario o contraseña rechazados. Con Gmail/Outlook usa una "
            "«contraseña de aplicación».")
    except (smtplib.SMTPException, OSError, ssl.SSLError) as e:
        raise RuntimeError(f"No se pudo enviar el correo: {e}")
