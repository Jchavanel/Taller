#!/usr/bin/env python3
"""Genera el par de claves Ed25519 para firmar licencias. EJECUTAR UNA SOLA VEZ.

- La **clave privada** se guarda fuera del repositorio (por defecto en
  ~/.taller-licencias/privada.pem). Guárdala a buen recaudo y haz copia: si la
  pierdes, no podrás emitir ni renovar licencias.
- La **clave pública** se imprime en hex: pégala en
  taller/licencia.py -> CLAVE_PUBLICA_HEX y publica una versión nueva.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--salida", type=Path,
                   default=Path.home() / ".taller-licencias" / "privada.pem")
    p.add_argument("--forzar", action="store_true", help="sobrescribir si ya existe")
    args = p.parse_args(argv)

    if args.salida.exists() and not args.forzar:
        print(f"Ya existe {args.salida}. Usa --forzar para sobrescribir "
              "(perderás la capacidad de renovar las licencias emitidas con la anterior).",
              file=sys.stderr)
        return 1

    priv = Ed25519PrivateKey.generate()
    args.salida.parent.mkdir(parents=True, exist_ok=True)
    args.salida.write_bytes(priv.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ))
    try:
        args.salida.chmod(0o600)
    except OSError:
        pass

    pub_hex = priv.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()

    print(f"Clave privada guardada en: {args.salida}")
    print("  -> guárdala a buen recaudo y haz copia de seguridad.\n")
    print("Pega esto en taller/licencia.py:\n")
    print(f'    CLAVE_PUBLICA_HEX = "{pub_hex}"\n')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
