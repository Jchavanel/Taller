"""Editor de documentos: presupuesto, orden de trabajo, albarán y factura."""
from __future__ import annotations

import datetime as _dt

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .. import domain
from ..repository import Repository
from .dialogs import ClienteDialog, VehiculoDialog

_COLS = ["Tipo", "Código", "Descripción", "Cant.", "Precio", "Dto %", "IVA %", "Importe"]


class DocumentoEditor(QDialog):
    def __init__(self, repo: Repository, parent=None, *, tipo: str | None = None,
                 documento_id: int | None = None) -> None:
        super().__init__(parent)
        self.repo = repo
        self.documento_id = documento_id
        self.saved = False
        self._botones_edicion: list = []

        if documento_id:
            doc = repo.get_documento(documento_id)
            self.tipo = doc["tipo"]
        else:
            self.tipo = tipo or domain.PRESUPUESTO
            doc = None

        bloqueado_doc = bool(doc is not None and repo.documento_bloqueado(doc))
        from .. import licencia
        bloqueo_licencia = not bloqueado_doc and not licencia.puede_operar()
        self.solo_lectura = bloqueado_doc or bloqueo_licencia

        titulo = domain.TIPO_NOMBRE[self.tipo]
        if self.solo_lectura:
            titulo += "  —  SOLO LECTURA"
        self.setWindowTitle(titulo)
        self.resize(920, 680)

        root = QVBoxLayout(self)
        if bloqueo_licencia:
            aviso = QLabel(
                "El programa está en modo consulta (licencia caducada o prueba "
                "terminada). No se pueden crear ni modificar documentos. "
                "Ve a Archivo → Licencia.")
            aviso.setProperty("clase", "aviso")
            aviso.setWordWrap(True)
            root.addWidget(aviso)
        elif self.solo_lectura:
            estado_f = {"anulado": "anulada", "cobrado": "cobrada"}.get(
                doc["estado"], doc["estado"])
            aviso = QLabel(
                f"Esta factura está {estado_f} y no se puede modificar. "
                "Para corregirla, emite una factura rectificativa.")
            aviso.setProperty("clase", "aviso")
            aviso.setWordWrap(True)
            root.addWidget(aviso)
        root.addWidget(self._build_cabecera(doc))
        root.addWidget(self._build_tabla(), stretch=1)
        root.addLayout(self._build_totales())
        root.addWidget(self._build_botones())

        self._cargar_clientes()
        if doc is not None:
            self._cargar_documento(doc)
        else:
            self.fecha.setDate(_dt.date.today())
            self._añadir_linea()
        self._recalcular()

        if self.solo_lectura:
            self._aplicar_solo_lectura()

    def _aplicar_solo_lectura(self) -> None:
        for w in (self.cliente, self.vehiculo, self.estado, self.forma_pago,
                  self.combo_articulo, self.descuento, self.kms, self.validez,
                  self.fecha, self.fecha_entrada, self.entrega_prevista):
            w.setEnabled(False)
        self.observaciones.setReadOnly(True)
        self.tabla.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        for b in self._botones_edicion:
            b.setEnabled(False)

    # ------------------------------------------------------------- cabecera
    def _build_cabecera(self, doc) -> QGroupBox:
        box = QGroupBox("Datos del documento")
        grid = QGridLayout(box)

        self.lbl_numero = QLabel(doc["numero"] if doc else "(se asignará al guardar)")
        self.lbl_numero.setStyleSheet("font-weight: bold;")

        self.fecha = QDateEdit()
        self.fecha.setCalendarPopup(True)
        self.fecha.setDisplayFormat("dd/MM/yyyy")

        self.cliente = QComboBox()
        self.cliente.currentIndexChanged.connect(self._on_cliente_cambiado)
        btn_cli_nuevo = QPushButton("+")
        btn_cli_nuevo.setFixedWidth(30)
        btn_cli_nuevo.setToolTip("Nuevo cliente")
        btn_cli_nuevo.clicked.connect(self._nuevo_cliente)
        cli_row = QHBoxLayout()
        cli_row.addWidget(self.cliente, 1)
        cli_row.addWidget(btn_cli_nuevo)

        self.vehiculo = QComboBox()
        btn_veh_nuevo = QPushButton("+")
        btn_veh_nuevo.setFixedWidth(30)
        btn_veh_nuevo.setToolTip("Nuevo vehículo")
        btn_veh_nuevo.clicked.connect(self._nuevo_vehiculo)
        btn_veh_hist = QPushButton("Historial")
        btn_veh_hist.setToolTip("Ver el historial de trabajos del vehículo")
        btn_veh_hist.clicked.connect(self._ver_historial)
        veh_row = QHBoxLayout()
        veh_row.addWidget(self.vehiculo, 1)
        veh_row.addWidget(btn_veh_nuevo)
        veh_row.addWidget(btn_veh_hist)

        self.kms = QSpinBox()
        self.kms.setRange(0, 9_999_999)
        self.kms.setSpecialValueText(" ")
        self.kms.setSuffix(" km")

        self.estado = QComboBox()
        if self.tipo == domain.FACTURA:
            # una factura está siempre emitida; solo puede pasar a cobrada (queda bloqueada)
            for e in domain.ESTADOS_FACTURA:
                self.estado.addItem(domain.ESTADO_NOMBRE[e], e)
            if doc is not None and doc["estado"] == "anulado":
                self.estado.addItem(domain.ESTADO_NOMBRE["anulado"], "anulado")
            self.estado.setToolTip("Al marcar «Cobrada» y guardar, la factura queda "
                                   "bloqueada y no se podrá modificar.")
        else:
            for e in domain.ESTADOS:
                self.estado.addItem(domain.ESTADO_NOMBRE.get(e, e), e)

        self.forma_pago = QComboBox()
        self.forma_pago.setEditable(True)
        self.forma_pago.addItems(
            ["", "Efectivo", "Tarjeta", "Transferencia", "Bizum", "Domiciliación bancaria"]
        )

        self.fecha_entrada = _date_opcional()
        self.entrega_prevista = _date_opcional()
        self.validez = QSpinBox()
        self.validez.setRange(0, 365)
        self.validez.setSpecialValueText("—")
        self.validez.setSuffix(" días")

        grid.addWidget(QLabel("Número:"), 0, 0)
        grid.addWidget(self.lbl_numero, 0, 1)
        grid.addWidget(QLabel("Fecha:"), 0, 2)
        grid.addWidget(self.fecha, 0, 3)
        grid.addWidget(QLabel("Estado:"), 0, 4)
        grid.addWidget(self.estado, 0, 5)

        grid.addWidget(QLabel("Cliente:"), 1, 0)
        grid.addLayout(cli_row, 1, 1, 1, 3)
        grid.addWidget(QLabel("Kms:"), 1, 4)
        grid.addWidget(self.kms, 1, 5)

        grid.addWidget(QLabel("Vehículo:"), 2, 0)
        grid.addLayout(veh_row, 2, 1, 1, 3)
        grid.addWidget(QLabel("Forma de pago:"), 2, 4)
        grid.addWidget(self.forma_pago, 2, 5)

        grid.addWidget(QLabel("Fecha entrada:"), 3, 0)
        grid.addWidget(self.fecha_entrada, 3, 1)
        grid.addWidget(QLabel("Entrega prevista:"), 3, 2)
        grid.addWidget(self.entrega_prevista, 3, 3)
        self.lbl_validez = QLabel("Validez:")
        grid.addWidget(self.lbl_validez, 3, 4)
        grid.addWidget(self.validez, 3, 5)
        solo_presupuesto = self.tipo == domain.PRESUPUESTO
        self.lbl_validez.setVisible(solo_presupuesto)
        self.validez.setVisible(solo_presupuesto)

        return box

    # -------------------------------------------------------------- tabla
    def _build_tabla(self) -> QWidget:
        cont = QWidget()
        lay = QVBoxLayout(cont)
        lay.setContentsMargins(0, 0, 0, 0)

        barra = QHBoxLayout()
        self.combo_articulo = QComboBox()
        self.combo_articulo.setMinimumWidth(320)
        self._cargar_articulos()
        btn_add_art = QPushButton("Añadir artículo")
        btn_add_art.clicked.connect(self._añadir_desde_articulo)
        btn_add_libre = QPushButton("Añadir línea libre")
        btn_add_libre.clicked.connect(lambda: self._añadir_linea())
        btn_del = QPushButton("Eliminar línea")
        btn_del.clicked.connect(self._eliminar_linea)
        self._botones_edicion.extend([btn_add_art, btn_add_libre, btn_del])
        barra.addWidget(self.combo_articulo)
        barra.addWidget(btn_add_art)
        barra.addWidget(btn_add_libre)
        barra.addStretch(1)
        barra.addWidget(btn_del)
        lay.addLayout(barra)

        cols = list(_COLS)
        cols[6] = f"{self.repo.get_empresa()['impuesto_nombre'] or 'IVA'} %"
        self.tabla = QTableWidget(0, len(cols))
        self.tabla.setHorizontalHeaderLabels(cols)
        # el combo de la columna "Tipo" y el editor de texto de las celdas necesitan
        # menos relleno que el general, para que quepan en la altura de fila
        self.tabla.setStyleSheet(
            "QComboBox { padding: 1px 6px; min-height: 0; border-radius: 5px; }"
            "QTableWidget QLineEdit { padding: 1px 4px; border-radius: 4px; margin: 0; "
            "min-height: 0; }")
        hdr = self.tabla.horizontalHeader()
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        for c in (1, 3, 4, 5, 6, 7):
            hdr.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.tabla.setColumnWidth(0, 120)
        self.tabla.verticalHeader().setDefaultSectionSize(38)
        self.tabla.itemChanged.connect(self._on_item_changed)
        lay.addWidget(self.tabla)
        return cont

    def _build_totales(self) -> QHBoxLayout:
        lay = QHBoxLayout()
        lay.addWidget(QLabel("Descuento general:"))
        self.descuento = QDoubleSpinBox()
        self.descuento.setRange(0, 100)
        self.descuento.setSuffix(" %")
        self.descuento.valueChanged.connect(self._recalcular)
        lay.addWidget(self.descuento)
        lay.addStretch(1)
        self.lbl_totales = QLabel()
        self.lbl_totales.setStyleSheet("font-size: 13px;")
        self.lbl_totales.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        lay.addWidget(self.lbl_totales)
        return lay

    def _build_botones(self) -> QWidget:
        cont = QWidget()
        lay = QHBoxLayout(cont)
        lay.setContentsMargins(0, 0, 0, 0)

        self.observaciones = QPlainTextEdit()
        self.observaciones.setPlaceholderText("Observaciones…")
        self.observaciones.setFixedHeight(56)
        lay.addWidget(self.observaciones, 1)

        botones = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        _save = botones.button(QDialogButtonBox.StandardButton.Save)
        _save.setText("Guardar")
        _save.setProperty("primary", "true")
        botones.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        b_correo = botones.addButton("Guardar y enviar por correo…",
                                     QDialogButtonBox.ButtonRole.ApplyRole)
        b_correo.clicked.connect(self._guardar_y_correo)
        b_imprimir = botones.addButton("Guardar e imprimir…",
                                       QDialogButtonBox.ButtonRole.ApplyRole)
        b_imprimir.clicked.connect(self._guardar_e_imprimir)
        botones.accepted.connect(self._guardar_y_cerrar)
        botones.rejected.connect(self.reject)
        self._botones_edicion.extend([_save, b_correo, b_imprimir])
        lay.addWidget(botones)
        return cont

    # ----------------------------------------------------------- cargar datos
    def _cargar_clientes(self, seleccionar: int | None = None) -> None:
        actual = seleccionar if seleccionar is not None else self.cliente.currentData()
        self.cliente.blockSignals(True)
        self.cliente.clear()
        self.cliente.addItem("— Sin cliente —", None)
        for c in self.repo.list_clientes():
            self.cliente.addItem(c["nombre"], c["id"])
        idx = self.cliente.findData(actual)
        self.cliente.setCurrentIndex(max(idx, 0))
        self.cliente.blockSignals(False)
        self._on_cliente_cambiado()

    def _on_cliente_cambiado(self, *_a) -> None:
        cliente_id = self.cliente.currentData()
        actual_veh = self.vehiculo.currentData()
        self.vehiculo.blockSignals(True)
        self.vehiculo.clear()
        self.vehiculo.addItem("— Sin vehículo —", None)
        if cliente_id:
            for v in self.repo.list_vehiculos(cliente_id=cliente_id):
                etiqueta = " ".join(x for x in [v["matricula"], v["marca"], v["modelo"]] if x)
                self.vehiculo.addItem(etiqueta or f"Vehículo #{v['id']}", v["id"])
        idx = self.vehiculo.findData(actual_veh)
        self.vehiculo.setCurrentIndex(max(idx, 0))
        self.vehiculo.blockSignals(False)

    def _cargar_articulos(self) -> None:
        self.combo_articulo.clear()
        self.combo_articulo.addItem("— Elegir artículo/servicio —", None)
        for a in self.repo.list_articulos():
            precio = domain.formato_moneda(a["precio"])
            self.combo_articulo.addItem(f"{a['descripcion']}  ·  {precio}", a["id"])

    def _cargar_documento(self, doc) -> None:
        self.fecha.setDate(_dt.date.fromisoformat(doc["fecha"]))
        self._cargar_clientes(seleccionar=doc["cliente_id"])
        idx = self.vehiculo.findData(doc["vehiculo_id"])
        if idx >= 0:
            self.vehiculo.setCurrentIndex(idx)
        self.kms.setValue(doc["kms"] or 0)
        _idx_estado = self.estado.findData(doc["estado"])
        self.estado.setCurrentIndex(_idx_estado if _idx_estado >= 0 else 0)
        self.forma_pago.setCurrentText(doc["forma_pago"])
        self.descuento.setValue(doc["descuento_pct"])
        self.observaciones.setPlainText(doc["observaciones"])
        _set_date_opcional(self.fecha_entrada, doc["fecha_entrada"])
        _set_date_opcional(self.entrega_prevista, doc["entrega_prevista"])
        self.validez.setValue(doc["validez_dias"] or 0)
        for ln in self.repo.get_lineas(doc["id"]):
            self._añadir_linea({
                "tipo": ln["tipo"], "codigo": ln["codigo"], "descripcion": ln["descripcion"],
                "cantidad": ln["cantidad"], "precio": ln["precio"],
                "descuento_pct": ln["descuento_pct"], "iva_pct": ln["iva_pct"],
                "es_canon": ("es_canon" in ln.keys() and ln["es_canon"]),
            })

    # -------------------------------------------------------------- líneas
    def _fila_vacia(self, fila: int) -> bool:
        return (not _texto(self.tabla.item(fila, 1))
                and not _texto(self.tabla.item(fila, 2))
                and _numero(self.tabla.item(fila, 3)) in (0, 1)
                and _numero(self.tabla.item(fila, 4)) == 0)

    def _añadir_linea(self, datos: dict | None = None, reutilizar_vacia: bool = False) -> None:
        datos = datos or {}
        self.tabla.blockSignals(True)

        fila = self.tabla.rowCount()
        if (reutilizar_vacia and fila > 0 and self._fila_vacia(fila - 1)
                and self.tabla.cellWidget(fila - 1, 0) is not None):
            fila -= 1  # rellenar la última fila vacía en vez de crear otra
        else:
            self.tabla.insertRow(fila)
            combo = QComboBox()
            for k, v in domain.TIPO_LINEA_NOMBRE.items():
                combo.addItem(v, k)
            combo.currentIndexChanged.connect(self._recalcular)
            self.tabla.setCellWidget(fila, 0, combo)
            importe = QTableWidgetItem("")
            importe.setFlags(Qt.ItemFlag.ItemIsEnabled)
            importe.setTextAlignment(Qt.AlignmentFlag.AlignRight
                                     | Qt.AlignmentFlag.AlignVCenter)
            self.tabla.setItem(fila, 7, importe)

        combo = self.tabla.cellWidget(fila, 0)
        idx = combo.findData(datos.get("tipo", domain.LINEA_MATERIAL))
        combo.setCurrentIndex(max(idx, 0))

        es_canon = bool(datos.get("es_canon"))
        valores = [
            datos.get("codigo", ""),
            datos.get("descripcion", ""),
            _fmt(datos.get("cantidad", 1)),
            _fmt(datos.get("precio", 0)),
            _fmt(datos.get("descuento_pct", 0)),
            _fmt(datos.get("iva_pct", self.repo.iva_defecto())),
        ]
        for col, val in zip(range(1, 7), valores):
            item = QTableWidgetItem(str(val))
            if col >= 3:
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            if es_canon:
                # línea de canon: bloqueada por completo. El importe se cambia en el artículo.
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                item.setForeground(Qt.GlobalColor.gray)
            self.tabla.setItem(fila, col, item)
        if es_canon:
            desc_it = self.tabla.item(fila, 2)
            desc_it.setData(Qt.ItemDataRole.UserRole, "canon")
            desc_it.setToolTip("Impuesto de reciclaje ligado al artículo. Para cambiar el "
                               "importe por unidad, edítalo en el artículo.")
            combo.setEnabled(False)

        self.tabla.blockSignals(False)
        self._recalcular()

    def _es_fila_canon(self, fila: int) -> bool:
        it = self.tabla.item(fila, 2)
        return bool(it and it.data(Qt.ItemDataRole.UserRole) == "canon")

    def _añadir_desde_articulo(self) -> None:
        art_id = self.combo_articulo.currentData()
        if not art_id:
            return
        a = self.repo.get_articulo(art_id)
        self._añadir_linea({
            "tipo": a["tipo"], "codigo": a["codigo"], "descripcion": a["descripcion"],
            "cantidad": 1, "precio": a["precio"], "descuento_pct": 0, "iva_pct": a["iva_pct"],
        }, reutilizar_vacia=True)
        canon = float(a["canon_reciclaje"] or 0) if "canon_reciclaje" in a.keys() else 0.0
        if canon > 0:
            texto = (a["canon_descripcion"] or "").strip() or domain.CANON_DESC_DEFECTO
            self._añadir_linea({
                "tipo": domain.LINEA_MATERIAL, "codigo": "",
                "descripcion": f"{texto} — {a['descripcion']}",
                "cantidad": 1, "precio": canon, "descuento_pct": 0,
                "iva_pct": a["iva_pct"], "es_canon": True,
            })

    def _eliminar_linea(self) -> None:
        fila = self.tabla.currentRow()
        if fila < 0:
            return
        # si justo debajo hay una línea de canon ligada, se quita también
        if (fila + 1 < self.tabla.rowCount() and self._es_fila_canon(fila + 1)
                and not self._es_fila_canon(fila)):
            self.tabla.removeRow(fila + 1)
        self.tabla.removeRow(fila)
        self._recalcular()

    def _on_item_changed(self, _item) -> None:
        self._recalcular()

    # ------------------------------------------------------------- cálculo
    def _leer_lineas(self) -> list[dict]:
        lineas = []
        for fila in range(self.tabla.rowCount()):
            combo = self.tabla.cellWidget(fila, 0)
            lineas.append({
                "tipo": combo.currentData() if combo else domain.LINEA_MATERIAL,
                "codigo": _texto(self.tabla.item(fila, 1)),
                "descripcion": _texto(self.tabla.item(fila, 2)),
                "cantidad": _numero(self.tabla.item(fila, 3)),
                "precio": _numero(self.tabla.item(fila, 4)),
                "descuento_pct": _numero(self.tabla.item(fila, 5)),
                "iva_pct": _numero(self.tabla.item(fila, 6)),
                "es_canon": self._es_fila_canon(fila),
            })
        return lineas

    def _recalcular(self) -> None:
        self.tabla.blockSignals(True)
        # las líneas de canon toman la cantidad de la línea de la que dependen (la de arriba)
        for fila in range(1, self.tabla.rowCount()):
            if self._es_fila_canon(fila) and not self._es_fila_canon(fila - 1):
                padre = _numero(self.tabla.item(fila - 1, 3))
                it = self.tabla.item(fila, 3)
                if it is not None and it.text() != _fmt(padre):
                    it.setText(_fmt(padre))
        calc = []
        for fila in range(self.tabla.rowCount()):
            lc = domain.LineaCalc(
                cantidad=_numero(self.tabla.item(fila, 3)),
                precio=_numero(self.tabla.item(fila, 4)),
                descuento_pct=_numero(self.tabla.item(fila, 5)),
                iva_pct=_numero(self.tabla.item(fila, 6)),
            )
            calc.append(lc)
            self.tabla.item(fila, 7).setText(domain.formato_moneda(lc.base))
        self.tabla.blockSignals(False)

        totales = domain.calcular_totales(calc, self.descuento.value())
        partes = [f"Base: <b>{domain.formato_moneda(totales.base)}</b>"]
        for iva_pct, (_b, cuota) in totales.desglose.items():
            partes.append(f"IVA {_fmt(iva_pct)}%: <b>{domain.formato_moneda(cuota)}</b>")
        partes.append(f"TOTAL: <b>{domain.formato_moneda(totales.total)}</b>")
        self.lbl_totales.setText("&nbsp;&nbsp;|&nbsp;&nbsp;".join(partes))

    # ------------------------------------------------------------- acciones
    def _nuevo_cliente(self) -> None:
        if self.solo_lectura:
            return
        dlg = ClienteDialog(self.repo, self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.result_id:
            self._cargar_clientes(seleccionar=dlg.result_id)

    def _ver_historial(self) -> None:
        vid = self.vehiculo.currentData()
        if not vid:
            QMessageBox.information(self, "Sin vehículo",
                                   "Seleccione un vehículo para ver su historial.")
            return
        from .historial import HistorialDialog
        HistorialDialog(self.repo, self, vehiculo_id=vid).exec()

    def _nuevo_vehiculo(self) -> None:
        if self.solo_lectura:
            return
        cliente_id = self.cliente.currentData()
        if not cliente_id:
            QMessageBox.information(self, "Cliente necesario",
                                   "Seleccione primero un cliente para asignarle el vehículo.")
            return
        dlg = VehiculoDialog(self.repo, self, cliente_id=cliente_id)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.result_id:
            self._on_cliente_cambiado()
            idx = self.vehiculo.findData(dlg.result_id)
            if idx >= 0:
                self.vehiculo.setCurrentIndex(idx)

    def _cabecera(self) -> dict:
        return {
            "tipo": self.tipo,
            "fecha": self.fecha.date().toString("yyyy-MM-dd"),
            "cliente_id": self.cliente.currentData(),
            "vehiculo_id": self.vehiculo.currentData(),
            "kms": self.kms.value() or None,
            "estado": self.estado.currentData() or self.estado.currentText(),
            "descuento_pct": self.descuento.value(),
            "observaciones": self.observaciones.toPlainText().strip(),
            "forma_pago": self.forma_pago.currentText().strip(),
            "fecha_entrada": _get_date_opcional(self.fecha_entrada),
            "entrega_prevista": _get_date_opcional(self.entrega_prevista),
            "validez_dias": self.validez.value() or None,
        }

    def _guardar(self) -> bool:
        if self.solo_lectura:
            return False
        lineas = self._leer_lineas()
        lineas = [ln for ln in lineas if ln["descripcion"] or ln["precio"]]
        if not lineas:
            QMessageBox.warning(self, "Documento vacío",
                                "Añada al menos una línea con descripción o importe.")
            return False
        if self.tipo == domain.FACTURA and not self.cliente.currentData():
            QMessageBox.warning(self, "Cliente obligatorio",
                                "Una factura debe tener un cliente asignado.")
            return False
        cabecera = self._cabecera()
        if (self.tipo == domain.FACTURA and cabecera["estado"] == "cobrado"
                and QMessageBox.question(
                    self, "Marcar como cobrada",
                    "Vas a marcar la factura como COBRADA.\n\n"
                    "Quedará bloqueada: no podrás modificarla después "
                    "(para corregirla habría que emitir una rectificativa).\n\n¿Continuar?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                ) != QMessageBox.StandardButton.Yes):
            return False
        if self.documento_id:
            self.repo.actualizar_documento(self.documento_id, cabecera, lineas)
        else:
            self.documento_id = self.repo.crear_documento(cabecera, lineas)
        self.saved = True
        return True

    def _guardar_y_cerrar(self) -> None:
        if self._guardar():
            self.accept()

    def _pdf_del_documento(self):
        """Guarda y genera el PDF. Devuelve (doc, cliente, vehiculo, ruta) o None."""
        from ..pdf_export import generar_pdf
        from .tabs import _error_pdf
        doc = self.repo.get_documento(self.documento_id)
        cli = self.repo.get_cliente(doc["cliente_id"]) if doc["cliente_id"] else None
        veh = self.repo.get_vehiculo(doc["vehiculo_id"]) if doc["vehiculo_id"] else None
        try:
            ruta = generar_pdf(doc, self.repo.get_lineas(self.documento_id), cli, veh,
                               self.repo.get_empresa())
        except Exception as e:  # noqa: BLE001
            _error_pdf(self, e)
            return None
        return doc, cli, veh, ruta

    def _guardar_e_imprimir(self) -> None:
        if not self._guardar():
            return
        r = self._pdf_del_documento()
        if r is not None:
            from .impresion import previsualizar_e_imprimir
            previsualizar_e_imprimir(self, r[3], r[0]["numero"])
        self.accept()

    def _guardar_y_correo(self) -> None:
        if not self._guardar():
            return
        r = self._pdf_del_documento()
        if r is not None:
            doc, cli, veh, ruta = r
            from .. import email_envio as mail
            from .correo import EnviarCorreoDialog
            ctx = mail.contexto_documento(doc, cli, veh, self.repo.get_empresa())
            EnviarCorreoDialog(
                self.repo, self, pdf=ruta, contexto=ctx,
                destinatario=(cli["email"] if cli and cli["email"] else "")).exec()
        self.accept()


# --------------------------------------------------------------- utilidades
_FECHA_MIN = QDate(2000, 1, 1)


class _FechaOpcional(QDateEdit):
    """QDateEdit opcional: vacío = «— sin fecha —». Al abrir el calendario estando
    vacío, se posiciona en el mes en curso (no en la fecha mínima)."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setCalendarPopup(True)
        self.setDisplayFormat("dd/MM/yyyy")
        self.setMinimumDate(_FECHA_MIN)
        self.setSpecialValueText("— sin fecha —")
        self.setDate(_FECHA_MIN)
        self._cal = self.calendarWidget()
        # el popup del calendario es el padre del QCalendarWidget
        popup = self._cal.parent() if self._cal is not None else None
        (popup or self._cal or self).installEventFilter(self)

    def eventFilter(self, obj, ev) -> bool:  # noqa: N802
        from PySide6.QtCore import QEvent
        if (self._cal is not None and ev.type() == QEvent.Type.Show
                and self.date() == _FECHA_MIN):
            hoy = QDate.currentDate()
            self._cal.setCurrentPage(hoy.year(), hoy.month())
        return super().eventFilter(obj, ev)


def _date_opcional() -> QDateEdit:
    return _FechaOpcional()


def _set_date_opcional(w: QDateEdit, iso: str | None) -> None:
    if iso:
        d = QDate.fromString(str(iso)[:10], "yyyy-MM-dd")
        w.setDate(d if d.isValid() else _FECHA_MIN)
    else:
        w.setDate(_FECHA_MIN)


def _get_date_opcional(w: QDateEdit) -> str | None:
    if w.date() == _FECHA_MIN:
        return None
    return w.date().toString("yyyy-MM-dd")


def _texto(item) -> str:
    return item.text().strip() if item else ""


def _numero(item) -> float:
    if not item:
        return 0.0
    txt = item.text().strip().replace(",", ".").replace("€", "").replace("%", "").strip()
    try:
        return float(txt)
    except ValueError:
        return 0.0


def _fmt(x) -> str:
    try:
        x = float(x)
    except (TypeError, ValueError):
        return "0"
    if x == int(x):
        return str(int(x))
    return f"{x:.2f}".replace(".", ",")
