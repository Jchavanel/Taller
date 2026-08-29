"""Historial de intervenciones y trabajos realizados a un vehículo."""
from __future__ import annotations

import datetime as _dt

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from .. import domain
from ..pdf_export import generar_historial_vehiculo
from ..repository import Repository
from .dialogs import IntervencionDialog


def _fecha_es(iso: str) -> str:
    try:
        return _dt.date.fromisoformat(iso).strftime("%d/%m/%Y")
    except (ValueError, TypeError):
        return iso or ""


def _km(v) -> str:
    return f"{v:,}".replace(",", ".") + " km" if v else "—"


class HistorialDialog(QDialog):
    _COLS = ["Fecha", "Kms", "Tipo", "Intervención", "Origen"]

    def __init__(self, repo: Repository, parent=None, *, vehiculo_id: int) -> None:
        super().__init__(parent)
        self.repo = repo
        self.vehiculo_id = vehiculo_id
        self._abrir_documento_cb = None  # lo fija quien crea el diálogo (opcional)

        veh = repo.get_vehiculo(vehiculo_id)
        desc = " ".join(x for x in [veh["marca"], veh["modelo"]] if x)
        self.setWindowTitle(f"Historial · {veh['matricula'] or desc or 'vehículo'}")
        self.resize(860, 560)

        root = QVBoxLayout(self)

        cab = QLabel(
            f"<b>{veh['matricula'] or '—'}</b>  ·  {desc or 'Vehículo'}"
            + (f"  ·  Bastidor {veh['bastidor']}" if veh["bastidor"] else "")
            + f"  ·  Cliente: {veh['cliente_nombre']}"
        )
        cab.setTextFormat(Qt.TextFormat.RichText)
        root.addWidget(cab)

        self.aviso = QLabel()
        self.aviso.setProperty("clase", "aviso")
        self.aviso.setVisible(False)
        root.addWidget(self.aviso)

        self.tabla = QTableWidget(0, len(self._COLS))
        self.tabla.setHorizontalHeaderLabels(self._COLS)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tabla.setWordWrap(True)
        self.tabla.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.tabla.doubleClicked.connect(self._editar)
        root.addWidget(self.tabla, 1)

        barra = QHBoxLayout()
        b_nueva = QPushButton("Nueva intervención")
        b_nueva.clicked.connect(self._nueva)
        self.b_editar = QPushButton("Editar / ver")
        self.b_editar.clicked.connect(self._editar)
        self.b_eliminar = QPushButton("Eliminar")
        self.b_eliminar.clicked.connect(self._eliminar)
        b_pdf = QPushButton("Imprimir historial…")
        b_pdf.clicked.connect(self._pdf)
        for b in (b_nueva, self.b_editar, self.b_eliminar, b_pdf):
            barra.addWidget(b)
        barra.addStretch(1)
        cerrar = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        cerrar.rejected.connect(self.reject)
        cerrar.button(QDialogButtonBox.StandardButton.Close).setText("Cerrar")
        barra.addWidget(cerrar)
        root.addLayout(barra)

        self._recargar()

    # ------------------------------------------------------------------ datos
    def _recargar(self) -> None:
        self._eventos = self.repo.historial_vehiculo(self.vehiculo_id)
        self.tabla.setRowCount(len(self._eventos))
        for i, ev in enumerate(self._eventos):
            intervencion = ev["titulo"]
            if ev["detalle"]:
                intervencion += "\n" + ev["detalle"]
            if ev.get("total") is not None:
                intervencion += f"\nTotal: {domain.formato_moneda(ev['total'])}"
            prox = self._texto_proxima(ev)
            if prox:
                intervencion += f"\n» Próxima revisión: {prox}"
            origen = "Manual" if ev["origen"] == "intervencion" else (
                ev["documento_numero"] or domain.TIPO_NOMBRE.get(ev["tipo"], ""))
            valores = [_fecha_es(ev["fecha"]), _km(ev["kms"]), ev["tipo_nombre"],
                       intervencion, origen]
            for col, val in enumerate(valores):
                item = QTableWidgetItem(val)
                item.setData(Qt.ItemDataRole.UserRole, i)
                if col in (1,):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight
                                          | Qt.AlignmentFlag.AlignVCenter)
                self.tabla.setItem(i, col, item)
        self.tabla.resizeRowsToContents()
        self._actualizar_aviso()

    def _texto_proxima(self, ev: dict) -> str:
        partes = []
        if ev.get("prox_fecha"):
            partes.append(_fecha_es(ev["prox_fecha"]))
        if ev.get("prox_kms"):
            partes.append(_km(ev["prox_kms"]))
        return " o ".join(partes)

    def _actualizar_aviso(self) -> None:
        prox = self.repo.proxima_revision(self.vehiculo_id)
        if not prox:
            self.aviso.setVisible(False)
            return
        partes = []
        if prox["prox_fecha"]:
            partes.append(f"fecha {_fecha_es(prox['prox_fecha'])}")
        if prox["prox_kms"]:
            partes.append(_km(prox["prox_kms"]))
        self.aviso.setText("Próxima revisión programada: " + " o ".join(partes))
        self.aviso.setVisible(True)

    def _evento_sel(self) -> dict | None:
        fila = self.tabla.currentRow()
        if fila < 0 or fila >= len(self._eventos):
            return None
        return self._eventos[fila]

    # --------------------------------------------------------------- acciones
    def _nueva(self) -> None:
        dlg = IntervencionDialog(self.repo, self, vehiculo_id=self.vehiculo_id)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._recargar()

    def _editar(self) -> None:
        ev = self._evento_sel()
        if ev is None:
            return
        if ev["origen"] == "intervencion":
            dlg = IntervencionDialog(self.repo, self, intervencion_id=ev["id"])
            if dlg.exec() == QDialog.DialogCode.Accepted:
                self._recargar()
        else:
            # Fila procedente de un documento: ofrecer registrarla como intervención.
            if QMessageBox.question(
                self, "Registrar en el historial",
                f"«{ev['titulo']}» procede de un documento.\n\n"
                "¿Quieres crear una intervención en el historial a partir de él "
                "(podrás editar el texto y añadir la próxima revisión)?",
            ) == QMessageBox.StandardButton.Yes:
                datos = self.repo.intervencion_desde_documento(ev["documento_id"])
                dlg = IntervencionDialog(self.repo, self, vehiculo_id=self.vehiculo_id,
                                         datos=datos)
                if dlg.exec() == QDialog.DialogCode.Accepted:
                    self._recargar()

    def _eliminar(self) -> None:
        ev = self._evento_sel()
        if ev is None:
            return
        if ev["origen"] != "intervencion":
            QMessageBox.information(
                self, "No editable",
                "Esta fila procede de un documento (orden o factura). Para quitarla del "
                "historial, edita o elimina el documento en la pestaña Documentos.",
            )
            return
        if QMessageBox.question(self, "Eliminar", "¿Eliminar esta intervención del historial?") \
                == QMessageBox.StandardButton.Yes:
            self.repo.delete_intervencion(ev["id"])
            self._recargar()

    def _pdf(self) -> None:
        veh = self.repo.get_vehiculo(self.vehiculo_id)
        cliente = self.repo.get_cliente(veh["cliente_id"])
        from .impresion import previsualizar_e_imprimir
        from .tabs import _error_pdf
        try:
            ruta = generar_historial_vehiculo(
                veh, cliente, self._eventos, self.repo.get_empresa()
            )
        except Exception as e:  # noqa: BLE001
            _error_pdf(self, e)
            return
        previsualizar_e_imprimir(self, ruta, f"Historial {veh['matricula'] or ''}".strip())
