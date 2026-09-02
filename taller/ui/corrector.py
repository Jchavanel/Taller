"""Corrector ortográfico de español para los campos de texto largo.

Subraya en rojo las palabras que no están en el diccionario y ofrece sugerencias con el
botón derecho. **No cambia nada automáticamente.**

Usa el diccionario Hunspell de español (LibreOffice / proyecto RLA, licencia triple
GPL-3 / LGPL-3 / MPL-1.1) incluido en ``taller/resources/diccionario/`` a través de
``spylls`` (Hunspell en Python puro). Si ``spylls`` o el diccionario no están, el campo
funciona como un cuadro de texto normal.
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QSyntaxHighlighter, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QMenu, QPlainTextEdit

from ..errores import log
from ..paths import data_dir

_RECURSOS = Path(__file__).resolve().parent.parent / "resources"
_DICCIONARIO = _RECURSOS / "diccionario" / "index"

_PALABRA = re.compile(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+(?:['\-·][A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+)*")

# Términos de automoción que el diccionario general no trae.
_EXTRA = {
    "silentblock", "silembloc", "bieleta", "homocinética", "homocinéticas", "airbag",
    "airbags", "adblue", "antipinchazos", "caudalímetro", "electroventilador",
    "portalámparas", "bendix", "cardán", "egr", "turbo", "gasoil", "diésel",
    "igic", "ipsi", "itv", "vin", "abs", "esp", "rpm",
    "bosch", "valeo", "sachs", "bilstein", "brembo", "ferodo", "monroe", "ngk", "denso",
    "mahle", "hella", "skf", "gates", "dayco", "contitech", "castrol", "repsol", "cepsa",
    "michelin", "bridgestone", "pirelli", "continental", "goodyear", "hankook",
}

_dic = None
_estado = "sin_cargar"   # "sin_cargar" | "ok" | "no"
_personales: set[str] = set()


def _ruta_personal() -> Path:
    return data_dir() / "diccionario_personal.txt"


def _sin_tildes(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto)
                   if unicodedata.category(c) != "Mn").lower()


def _cargar():
    global _dic, _estado
    if _estado != "sin_cargar":
        return _dic
    try:
        from spylls.hunspell import Dictionary
        _dic = Dictionary.from_files(str(_DICCIONARIO))
        _estado = "ok"
        try:
            for w in _ruta_personal().read_text(encoding="utf-8").splitlines():
                if w.strip():
                    _personales.add(w.strip().lower())
        except OSError:
            pass
    except Exception:  # noqa: BLE001
        log().info("Corrector ortográfico no disponible (falta 'spylls' o el diccionario).")
        _dic, _estado = None, "no"
    return _dic


def disponible() -> bool:
    return _cargar() is not None


def _es_palabra_normal(w: str) -> bool:
    return len(w) >= 3 and not any(c.isdigit() for c in w) and not w.isupper()


def esta_mal(palabra: str) -> bool:
    d = _cargar()
    if d is None or not _es_palabra_normal(palabra):
        return False
    p = palabra.lower()
    if p in _personales or p in _EXTRA:
        return False
    try:
        return not d.lookup(palabra)
    except Exception:  # noqa: BLE001
        return False


def sugerencias(palabra: str, n: int = 7) -> list[str]:
    d = _cargar()
    if d is None:
        return []
    try:
        brutas = list(d.suggest(palabra))
    except Exception:  # noqa: BLE001
        brutas = []
    # las que solo cambian tildes/mayúsculas van primero (p. ej. camion -> camión)
    base = _sin_tildes(palabra)
    orden = {w: i for i, w in enumerate(brutas)}
    brutas.sort(key=lambda w: (_sin_tildes(w) != base, orden[w]))
    vistos, salida = set(), []
    for w in brutas:
        if w.lower() != palabra.lower() and w.lower() not in vistos:
            vistos.add(w.lower())
            salida.append(w)
        if len(salida) >= n:
            break
    return salida


def anadir_personal(palabra: str) -> None:
    palabra = palabra.strip().lower()
    if not palabra:
        return
    _personales.add(palabra)
    try:
        with open(_ruta_personal(), "a", encoding="utf-8") as f:
            f.write(palabra + "\n")
    except OSError:
        pass


class _Resaltador(QSyntaxHighlighter):
    def highlightBlock(self, texto: str) -> None:  # noqa: N802
        if _cargar() is None:
            return
        fmt = QTextCharFormat()
        fmt.setUnderlineColor(Qt.GlobalColor.red)
        fmt.setUnderlineStyle(QTextCharFormat.UnderlineStyle.SpellCheckUnderline)
        for m in _PALABRA.finditer(texto):
            if esta_mal(m.group()):
                self.setFormat(m.start(), len(m.group()), fmt)


class CorrectorTextEdit(QPlainTextEdit):
    """QPlainTextEdit con corrector ortográfico de español (subrayado + sugerencias)."""

    def __init__(self, texto: str = "", parent=None) -> None:
        super().__init__(texto, parent)
        self._resaltador = _Resaltador(self.document())

    def contextMenuEvent(self, evento) -> None:  # noqa: N802
        menu = self.createStandardContextMenu()
        cursor = self.cursorForPosition(evento.pos())
        cursor.select(QTextCursor.SelectionType.WordUnderCursor)
        palabra = cursor.selectedText()

        if esta_mal(palabra):
            ini, fin = cursor.selectionStart(), cursor.selectionEnd()
            sub = QMenu(f"Corregir «{palabra}»", menu)
            sugs = sugerencias(palabra)
            if sugs:
                for sug in sugs:
                    sub.addAction(sug, lambda w=sug: self._reemplazar(ini, fin, w))
            else:
                sub.addAction("(sin sugerencias)").setEnabled(False)
            sub.addSeparator()
            sub.addAction(f"Añadir «{palabra}» al diccionario",
                          lambda: (anadir_personal(palabra),
                                   self._resaltador.rehighlight()))
            primera = menu.actions()[0] if menu.actions() else None
            menu.insertMenu(primera, sub)
            menu.insertSeparator(primera)

        menu.exec(evento.globalPos())

    def _reemplazar(self, ini: int, fin: int, palabra: str) -> None:
        cur = self.textCursor()
        cur.setPosition(ini)
        cur.setPosition(fin, QTextCursor.MoveMode.KeepAnchor)
        cur.insertText(palabra)
