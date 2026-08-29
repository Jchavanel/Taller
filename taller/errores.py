"""Registro de errores y captura global de excepciones.

Objetivo: que un fallo inesperado NO cierre la aplicación. Se registra en
``datos/registro.log`` y se avisa al usuario, pero la app sigue en marcha.
"""
from __future__ import annotations

import logging
import logging.handlers
import sys
import traceback
from types import TracebackType

from .paths import data_dir

_log = logging.getLogger("taller")
_configurado = False


def configurar_logging() -> None:
    global _configurado
    if _configurado:
        return
    _configurado = True

    fichero = data_dir() / "registro.log"
    handler = logging.handlers.RotatingFileHandler(
        fichero, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter(
        "%(asctime)s  %(levelname)-7s  %(name)s: %(message)s"
    ))
    _log.setLevel(logging.INFO)
    _log.addHandler(handler)
    if sys.stderr:
        _log.addHandler(logging.StreamHandler(sys.stderr))
    _log.info("=== Inicio de sesión ===")


def log() -> logging.Logger:
    return _log


def _mostrar_dialogo(texto: str) -> None:
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox

        if QApplication.instance() is None:
            return
        box = QMessageBox()
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Se ha producido un error")
        box.setText(
            "La aplicación ha encontrado un problema, pero puede seguir usándose.\n\n"
            "El error se ha guardado en el registro. Si se repite, envía el fichero\n"
            f"{data_dir() / 'registro.log'}"
        )
        box.setDetailedText(texto)
        box.exec()
    except Exception:  # noqa: BLE001 - nunca dejar que el manejador de errores falle
        pass


def instalar_excepthook() -> None:
    """Sustituye ``sys.excepthook`` para que las excepciones no aborten la app."""
    configurar_logging()
    vistos: dict[str, int] = {}

    def _hook(tipo: type[BaseException], valor: BaseException,
              tb: TracebackType | None) -> None:
        if issubclass(tipo, KeyboardInterrupt):
            sys.__excepthook__(tipo, valor, tb)
            return
        texto = "".join(traceback.format_exception(tipo, valor, tb))
        _log.error("Excepción no controlada:\n%s", texto)
        # evita una tormenta de diálogos si el mismo error se repite
        clave = f"{tipo.__name__}:{tb.tb_lineno if tb else 0}"
        vistos[clave] = vistos.get(clave, 0) + 1
        if vistos[clave] <= 3:
            _mostrar_dialogo(texto)

    sys.excepthook = _hook

    # PySide6: encaminar también las excepciones de los slots a sys.excepthook.
    try:
        import PySide6.QtCore as _qtcore

        if hasattr(_qtcore, "qInstallMessageHandler"):
            pass  # los mensajes de Qt ya van a stderr
    except Exception:  # noqa: BLE001
        pass
