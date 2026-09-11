"""Campos de texto de la aplicación: mayúscula/minúscula automática al escribir."""
from __future__ import annotations

from PySide6.QtWidgets import QLineEdit

from ..domain import titular  # noqa: F401 - se reexporta: lo usan otros módulos de ui


class LineaTitulo(QLineEdit):
    """QLineEdit que normaliza mayúsculas/minúsculas según se escribe.

    Por defecto deja la inicial de cada palabra en mayúscula y el resto en
    minúscula (:func:`titular`). Con ``mayusculas=True`` (la marca del vehículo)
    lo pone todo en mayúsculas.
    """

    def __init__(self, texto: str = "", parent=None, *, mayusculas: bool = False) -> None:
        super().__init__("", parent)
        self._normalizar = str.upper if mayusculas else titular
        self.textEdited.connect(self._al_editar)
        if texto:
            self.setText(texto)

    def _al_editar(self, _texto: str) -> None:
        nuevo = self._normalizar(self.text())
        if nuevo != self.text():
            pos = self.cursorPosition()
            self.blockSignals(True)
            super().setText(nuevo)      # misma longitud → el cursor no se descoloca
            self.setCursorPosition(pos)
            self.blockSignals(False)

    def setText(self, texto: str) -> None:  # noqa: N802
        super().setText(self._normalizar(texto or ""))
