"""Sistema de licencia offline con firma Ed25519.

El desarrollador genera un par de claves una vez (``scripts/generar_par_claves.py``),
pega aquí la **clave pública** y guarda la privada fuera del repositorio. Para cada
cliente emite un código de licencia firmado con caducidad
(``scripts/generar_licencia.py``). La aplicación lo verifica sin conexión.

Mientras ``CLAVE_PUBLICA_HEX`` esté vacía, el control de licencia está **desactivado**
(la aplicación funciona sin restricciones).

Estados:
  - prueba          : instalación nueva sin licencia, dentro de los 30 días → opera
  - prueba_fin      : se acabó la prueba → modo consulta (solo lectura)
  - activa          : licencia válida → opera
  - por_caducar     : licencia válida, quedan ≤ 15 días → opera, con aviso
  - caducada        : licencia vencida → modo consulta
  - otra_maquina    : licencia asignada a otro equipo → modo consulta
  - invalida        : licencia dañada o firma incorrecta → modo consulta

Limitación conocida: la aplicación es Python y se distribuye con su código; este control
disuade la copia y ordena las renovaciones, pero alguien con el código puede quitarlo.
Para endurecerlo habría que compilar el binario (Nuitka/Cython).
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import platform
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .errores import log
from .paths import data_dir

# --- Clave pública del desarrollador (hex de 32 bytes Ed25519). Vacía = desactivado. --
CLAVE_PUBLICA_HEX = ""
# ------------------------------------------------------------------------------------

PRUEBA_DIAS = 30
AVISO_DIAS = 15
CONTACTO = "Para licencias y renovaciones, contacta con el proveedor del programa."

_FICHERO = "licencia.txt"

try:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    _CRYPTO_OK = True
except Exception:  # noqa: BLE001
    _CRYPTO_OK = False


# --------------------------------------------------------------------- utilidades
def _b64u_dec(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _b64u_enc(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def huella_maquina() -> str:
    """Identificador estable de este equipo (para atar una licencia a una máquina)."""
    partes = [platform.node() or ""]
    for ruta in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
        try:
            partes.append(Path(ruta).read_text(encoding="ascii").strip())
            break
        except OSError:
            pass
    if os.name == "nt":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                r"SOFTWARE\Microsoft\Cryptography") as k:
                partes.append(winreg.QueryValueEx(k, "MachineGuid")[0])
        except OSError:
            pass
    base = "|".join(p for p in partes if p)
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:20]


# --------------------------------------------------------------------- licencia
@dataclass(frozen=True)
class Licencia:
    cliente: str
    nif: str
    emitida: date
    expira: date
    maquinas: list[str] | None
    plan: str
    notas: str


def verificar(token: str) -> Licencia | None:
    """Comprueba la firma y devuelve la licencia, o ``None`` si no es válida."""
    if not CLAVE_PUBLICA_HEX or not _CRYPTO_OK:
        return None
    try:
        payload_b64, firma_b64 = token.strip().split(".")
        payload = _b64u_dec(payload_b64)
        firma = _b64u_dec(firma_b64)
        clave = Ed25519PublicKey.from_public_bytes(bytes.fromhex(CLAVE_PUBLICA_HEX))
        clave.verify(firma, payload)  # lanza InvalidSignature si no cuadra
        d = json.loads(payload)
        return Licencia(
            cliente=str(d["cliente"]),
            nif=str(d.get("nif", "")),
            emitida=date.fromisoformat(d["emitida"]),
            expira=date.fromisoformat(d["expira"]),
            maquinas=list(d["maquinas"]) if d.get("maquinas") else None,
            plan=str(d.get("plan", "completo")),
            notas=str(d.get("notas", "")),
        )
    except (ValueError, KeyError, TypeError):
        return None
    except InvalidSignature:
        return None
    except Exception:  # noqa: BLE001 - cualquier fallo del verificador = licencia no válida
        log().exception("Fallo verificando la licencia")
        return None


# --------------------------------------------------------------------- estado
@dataclass(frozen=True)
class Estado:
    codigo: str
    puede_operar: bool
    nivel: str            # "ok" | "aviso" | "bloqueo"
    titulo: str
    detalle: str
    dias: int | None = None
    licencia: Licencia | None = None


def _ruta_fichero() -> Path:
    return data_dir() / _FICHERO


def _leer_token(repo) -> str:
    tok = repo.get_ajuste("licencia_token", "")
    if tok:
        return tok
    try:
        return _ruta_fichero().read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _hoy_efectivo(repo) -> date:
    """Fecha de hoy, protegida contra atrasar el reloj del sistema."""
    hoy = date.today()
    vista = repo.get_ajuste("licencia_fecha_max", "")
    ref = None
    if vista:
        try:
            ref = date.fromisoformat(vista)
        except ValueError:
            ref = None
    if ref is None or hoy > ref:
        repo.set_ajuste("licencia_fecha_max", hoy.isoformat())
        return hoy
    return ref  # el reloj va por detrás de una fecha ya vista: usamos esa


def evaluar(repo) -> Estado:
    if not CLAVE_PUBLICA_HEX or not _CRYPTO_OK:
        return Estado("desactivada", True, "ok", "", "")

    hoy = _hoy_efectivo(repo)
    token = _leer_token(repo)

    if token:
        lic = verificar(token)
        if lic is None:
            return Estado("invalida", False, "bloqueo", "Licencia no válida",
                          "La licencia guardada está dañada o no es auténtica.\n"
                          + CONTACTO)
        if lic.maquinas and huella_maquina() not in lic.maquinas:
            return Estado("otra_maquina", False, "bloqueo", "Licencia de otro equipo",
                          "Esta licencia está asignada a otro equipo.\n" + CONTACTO,
                          licencia=lic)
        dias = (lic.expira - hoy).days
        if dias < 0:
            return Estado("caducada", False, "bloqueo", "Licencia caducada",
                          f"La licencia de «{lic.cliente}» caducó el "
                          f"{lic.expira:%d/%m/%Y}.\n" + CONTACTO, dias, lic)
        if dias <= AVISO_DIAS:
            return Estado("por_caducar", True, "aviso", "La licencia caduca pronto",
                          f"Tu licencia caduca el {lic.expira:%d/%m/%Y} "
                          f"(quedan {dias} días).\n" + CONTACTO, dias, lic)
        return Estado("activa", True, "ok", "", "", dias, lic)

    # sin licencia: periodo de prueba
    inicio = repo.get_ajuste("prueba_inicio", "")
    if not inicio:
        repo.set_ajuste("prueba_inicio", hoy.isoformat())
        inicio = hoy.isoformat()
    try:
        d0 = date.fromisoformat(inicio)
    except ValueError:
        d0 = hoy
    dias = PRUEBA_DIAS - (hoy - d0).days
    if dias < 0:
        return Estado("prueba_fin", False, "bloqueo", "Periodo de prueba terminado",
                      f"Los {PRUEBA_DIAS} días de prueba han terminado.\n"
                      "Introduce una licencia para seguir creando documentos.\n"
                      + CONTACTO, dias)
    return Estado("prueba", True, "aviso", "Versión de prueba",
                  f"Versión de prueba: quedan {dias} días.\n" + CONTACTO, dias)


def guardar_token(repo, token: str) -> Licencia:
    """Valida y guarda una licencia nueva. Lanza ``ValueError`` con un motivo claro."""
    token = (token or "").strip()
    if not token:
        raise ValueError("No has introducido ninguna licencia.")
    lic = verificar(token)
    if lic is None:
        raise ValueError("La licencia no es válida (firma incorrecta o texto incompleto).")
    if lic.maquinas and huella_maquina() not in lic.maquinas:
        raise ValueError("Esta licencia está asignada a otro equipo.\n"
                         f"Huella de este equipo: {huella_maquina()}")
    if lic.expira < _hoy_efectivo(repo):
        raise ValueError(f"Esa licencia ya estaba caducada ({lic.expira:%d/%m/%Y}).")
    repo.set_ajuste("licencia_token", token)
    try:
        _ruta_fichero().write_text(token, encoding="utf-8")
    except OSError:
        pass
    return lic


# ------------------------------------------------------- caché para el resto de la app
_ESTADO: Estado | None = None


def fijar(estado: Estado) -> None:
    global _ESTADO
    _ESTADO = estado


def actual() -> Estado | None:
    return _ESTADO


def puede_operar() -> bool:
    """True si se pueden crear/modificar datos. Por defecto True (sin evaluar todavía)."""
    return _ESTADO is None or _ESTADO.puede_operar


def exigir_operar(parent=None) -> bool:
    """True si se puede operar; si no, avisa al usuario y devuelve False."""
    if puede_operar():
        return True
    try:
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.warning(
            parent, "Licencia",
            "El programa está en modo consulta: la licencia ha caducado o el periodo "
            "de prueba ha terminado.\n\n"
            "Puedes consultar, imprimir y exportar lo que ya tienes, pero no crear ni "
            "modificar. Ve a Archivo → Licencia para activar una licencia.")
    except Exception:  # noqa: BLE001
        pass
    return False
