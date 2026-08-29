"""Comprobación e instalación de actualizaciones desde GitHub Releases.

La aplicación consulta un fichero ``latest.json`` publicado como recurso de la última
*release* del repositorio. Si anuncia una versión superior a la instalada, descarga el
paquete adecuado para el tipo de instalación (AppImage o código fuente), comprueba su
huella **SHA-256** y lo aplica, reiniciando la aplicación.

Todo se hace por HTTPS contra GitHub. La huella SHA-256 del manifiesto protege frente a
una descarga corrupta o manipulada en tránsito; no sustituye a una firma de código.

Configuración:
  - Constante ``REPO`` (abajo): ``usuario/repositorio`` de GitHub.
  - Variable de entorno ``TALLER_UPDATE_REPO`` para cambiarlo sin tocar el código.
  - Variable de entorno ``TALLER_UPDATE_URL`` para apuntar a un manifiesto concreto
    (útil en pruebas).
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import ssl
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

from . import __version__
from .errores import log
from .paths import _project_root

# --- CONFIGURA AQUÍ tu repositorio de GitHub (usuario/repositorio) --------------
REPO = os.environ.get("TALLER_UPDATE_REPO", "TU_USUARIO/taller-coches")
# ------------------------------------------------------------------------------

URL_MANIFIESTO = os.environ.get(
    "TALLER_UPDATE_URL",
    f"https://github.com/{REPO}/releases/latest/download/latest.json",
)
_TIMEOUT = 15
_UA = {"User-Agent": f"taller-coches/{__version__}"}
_ANTES_DE_REINICIAR = None  # callback opcional, se fija en aplicar()

# Si nadie ha configurado el repositorio, el sistema de actualización se desactiva
# silenciosamente (no hay adónde llamar).
SIN_CONFIGURAR = REPO.startswith("TU_USUARIO") and "TALLER_UPDATE_URL" not in os.environ


class ErrorActualizacion(RuntimeError):
    """Fallo controlado durante la comprobación o instalación de una actualización."""


# --------------------------------------------------------------------- versiones
def _version_tupla(v: str) -> tuple[int, ...]:
    partes: list[int] = []
    for trozo in str(v).strip().lstrip("vV").split("."):
        digitos = ""
        for ch in trozo:
            if ch.isdigit():
                digitos += ch
            else:
                break
        partes.append(int(digitos or 0))
    return tuple(partes) or (0,)


def hay_version_nueva(remota: str, actual: str = __version__) -> bool:
    return _version_tupla(remota) > _version_tupla(actual)


# ------------------------------------------------------------- tipo de instalación
def modo_instalacion() -> str:
    """'appimage', 'congelado' (PyInstaller), 'git' (clon de desarrollo) o 'fuente'."""
    if os.environ.get("APPIMAGE"):
        return "appimage"
    if getattr(sys, "frozen", False):
        return "congelado"
    if (_project_root() / ".git").is_dir():
        return "git"
    return "fuente"


def _ctx() -> ssl.SSLContext:
    return ssl.create_default_context()


# --------------------------------------------------------------------- comprobar
def comprobar() -> dict | None:
    """Descarga el manifiesto. Devuelve el dict si hay versión nueva, ``None`` si no.

    Lanza ``ErrorActualizacion`` si no se puede contactar o el manifiesto no es válido.
    """
    if SIN_CONFIGURAR:
        return None
    try:
        req = urllib.request.Request(URL_MANIFIESTO, headers=_UA)
        with urllib.request.urlopen(req, timeout=_TIMEOUT, context=_ctx()) as r:
            manifiesto = json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise ErrorActualizacion(f"No se pudo comprobar si hay actualizaciones: {e}") from e
    except json.JSONDecodeError as e:
        raise ErrorActualizacion("El servidor devolvió un manifiesto ilegible.") from e

    if not isinstance(manifiesto, dict) or not manifiesto.get("version"):
        raise ErrorActualizacion("Manifiesto de actualización no válido.")

    log().info("Actualizaciones: instalada %s, disponible %s",
               __version__, manifiesto["version"])
    if not hay_version_nueva(manifiesto["version"]):
        return None
    return manifiesto


def _info_paquete(manifiesto: dict) -> dict:
    clave = "appimage" if modo_instalacion() == "appimage" else "fuente"
    info = manifiesto.get(clave)
    if not isinstance(info, dict) or not info.get("url"):
        raise ErrorActualizacion(
            "Esta actualización no incluye un paquete compatible con tu instalación.")
    return info


# --------------------------------------------------------------------- descargar
def descargar(manifiesto: dict, progreso=None) -> Path:
    """Descarga y verifica el paquete. Devuelve la ruta al fichero en una carpeta temporal.

    ``progreso`` se llama con ``(bytes_descargados, bytes_totales)`` (totales puede ser 0).
    """
    info = _info_paquete(manifiesto)
    url = info["url"]
    esperado = str(info.get("sha256") or "").lower().strip()

    tmp = Path(tempfile.mkdtemp(prefix="taller-actu-"))
    destino = tmp / (os.path.basename(url.split("?")[0]) or "paquete")
    h = hashlib.sha256()
    try:
        req = urllib.request.Request(url, headers=_UA)
        with urllib.request.urlopen(req, timeout=_TIMEOUT, context=_ctx()) as r, \
                open(destino, "wb") as f:
            total = int(r.headers.get("Content-Length") or 0)
            hecho = 0
            while True:
                trozo = r.read(65536)
                if not trozo:
                    break
                f.write(trozo)
                h.update(trozo)
                hecho += len(trozo)
                if progreso:
                    progreso(hecho, total)
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        shutil.rmtree(tmp, ignore_errors=True)
        raise ErrorActualizacion(f"Falló la descarga: {e}") from e

    if esperado and h.hexdigest() != esperado:
        shutil.rmtree(tmp, ignore_errors=True)
        raise ErrorActualizacion(
            "El fichero descargado no coincide con la huella SHA-256 esperada. "
            "Actualización cancelada por seguridad.")
    return destino


# --------------------------------------------------------------------- aplicar
def aplicar(paquete: Path, antes_de_reiniciar=None) -> None:
    """Instala el paquete descargado y **reinicia** la aplicación (no retorna si va bien).

    ``antes_de_reiniciar`` (opcional) se ejecuta justo antes del reinicio, cuando los
    ficheros ya están sustituidos: úsalo para cerrar la base de datos limpiamente.
    """
    modo = modo_instalacion()
    if modo == "git":
        raise ErrorActualizacion(
            "Esta copia se ejecuta desde un clon de git. Actualiza con «git pull».")
    if modo == "congelado":
        raise ErrorActualizacion(
            "Este ejecutable independiente no se actualiza solo. Descarga la versión "
            "nueva desde la página de releases.")
    global _ANTES_DE_REINICIAR
    _ANTES_DE_REINICIAR = antes_de_reiniciar
    if modo == "appimage":
        _aplicar_appimage(paquete)
    else:
        _aplicar_fuente(paquete)


def _relanzar_argv(modo: str) -> tuple[str, list[str]]:
    if modo == "appimage":
        exe = os.environ["APPIMAGE"]
        return exe, [exe]
    if modo == "congelado":
        return sys.executable, [sys.executable]
    return sys.executable, [sys.executable, "-m", "taller"]


def _reiniciar(modo: str) -> None:
    exe, argv = _relanzar_argv(modo)
    log().info("Reiniciando tras actualizar: %s", argv)
    if callable(_ANTES_DE_REINICIAR):
        try:
            _ANTES_DE_REINICIAR()
        except Exception:  # noqa: BLE001
            log().exception("Fallo en la limpieza previa al reinicio")
    sys.stdout.flush()
    sys.stderr.flush()
    if modo not in ("appimage", "congelado"):
        try:
            os.chdir(_project_root())
        except OSError:
            pass
    os.execv(exe, argv)


def _aplicar_appimage(nuevo: Path) -> None:
    ruta_env = os.environ.get("APPIMAGE")
    if not ruta_env:
        raise ErrorActualizacion("No se encuentra la ruta del AppImage en ejecución.")
    actual = Path(ruta_env).resolve()
    if not os.access(actual.parent, os.W_OK):
        raise ErrorActualizacion(
            f"No hay permiso para escribir en {actual.parent}.\n"
            "Mueve el AppImage a tu carpeta personal (o Descargas) y vuelve a intentarlo.")
    anterior = actual.parent / (actual.name + ".anterior")
    try:
        if anterior.exists():
            anterior.unlink()
        os.replace(actual, anterior)          # conserva la versión previa
        shutil.move(str(nuevo), str(actual))
        os.chmod(actual, 0o755)
    except OSError as e:
        # intento de dejar todo como estaba
        if not actual.exists() and anterior.exists():
            os.replace(anterior, actual)
        raise ErrorActualizacion(f"No se pudo sustituir el AppImage: {e}") from e
    finally:
        shutil.rmtree(nuevo.parent, ignore_errors=True)
    _reiniciar("appimage")


def _miembros_seguros(tar: tarfile.TarFile, destino: Path) -> None:
    destino = destino.resolve()
    for m in tar.getmembers():
        p = (destino / m.name).resolve()
        if destino not in p.parents and p != destino:
            raise ErrorActualizacion("El paquete contiene rutas inseguras. Cancelado.")


def _aplicar_fuente(tar_gz: Path) -> None:
    raiz = _project_root()
    if not os.access(raiz, os.W_OK):
        raise ErrorActualizacion(
            f"No hay permiso para escribir en {raiz}. Actualiza esa carpeta a mano.")

    tmp = Path(tempfile.mkdtemp(prefix="taller-src-"))
    try:
        with tarfile.open(tar_gz) as t:
            _miembros_seguros(t, tmp)
            try:
                t.extractall(tmp, filter="data")  # Python 3.12+
            except TypeError:
                t.extractall(tmp)
        # el .tar.gz contiene una carpeta raíz (taller-coches/)
        subdirs = [p for p in tmp.iterdir() if p.is_dir()]
        origen = subdirs[0] if len(subdirs) == 1 else tmp
        if not (origen / "taller").is_dir():
            raise ErrorActualizacion("El paquete no tiene la estructura esperada.")

        excluir = {"datos", ".venv", ".build-venv", "venv", ".git", "__pycache__"}
        for elemento in origen.iterdir():
            if elemento.name in excluir:
                continue
            destino = raiz / elemento.name
            if elemento.is_dir():
                shutil.copytree(
                    elemento, destino, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            else:
                shutil.copy2(elemento, destino)
    except (OSError, tarfile.TarError) as e:
        raise ErrorActualizacion(f"No se pudo aplicar la actualización: {e}") from e
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        shutil.rmtree(tar_gz.parent, ignore_errors=True)

    _instalar_dependencias(raiz)
    _reiniciar(modo_instalacion())


def _instalar_dependencias(raiz: Path) -> None:
    req = raiz / "requirements.txt"
    if not req.is_file():
        return
    import subprocess
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-q", "--disable-pip-version-check",
             "-r", str(req)],
            check=False, timeout=600)
    except (OSError, subprocess.SubprocessError) as e:
        log().warning("No se pudieron actualizar las dependencias: %s", e)
