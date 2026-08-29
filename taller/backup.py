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


def carpeta_copias() -> Path:
    d = data_dir() / "copias"
    d.mkdir(parents=True, exist_ok=True)
    return d


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
