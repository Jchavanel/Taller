#!/usr/bin/env python3
"""Punto de entrada para empaquetar con PyInstaller (equivale a `python -m taller`)."""
from taller.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
