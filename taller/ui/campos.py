"""Campos de texto de la aplicación: mayúscula inicial automática en cada palabra."""
from __future__ import annotations

from PySide6.QtWidgets import QLineEdit

# caracteres tras los que empieza una palabra nueva
_SEPARADORES = set(" \t\n\r-/.,;:()[]'\"·")


def titular(texto: str) -> str:
    """Pone en mayúscula la primera letra de cada palabra. No cambia el resto de
    letras (respeta lo que ha escrito el usuario: siglas, BMW…). No cambia longitud."""
    salida = []
    nueva = True
    for ch in texto:
        if nueva and ch.isalpha():
            salida.append(ch.upper())
            nueva = False
        else:
            salida.append(ch)
        nueva = ch in _SEPARADORES
    return "".join(salida)


class LineaTitulo(QLineEdit):
    """QLineEdit que pone en mayúscula la inicial de cada palabra según se escribe."""

    def __init__(self, texto: str = "", parent=None) -> None:
        super().__init__("", parent)
        self.textEdited.connect(self._al_editar)
        if texto:
            self.setText(texto)

    def _al_editar(self, _texto: str) -> None:
        nuevo = titular(self.text())
        if nuevo != self.text():
            pos = self.cursorPosition()
            self.blockSignals(True)
            super().setText(nuevo)      # misma longitud → el cursor no se descoloca
            self.setCursorPosition(pos)
            self.blockSignals(False)

    def setText(self, texto: str) -> None:  # noqa: N802
        super().setText(titular(texto or ""))
