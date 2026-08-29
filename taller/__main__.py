"""Punto de entrada: python -m taller"""
from __future__ import annotations

import sys


def main() -> int:
    try:
        from .ui.main_window import run
    except ModuleNotFoundError as e:
        if e.name and e.name.lower().startswith("pyside6"):
            sys.stderr.write(
                "Falta PySide6. Instala las dependencias con:\n"
                "    pip install -r requirements.txt\n"
            )
            return 1
        raise
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
