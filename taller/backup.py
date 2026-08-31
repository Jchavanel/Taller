"""Copias de seguridad automáticas de la base de datos."""
from __future__ import annotations

import datetime as _dt
import shutil
import sqlite3
from pathlib import Path

from .database import Database
from .errores import log
from .paths import data_dir, db_path

MAX_COPIAS = 20
_AJUSTE_EXTERNA = "copia_externa_dir"


def carpeta_copias() -> Path:
    d = data_dir() / "copias"
    d.mkdir(parents=True, exist_ok=True)
    return d


# --------------------------------------------------- copia en carpeta externa (USB)
def carpeta_externa(repo) -> Path | None:
    """Carpeta adicional (pendrive, disco externo…) donde replicar cada copia, o None."""
    valor = repo.get_ajuste(_AJUSTE_EXTERNA, "") if repo is not None else ""
    return Path(valor) if valor else None


def set_carpeta_externa(repo, ruta) -> None:
    repo.set_ajuste(_AJUSTE_EXTERNA, str(ruta) if ruta else "")


def replicar_externa(copia: Path | None, repo) -> tuple[bool, str]:
    """Copia `copia` a la carpeta externa configurada. (ok, mensaje)."""
    base = carpeta_externa(repo)
    if base is None or copia is None:
        return False, ""
    if not base.is_dir():
        return False, (f"La carpeta de copia externa no está disponible:\n{base}\n"
                       "¿Está conectado el pendrive / disco externo?")
    try:
        destino_dir = base / "taller-copias"
        destino_dir.mkdir(parents=True, exist_ok=True)
        destino = destino_dir / copia.name
        shutil.copy2(copia, destino)
        externas = sorted(destino_dir.glob("taller-*.db"), reverse=True)
        for viejo in externas[MAX_COPIAS:]:
            try:
                viejo.unlink()
            except OSError:
                pass
        log().info("Copia replicada en carpeta externa: %s", destino)
        return True, str(destino)
    except OSError as e:
        log().warning("No se pudo replicar la copia en la carpeta externa: %s", e)
        return False, f"No se pudo copiar a la carpeta externa:\n{e}"


def exportar_copia(destino: Path, db: Database | None = None) -> Path:
    """Copia puntual de la base de datos a una ruta cualquiera (USB, disco externo…)."""
    _checkpoint(db)
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(db_path(), destino)
    log().info("Copia exportada a %s", destino)
    return destino


def listar_copias() -> list[Path]:
    return sorted(carpeta_copias().glob("taller-*.db"), reverse=True)


def _checkpoint(db: Database | None) -> None:
    """Vuelca el WAL al fichero .db para que la copia esté completa."""
    try:
        if db is not None:
            db.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            db.conn.commit()
        else:
            con = sqlite3.connect(db_path())
            con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            con.commit()
            con.close()
    except sqlite3.Error as e:  # noqa: BLE001
        log().warning("No se pudo hacer checkpoint antes de la copia: %s", e)


def hacer_copia(db: Database | None = None, forzar: bool = False) -> Path | None:
    """Crea una copia de la BD. Como máximo una al día salvo `forzar`. Devuelve la ruta."""
    origen = db_path()
    if not origen.is_file():
        return None

    hoy = _dt.date.today().isoformat()
    if not forzar and any(p.name.startswith(f"taller-{hoy}") for p in listar_copias()):
        return None  # ya hay copia de hoy

    _checkpoint(db)
    sello = _dt.datetime.now().strftime("%Y-%m-%d-%H%M%S")
    destino = carpeta_copias() / f"taller-{sello}.db"
    n = 2
    while destino.exists():
        destino = carpeta_copias() / f"taller-{sello}-{n}.db"
        n += 1
    try:
        shutil.copy2(origen, destino)
    except OSError as e:
        log().error("Error al crear la copia de seguridad: %s", e)
        return None

    log().info("Copia de seguridad creada: %s", destino.name)
    _podar()
    return destino


def _podar() -> None:
    copias = listar_copias()
    for viejo in copias[MAX_COPIAS:]:
        try:
            viejo.unlink()
        except OSError:
            pass


def restaurar(copia: Path, db: Database | None = None) -> None:
    """Sustituye la BD actual por una copia. Antes guarda una copia del estado actual."""
    import time

    copia = Path(copia)
    if not copia.is_file():
        raise FileNotFoundError(f"No existe la copia {copia}")

    # salvaguarda del estado actual antes de sobrescribir
    hacer_copia(db, forzar=True)
    if db is not None:
        db.close()

    destino = db_path()
    # vuelca y vacía el WAL con una conexión nueva, para que no se aplique sobre la copia
    try:
        con = sqlite3.connect(destino)
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        con.close()
    except sqlite3.Error:
        pass

    for sufijo in ("-wal", "-shm"):
        aux = destino.with_name(destino.name + sufijo)
        for _ in range(10):
            if not aux.exists():
                break
            try:
                aux.unlink()
                break
            except OSError:
                time.sleep(0.1)

    shutil.copy2(copia, destino)
    log().info("Base de datos restaurada desde %s", copia.name)
