"""Corrector ortográfico de español para los campos de texto largo.

Subraya en rojo las palabras que no están en el diccionario y ofrece sugerencias con el
botón derecho. **No cambia nada automáticamente.** Si ``pyspellchecker`` no está
instalado, el campo funciona como un cuadro de texto normal.
"""
from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QSyntaxHighlighter, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QMenu, QPlainTextEdit

from ..errores import log
from ..paths import data_dir

_PALABRA = re.compile(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+(?:['\-·][A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+)*")

# Términos de automoción y marcas frecuentes que el diccionario general no trae.
_EXTRA = {
    "igic", "iva", "ipsi", "itv", "vin", "km", "cv", "rpm", "abs", "esp", "gps",
    "airbag", "turbo", "diésel", "gasoil", "adblue", "antipinchazos",
    "cárter", "retén", "silentblock", "silembloc", "rótula", "bieleta", "amortiguador",
    "distribución", "embrague", "bujía", "bujías", "inyector", "inyectores", "colector",
    "catalizador", "egr", "caudalímetro", "alternador", "bendix", "cardán", "homocinética",
    "palier", "trapecio", "latiguillo", "latiguillos", "calorímetro", "termostato",
    "anticongelante", "refrigerante", "portalámparas", "electroventilador",
    "bosch", "valeo", "sachs", "bilstein", "brembo", "ferodo", "monroe", "ngk", "denso",
    "mahle", "hella", "skf", "gates", "dayco", "contitech", "castrol", "repsol", "cepsa",
    "michelin", "bridgestone", "pirelli", "continental", "goodyear", "hankook",
}

_spell = None
_estado = "sin_cargar"   # "sin_cargar" | "ok" | "no"


def _ruta_personal() -> Path:
    return data_dir() / "diccionario_personal.txt"


def _cargar():
    global _spell, _estado
    if _estado != "sin_cargar":
        return _spell
    try:
        from spellchecker import SpellChecker
        _spell = SpellChecker(language="es", distance=2)
        _spell.word_frequency.load_words(_EXTRA)
        try:
            personales = [w.strip().lower() for w in
                          _ruta_personal().read_text(encoding="utf-8").splitlines()
                          if w.strip()]
            _spell.word_frequency.load_words(personales)
        except OSError:
            pass
        _estado = "ok"
    except Exception:  # noqa: BLE001
        log().info("Corrector ortográfico no disponible (instala 'pyspellchecker').")
        _spell, _estado = None, "no"
    return _spell


def disponible() -> bool:
    return _cargar() is not None


def _es_palabra_normal(w: str) -> bool:
    return len(w) >= 3 and not any(c.isdigit() for c in w) and not w.isupper()


def esta_mal(palabra: str) -> bool:
    s = _cargar()
    if s is None or not _es_palabra_normal(palabra):
        return False
    return palabra.lower() not in s


def sugerencias(palabra: str, n: int = 6) -> list[str]:
    s = _cargar()
    if s is None:
        return []
    base = palabra.lower()
    cand = set(s.candidates(base) or [])
    cand.discard(base)
    ordenadas = sorted(cand, key=lambda w: s.word_frequency[w], reverse=True)[:n]
    if palabra[:1].isupper():
        ordenadas = [w[:1].upper() + w[1:] for w in ordenadas]
    return ordenadas


def anadir_personal(palabra: str) -> None:
    palabra = palabra.strip().lower()
    if not palabra:
        return
    try:
        with open(_ruta_personal(), "a", encoding="utf-8") as f:
            f.write(palabra + "\n")
    except OSError:
        pass
    s = _cargar()
    if s is not None:
        s.word_frequency.add(palabra)


class _Resaltador(QSyntaxHighlighter):
    def highlightBlock(self, texto: str) -> None:  # noqa: N802
        s = _cargar()
        if s is None:
            return
        fmt = QTextCharFormat()
        fmt.setUnderlineColor(Qt.GlobalColor.red)
        fmt.setUnderlineStyle(QTextCharFormat.UnderlineStyle.SpellCheckUnderline)
        for m in _PALABRA.finditer(texto):
            w = m.group()
            if _es_palabra_normal(w) and w.lower() not in s:
                self.setFormat(m.start(), len(w), fmt)


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
