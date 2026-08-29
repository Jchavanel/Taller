"""Rutas de datos de la aplicación.

Por defecto todo se guarda en la carpeta ``datos/`` **dentro de la propia carpeta del
programa**, para que sea fácil de localizar y de copiar. Si esa carpeta no se puede
escribir (por ejemplo si el programa está instalado en una ruta protegida), se usa la
carpeta de datos del usuario del sistema.

Se puede forzar otra ubicación con la variable de entorno ``TALLER_DATA_DIR`` (carpeta)
o ``TALLER_DB`` (fichero concreto de base de datos).

Nada se guarda en la nube.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

APP_DIR_NAME = "taller-coches"


def _project_root() -> Path:
    """Carpeta del programa: junto al ejecutable si está empaquetado, si no la raíz del repo."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _es_escribible(carpeta: Path) -> bool:
    try:
        carpeta.mkdir(parents=True, exist_ok=True)
        prueba = carpeta / ".escritura"
        prueba.touch()
        prueba.unlink()
        return True
    except OSError:
        return False


def _carpeta_datos_usuario() -> Path:
    """Ubicación anterior a la v1.3.2 (carpeta de datos del sistema operativo)."""
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        base = Path(xdg)
    elif os.name == "nt" and os.environ.get("APPDATA"):
        base = Path(os.environ["APPDATA"])
    else:
        base = Path.home() / ".local" / "share"
    return base / APP_DIR_NAME


def data_dir() -> Path:
    override = os.environ.get("TALLER_DATA_DIR")
    if override:
        d = Path(override).expanduser()
        d.mkdir(parents=True, exist_ok=True)
        return d

    # En un AppImage el ejecutable está en un sistema de solo lectura: guardar en $HOME.
    if not os.environ.get("APPIMAGE"):
        preferida = _project_root() / "datos"
        if _es_escribible(preferida):
            return preferida

    alternativa = _carpeta_datos_usuario()
    alternativa.mkdir(parents=True, exist_ok=True)
    return alternativa


def db_path() -> Path:
    override = os.environ.get("TALLER_DB")
    if override:
        p = Path(override).expanduser()
        p.parent.mkdir(parents=True, exist_ok=True)
        return p
    return data_dir() / "taller.db"


def documents_dir() -> Path:
    d = data_dir() / "documentos"
    d.mkdir(parents=True, exist_ok=True)
    return d


def migrar_datos_antiguos() -> Path | None:
    """Si hay datos en la ubicación antigua y no en la nueva, los traslada.

    Devuelve la ruta de origen si se hizo la migración, o ``None``.
    """
    if os.environ.get("TALLER_DB") or os.environ.get("TALLER_DATA_DIR"):
        return None

    destino = data_dir()
    origen = _carpeta_datos_usuario()
    if origen == destino or not origen.is_dir():
        return None

    db_nueva = destino / "taller.db"
    db_vieja = origen / "taller.db"
    if db_nueva.exists() or not db_vieja.exists():
        return None

    for nombre in ("taller.db", "taller.db-wal", "taller.db-shm", "logo.png"):
        f = origen / nombre
        if f.is_file():
            shutil.copy2(f, destino / nombre)

    docs_viejos = origen / "documentos"
    if docs_viejos.is_dir():
        destino_docs = destino / "documentos"
        destino_docs.mkdir(exist_ok=True)
        for f in docs_viejos.glob("*"):
            if f.is_file() and not (destino_docs / f.name).exists():
                shutil.copy2(f, destino_docs / f.name)

    return origen
