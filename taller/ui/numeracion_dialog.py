"""Diálogo: fijar desde qué número sigue la numeración de cada tipo de documento.

Útil al empezar a usar el programa cuando el taller ya venía emitiendo documentos con
otro sistema (p. ej. facturas 1..560): se indica que la siguiente factura sea la 561 y el
programa continúa correlativo a partir de ahí.
"""
from __future__ import annotations

import datetime as _dt

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .. import domain


class NumeracionDialog(QDialog):
    def __init__(self, repo, parent=None) -> None:
        super().__init__(parent)
        self.repo = repo
        self.setWindowTitle("Numeración de documentos")
        self.setMinimumWidth(460)

        root = QVBoxLayout(self)
        aviso = QLabel(
            "Indica desde qué número debe seguir cada serie. El programa continúa "
            "correlativo a partir de ahí y, cuando emitas un número mayor, sigue desde "
            "ese último.\n\nNo se puede poner un número igual o inferior a uno ya emitido.")
        aviso.setWordWrap(True)
        root.addWidget(aviso)

        fila_anio = QHBoxLayout()
        fila_anio.addWidget(QLabel("Año:"))
        self.anio = QSpinBox()
        self.anio.setRange(2000, 2100)
        self.anio.setValue(_dt.date.today().year)
        self.anio.valueChanged.connect(self._recargar)
        fila_anio.addWidget(self.anio)
        fila_anio.addStretch(1)
        root.addLayout(fila_anio)

        form = QFormLayout()
        self._spins: dict[str, QSpinBox] = {}
        self._labels: dict[str, QLabel] = {}
        for tipo in domain.TIPOS:
            sp = QSpinBox()
            sp.setRange(1, 9_999_999)
            sp.setGroupSeparatorShown(True)
            lbl = QLabel()
            lbl.setStyleSheet("color: #666;")
            cont = QWidget()
            caja = QHBoxLayout(cont)
            caja.setContentsMargins(0, 0, 0, 0)
            caja.addWidget(sp)
            caja.addWidget(lbl, 1)
            form.addRow(f"{domain.TIPO_NOMBRE[tipo]}  ({domain.TIPO_PREFIJO[tipo]}-…):", cont)
            self._spins[tipo] = sp
            self._labels[tipo] = lbl
        root.addLayout(form)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Save
                              | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self._guardar)
        bb.rejected.connect(self.reject)
        root.addWidget(bb)

        self._recargar()

    def _recargar(self) -> None:
        anio = self.anio.value()
        for tipo, sp in self._spins.items():
            ultimo = self.repo.ultimo_numero(tipo, anio)
            proximo = self.repo.proximo_numero(tipo, anio)
            sp.blockSignals(True)
            sp.setMinimum(max(1, ultimo + 1))
            sp.setValue(proximo)
            sp.blockSignals(False)
            self._labels[tipo].setText(
                f"último emitido: {ultimo}" if ultimo else "sin documentos todavía")

    def _guardar(self) -> None:
        anio = self.anio.value()
        cambios = 0
        try:
            for tipo, sp in self._spins.items():
                natural = self.repo.ultimo_numero(tipo, anio) + 1
                valor = sp.value()
                if valor == natural:
                    self.repo.set_numeracion_inicial(tipo, anio, None)
                else:
                    self.repo.set_numeracion_inicial(tipo, anio, valor)
                    cambios += 1
        except ValueError as e:
            QMessageBox.warning(self, "Numeración", str(e))
            self._recargar()
            return
        QMessageBox.information(
            self, "Numeración",
            "Numeración guardada." if cambios else "No había nada que cambiar.")
        self.accept()
