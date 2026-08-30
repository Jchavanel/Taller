#!/usr/bin/env python3
"""Genera el fichero ``latest.json`` que consulta la aplicación para autoactualizarse.

Se usa desde el workflow de GitHub Actions al publicar una release, pero también sirve
para hacerlo a mano.

Ejemplo:
    python scripts/generar_latest_json.py \\
        --version 1.11.0 --repo usuario/taller-coches \\
        --appimage dist/Taller-de-Coches-x86_64.AppImage \\
        --fuente   dist/taller-coches-1.11.0.tar.gz \\
        --notas-file NOTAS.txt \\
        --salida   dist/latest.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path


def sha256(ruta: Path) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for trozo in iter(lambda: f.read(1 << 20), b""):
            h.update(trozo)
    return h.hexdigest()


def activo(repo: str, version: str, ruta: Path) -> dict:
    url = (f"https://github.com/{repo}/releases/download/"
           f"v{version}/{ruta.name}")
    return {"url": url, "sha256": sha256(ruta), "bytes": ruta.stat().st_size}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--version", required=True)
    p.add_argument("--repo", required=True, help="usuario/repositorio de GitHub")
    p.add_argument("--appimage", type=Path)
    p.add_argument("--fuente", type=Path)
    p.add_argument("--notas", default="")
    p.add_argument("--notas-file", type=Path)
    p.add_argument("--salida", type=Path, default=Path("dist/latest.json"))
    args = p.parse_args(argv)

    version = args.version.lstrip("vV")
    notas = args.notas
    if args.notas_file and args.notas_file.is_file():
        notas = args.notas_file.read_text(encoding="utf-8").strip()

    manifiesto: dict = {
        "version": version,
        "fecha": dt.date.today().isoformat(),
        "notas": notas,
    }
    if args.appimage:
        if not args.appimage.is_file():
            print(f"AVISO: no existe {args.appimage}, se omite AppImage", file=sys.stderr)
        else:
            manifiesto["appimage"] = activo(args.repo, version, args.appimage)
    if args.fuente:
        if not args.fuente.is_file():
            print(f"AVISO: no existe {args.fuente}, se omite fuente", file=sys.stderr)
        else:
            manifiesto["fuente"] = activo(args.repo, version, args.fuente)

    if "appimage" not in manifiesto and "fuente" not in manifiesto:
        print("ERROR: no se ha añadido ningún paquete al manifiesto", file=sys.stderr)
        return 1

    args.salida.parent.mkdir(parents=True, exist_ok=True)
    args.salida.write_text(
        json.dumps(manifiesto, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Escrito {args.salida}:")
    print(args.salida.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
