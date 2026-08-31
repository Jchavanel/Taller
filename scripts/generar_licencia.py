#!/usr/bin/env python3
"""Emite un código de licencia firmado para un cliente.

    python scripts/generar_licencia.py --cliente "Taller X, S.L." --nif B12345678 --meses 12
    python scripts/generar_licencia.py --cliente "Demo" --expira 2027-01-31 --maquina a1b2c3...

El cliente ve su huella de equipo en Archivo -> Licencia -> «Copiar». Si pasas una o
varias --maquina, la licencia solo valdrá en esos equipos; si no, vale en cualquiera.

La salida es una sola línea: pásala al cliente (correo). Él la pega en Archivo -> Licencia.
"""
from __future__ import annotations

import argparse
import base64
import calendar
import json
import sys
from datetime import date
from pathlib import Path

from cryptography.hazmat.primitives import serialization


def _b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def add_months(d: date, meses: int) -> date:
    total = d.month - 1 + meses
    anio = d.year + total // 12
    mes = total % 12 + 1
    dia = min(d.day, calendar.monthrange(anio, mes)[1])
    return date(anio, mes, dia)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cliente", required=True)
    p.add_argument("--nif", default="")
    p.add_argument("--meses", type=int, help="validez en meses desde hoy")
    p.add_argument("--expira", help="fecha de caducidad AAAA-MM-DD (alternativa a --meses)")
    p.add_argument("--maquina", action="append", default=[],
                   help="huella de equipo (repetible). Sin esto, vale en cualquier equipo")
    p.add_argument("--sin-maquina", action="store_true",
                   help="emitir a propósito una licencia sin atar a ningún equipo, sin avisar")
    p.add_argument("--plan", default="completo")
    p.add_argument("--notas", default="")
    p.add_argument("--clave", type=Path,
                   default=Path.home() / ".taller-licencias" / "privada.pem")
    p.add_argument("--fichero", type=Path, help="además, escribe el token en este fichero")
    args = p.parse_args(argv)

    if not args.clave.is_file():
        print(f"No se encuentra la clave privada en {args.clave}. "
              "Genérala con scripts/generar_par_claves.py", file=sys.stderr)
        return 1

    if args.expira:
        expira = date.fromisoformat(args.expira)
    elif args.meses:
        expira = add_months(date.today(), args.meses)
    else:
        print("Indica --meses N o --expira AAAA-MM-DD", file=sys.stderr)
        return 1

    if not args.maquina and not args.sin_maquina:
        print(
            "\n  AVISO: vas a emitir una licencia SIN atar a ningún equipo.\n"
            "  Cualquiera con este código podría usarla en otro ordenador hasta que\n"
            f"  caduque ({expira:%d/%m/%Y}).\n\n"
            "  Para atarla, pide la 'huella' al cliente (Archivo -> Licencia -> Copiar)\n"
            "  y anade  --maquina <huella>.\n", file=sys.stderr)
        try:
            resp = input("  ¿Emitir de todas formas sin atar a un equipo? (escribe SI): ")
        except EOFError:
            resp = ""
        if resp.strip().lower() not in ("si", "sí", "s"):
            print("Cancelado.", file=sys.stderr)
            return 1

    priv = serialization.load_pem_private_key(args.clave.read_bytes(), password=None)

    payload = json.dumps({
        "cliente": args.cliente,
        "nif": args.nif,
        "emitida": date.today().isoformat(),
        "expira": expira.isoformat(),
        "maquinas": args.maquina or None,
        "plan": args.plan,
        "notas": args.notas,
    }, sort_keys=True, separators=(",", ":")).encode("utf-8")

    firma = priv.sign(payload)
    token = _b64u(payload) + "." + _b64u(firma)

    print(f"\nLicencia para «{args.cliente}»  válida hasta {expira:%d/%m/%Y}"
          + (f"  ({len(args.maquina)} equipo/s)" if args.maquina else "  (cualquier equipo)"))
    print("\n" + token + "\n")
    if args.fichero:
        args.fichero.write_text(token, encoding="utf-8")
        print(f"Escrito en {args.fichero}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
