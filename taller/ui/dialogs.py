"""Diálogos de alta/edición para clientes, vehículos, artículos y datos de empresa."""
from __future__ import annotations

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
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
    QTabWidget,
    QVBoxLayout,
)

from .. import domain
from ..repository import Repository


class _BaseDialog(QDialog):
    def __init__(self, parent=None, titulo="") -> None:
        super().__init__(parent)
        self.setWindowTitle(titulo)
        self.setMinimumWidth(460)
        self._layout = QVBoxLayout(self)
        self.form = QFormLayout()
        self._layout.addLayout(self.form)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        _save = self.buttons.button(QDialogButtonBox.StandardButton.Save)
        _save.setText("Guardar")
        _save.setProperty("primary", "true")
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        self.buttons.accepted.connect(self._on_accept)
        self.buttons.rejected.connect(self.reject)
        self._layout.addWidget(self.buttons)
        self.result_id: int | None = None

    def _on_accept(self) -> None:
        raise NotImplementedError


_COMBUSTIBLES = ["", "Gasolina", "Diésel", "Híbrido", "Eléctrico", "GLP", "GNC"]

_CAMPOS_VEHICULO = ["matricula", "marca", "modelo", "bastidor", "anio",
                    "color", "combustible", "kms", "notas"]


class VehiculoFormDialog(QDialog):
    """Formulario de datos de un vehículo, sin selector de cliente ni acceso a BD.

    Devuelve un diccionario en `self.datos` (conserva la clave 'id' si venía).
    """

    def __init__(self, parent=None, datos: dict | None = None) -> None:
        super().__init__(parent)
        datos = datos or {}
        self.setWindowTitle("Vehículo del cliente")
        self.setMinimumWidth(440)
        self.datos: dict | None = None
        self._id = datos.get("id")

        lay = QVBoxLayout(self)
        form = QFormLayout()
        lay.addLayout(form)

        self.matricula = QLineEdit(str(datos.get("matricula", "") or ""))
        self.marca = QLineEdit(str(datos.get("marca", "") or ""))
        self.modelo = QLineEdit(str(datos.get("modelo", "") or ""))
        self.bastidor = QLineEdit(str(datos.get("bastidor", "") or ""))
        self.anio = QSpinBox()
        self.anio.setRange(0, 2100)
        self.anio.setSpecialValueText(" ")
        self.anio.setValue(int(datos.get("anio") or 0))
        self.color = QLineEdit(str(datos.get("color", "") or ""))
        self.combustible = QComboBox()
        self.combustible.setEditable(True)
        self.combustible.addItems(_COMBUSTIBLES)
        self.combustible.setCurrentText(str(datos.get("combustible", "") or ""))
        self.kms = QSpinBox()
        self.kms.setRange(0, 9_999_999)
        self.kms.setSpecialValueText(" ")
        self.kms.setSuffix(" km")
        self.kms.setValue(int(datos.get("kms") or 0))
        self.notas = QPlainTextEdit(str(datos.get("notas", "") or ""))
        self.notas.setFixedHeight(56)

        form.addRow("Matrícula", self.matricula)
        form.addRow("Marca", self.marca)
        form.addRow("Modelo", self.modelo)
        form.addRow("Bastidor (VIN)", self.bastidor)
        form.addRow("Año", self.anio)
        form.addRow("Color", self.color)
        form.addRow("Combustible", self.combustible)
        form.addRow("Kilómetros", self.kms)
        form.addRow("Notas", self.notas)

        botones = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        botones.button(QDialogButtonBox.StandardButton.Save).setText("Aceptar")
        botones.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        botones.accepted.connect(self._on_accept)
        botones.rejected.connect(self.reject)
        lay.addWidget(botones)

    def _on_accept(self) -> None:
        if not (self.matricula.text().strip() or self.bastidor.text().strip()):
            QMessageBox.warning(self, "Falta un dato",
                                "Indique al menos la matrícula o el bastidor.")
            return
        self.datos = {
            "matricula": self.matricula.text().strip().upper(),
            "marca": self.marca.text().strip(),
            "modelo": self.modelo.text().strip(),
            "bastidor": self.bastidor.text().strip().upper(),
            "anio": self.anio.value() or None,
            "color": self.color.text().strip(),
            "combustible": self.combustible.currentText().strip(),
            "kms": self.kms.value() or None,
            "notas": self.notas.toPlainText().strip(),
        }
        if self._id:
            self.datos["id"] = self._id
        self.accept()


class ClienteDialog(_BaseDialog):
    def __init__(self, repo: Repository, parent=None, cliente_id: int | None = None) -> None:
        super().__init__(parent, "Cliente")
        self.repo = repo
        self.cliente_id = cliente_id
        self._vehiculos: list[dict] = []
        self._eliminar: list[int] = []

        self.nombre = QLineEdit()
        self.nif = QLineEdit()
        self.direccion = QLineEdit()
        self.cp = QLineEdit()
        self.poblacion = QLineEdit()
        self.provincia = QLineEdit()
        self.telefono = QLineEdit()
        self.email = QLineEdit()
        self.notas = QPlainTextEdit()
        self.notas.setFixedHeight(56)

        self.form.addRow("Nombre / Razón social *", self.nombre)
        self.form.addRow("NIF / CIF", self.nif)
        self.form.addRow("Dirección", self.direccion)
        self.form.addRow("Código postal", self.cp)
        self.form.addRow("Población", self.poblacion)
        self.form.addRow("Provincia", self.provincia)
        self.form.addRow("Teléfono", self.telefono)
        self.form.addRow("Email", self.email)
        self.form.addRow("Notas", self.notas)

        self._layout.insertWidget(1, self._build_vehiculos())
        self.setMinimumWidth(560)

        if cliente_id:
            row = repo.get_cliente(cliente_id)
            self.nombre.setText(row["nombre"])
            self.nif.setText(row["nif"])
            self.direccion.setText(row["direccion"])
            self.cp.setText(row["cp"])
            self.poblacion.setText(row["poblacion"])
            self.provincia.setText(row["provincia"])
            self.telefono.setText(row["telefono"])
            self.email.setText(row["email"])
            self.notas.setPlainText(row["notas"])
            for v in repo.list_vehiculos(cliente_id=cliente_id):
                self._vehiculos.append({k: v[k] for k in ("id", *_CAMPOS_VEHICULO)})
            self._refrescar_tabla()

    # ------------------------------------------------------------- vehículos
    def _build_vehiculos(self) -> QGroupBox:
        box = QGroupBox("Vehículos del cliente")
        lay = QVBoxLayout(box)

        self.tabla_veh = QTableWidget(0, 5)
        self.tabla_veh.setHorizontalHeaderLabels(["Matrícula", "Marca", "Modelo", "Año", "Kms"])
        self.tabla_veh.verticalHeader().setVisible(False)
        self.tabla_veh.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla_veh.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla_veh.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tabla_veh.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch
        )
        self.tabla_veh.setFixedHeight(140)
        self.tabla_veh.doubleClicked.connect(self._editar_vehiculo)
        lay.addWidget(self.tabla_veh)

        barra = QHBoxLayout()
        b_add = QPushButton("Añadir vehículo")
        b_add.clicked.connect(self._añadir_vehiculo)
        b_edit = QPushButton("Editar")
        b_edit.clicked.connect(self._editar_vehiculo)
        b_del = QPushButton("Quitar")
        b_del.clicked.connect(self._quitar_vehiculo)
        barra.addWidget(b_add)
        barra.addWidget(b_edit)
        barra.addWidget(b_del)
        barra.addStretch(1)
        lay.addLayout(barra)
        return box

    def _refrescar_tabla(self) -> None:
        self.tabla_veh.setRowCount(len(self._vehiculos))
        for i, v in enumerate(self._vehiculos):
            valores = [v.get("matricula", ""), v.get("marca", ""), v.get("modelo", ""),
                       str(v.get("anio") or ""), str(v.get("kms") or "")]
            for col, val in enumerate(valores):
                item = QTableWidgetItem(val)
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, i)
                self.tabla_veh.setItem(i, col, item)

    def _fila_veh(self) -> int:
        return self.tabla_veh.currentRow()

    def _añadir_vehiculo(self) -> None:
        dlg = VehiculoFormDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.datos:
            self._vehiculos.append(dlg.datos)
            self._refrescar_tabla()

    def _editar_vehiculo(self) -> None:
        fila = self._fila_veh()
        if fila < 0:
            return
        dlg = VehiculoFormDialog(self, datos=self._vehiculos[fila])
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.datos:
            self._vehiculos[fila] = dlg.datos
            self._refrescar_tabla()

    def _quitar_vehiculo(self) -> None:
        fila = self._fila_veh()
        if fila < 0:
            return
        v = self._vehiculos[fila]
        if v.get("id") and self.repo.vehiculo_tiene_documentos(v["id"]):
            QMessageBox.warning(self, "No se puede quitar",
                                "El vehículo tiene documentos asociados.")
            return
        if v.get("id"):
            self._eliminar.append(v["id"])
        self._vehiculos.pop(fila)
        self._refrescar_tabla()

    def _on_accept(self) -> None:
        if not self.nombre.text().strip():
            QMessageBox.warning(self, "Falta un dato", "El nombre del cliente es obligatorio.")
            return
        data = {
            "id": self.cliente_id,
            "nombre": self.nombre.text().strip(),
            "nif": self.nif.text().strip(),
            "direccion": self.direccion.text().strip(),
            "cp": self.cp.text().strip(),
            "poblacion": self.poblacion.text().strip(),
            "provincia": self.provincia.text().strip(),
            "telefono": self.telefono.text().strip(),
            "email": self.email.text().strip(),
            "notas": self.notas.toPlainText().strip(),
        }
        self.result_id = self.repo.guardar_cliente_con_vehiculos(
            data, self._vehiculos, self._eliminar
        )
        self.cliente_id = self.result_id
        self.accept()


class VehiculoDialog(_BaseDialog):
    def __init__(self, repo: Repository, parent=None, vehiculo_id: int | None = None,
                 cliente_id: int | None = None) -> None:
        super().__init__(parent, "Vehículo")
        self.repo = repo
        self.vehiculo_id = vehiculo_id

        self.cliente = QComboBox()
        self._clientes = repo.list_clientes()
        for c in self._clientes:
            self.cliente.addItem(c["nombre"], c["id"])

        self.matricula = QLineEdit()
        self.marca = QLineEdit()
        self.modelo = QLineEdit()
        self.bastidor = QLineEdit()
        self.anio = QSpinBox()
        self.anio.setRange(0, 2100)
        self.anio.setSpecialValueText(" ")
        self.color = QLineEdit()
        self.combustible = QComboBox()
        self.combustible.setEditable(True)
        self.combustible.addItems(["", "Gasolina", "Diésel", "Híbrido", "Eléctrico", "GLP", "GNC"])
        self.kms = QSpinBox()
        self.kms.setRange(0, 9_999_999)
        self.kms.setSpecialValueText(" ")
        self.kms.setSuffix(" km")
        self.notas = QPlainTextEdit()
        self.notas.setFixedHeight(60)

        self.form.addRow("Cliente *", self.cliente)
        self.form.addRow("Matrícula", self.matricula)
        self.form.addRow("Marca", self.marca)
        self.form.addRow("Modelo", self.modelo)
        self.form.addRow("Bastidor (VIN)", self.bastidor)
        self.form.addRow("Año", self.anio)
        self.form.addRow("Color", self.color)
        self.form.addRow("Combustible", self.combustible)
        self.form.addRow("Kilómetros", self.kms)
        self.form.addRow("Notas", self.notas)

        if vehiculo_id:
            row = repo.get_vehiculo(vehiculo_id)
            self._set_combo(self.cliente, row["cliente_id"])
            self.matricula.setText(row["matricula"])
            self.marca.setText(row["marca"])
            self.modelo.setText(row["modelo"])
            self.bastidor.setText(row["bastidor"])
            self.anio.setValue(row["anio"] or 0)
            self.color.setText(row["color"])
            self.combustible.setCurrentText(row["combustible"])
            self.kms.setValue(row["kms"] or 0)
            self.notas.setPlainText(row["notas"])
        elif cliente_id:
            self._set_combo(self.cliente, cliente_id)

    @staticmethod
    def _set_combo(combo: QComboBox, value) -> None:
        idx = combo.findData(value)
        if idx >= 0:
            combo.setCurrentIndex(idx)

    def _on_accept(self) -> None:
        if self.cliente.currentData() is None:
            QMessageBox.warning(self, "Falta un dato",
                                "Debe existir al menos un cliente. Cree primero el cliente.")
            return
        if not (self.matricula.text().strip() or self.bastidor.text().strip()):
            QMessageBox.warning(self, "Falta un dato",
                                "Indique al menos la matrícula o el bastidor.")
            return
        data = {
            "id": self.vehiculo_id,
            "cliente_id": self.cliente.currentData(),
            "matricula": self.matricula.text().strip().upper(),
            "marca": self.marca.text().strip(),
            "modelo": self.modelo.text().strip(),
            "bastidor": self.bastidor.text().strip().upper(),
            "anio": self.anio.value() or None,
            "color": self.color.text().strip(),
            "combustible": self.combustible.currentText().strip(),
            "kms": self.kms.value() or None,
            "notas": self.notas.toPlainText().strip(),
        }
        self.result_id = self.repo.save_vehiculo(data)
        self.accept()


class ArticuloDialog(_BaseDialog):
    def __init__(self, repo: Repository, parent=None, articulo_id: int | None = None) -> None:
        super().__init__(parent, "Artículo / Servicio")
        self.repo = repo
        self.articulo_id = articulo_id

        self.codigo = QLineEdit()
        self.descripcion = QLineEdit()
        self.tipo = QComboBox()
        for k, v in domain.TIPO_LINEA_NOMBRE.items():
            self.tipo.addItem(v, k)
        self.precio = QDoubleSpinBox()
        self.precio.setRange(0, 1_000_000)
        self.precio.setDecimals(2)
        self.precio.setSuffix(" €")
        self.iva = QDoubleSpinBox()
        self.iva.setRange(0, 100)
        self.iva.setDecimals(2)
        self.iva.setSuffix(" %")
        self.iva.setValue(repo.iva_defecto())
        self.activo = QCheckBox("Activo")
        self.activo.setChecked(True)

        self._imp_nombre = repo.get_empresa()["impuesto_nombre"] or "IVA"
        self.lbl_con_imp = QLabel()
        self.lbl_con_imp.setStyleSheet("color:#777;")
        self.precio.valueChanged.connect(self._actualizar_con_imp)
        self.iva.valueChanged.connect(self._actualizar_con_imp)

        self.form.addRow("Código", self.codigo)
        self.form.addRow("Descripción *", self.descripcion)
        self.form.addRow("Tipo", self.tipo)
        self.form.addRow("Precio base (sin impuesto)", self.precio)
        self.form.addRow(self._imp_nombre, self.iva)
        self.form.addRow("Precio con impuesto", self.lbl_con_imp)
        self.form.addRow("", self.activo)

        if articulo_id:
            row = repo.get_articulo(articulo_id)
            self.codigo.setText(row["codigo"])
            self.descripcion.setText(row["descripcion"])
            idx = self.tipo.findData(row["tipo"])
            if idx >= 0:
                self.tipo.setCurrentIndex(idx)
            self.precio.setValue(row["precio"])
            self.iva.setValue(row["iva_pct"])
            self.activo.setChecked(bool(row["activo"]))
        self._actualizar_con_imp()

    def _actualizar_con_imp(self) -> None:
        con = domain.con_impuesto(self.precio.value(), self.iva.value())
        self.lbl_con_imp.setText(
            f"<b>{domain.formato_moneda(con)}</b>  "
            f"({self._imp_nombre} {self.iva.value():g} % incluido)")

    def _on_accept(self) -> None:
        if not self.descripcion.text().strip():
            QMessageBox.warning(self, "Falta un dato", "La descripción es obligatoria.")
            return
        data = {
            "id": self.articulo_id,
            "codigo": self.codigo.text().strip(),
            "descripcion": self.descripcion.text().strip(),
            "tipo": self.tipo.currentData(),
            "precio": self.precio.value(),
            "iva_pct": self.iva.value(),
            "activo": self.activo.isChecked(),
        }
        self.result_id = self.repo.save_articulo(data)
        self.accept()


class EmpresaDialog(_BaseDialog):
    def __init__(self, repo: Repository, parent=None) -> None:
        super().__init__(parent, "Datos de mi taller")
        self.repo = repo
        row = repo.get_empresa()

        self.nombre = QLineEdit(row["nombre"])
        self.nif = QLineEdit(row["nif"])
        self.direccion = QLineEdit(row["direccion"])
        self.cp = QLineEdit(row["cp"])
        self.poblacion = QLineEdit(row["poblacion"])
        self.provincia = QLineEdit(row["provincia"])
        self.telefono = QLineEdit(row["telefono"])
        self.email = QLineEdit(row["email"])
        self.iban = QLineEdit(row["iban"])

        self.impuesto = QComboBox()
        self.impuesto.setEditable(True)
        self.impuesto.addItems(["IVA", "IGIC", "IPSI"])
        self.impuesto.setCurrentText(row["impuesto_nombre"] or "IVA")
        self.iva = QDoubleSpinBox()
        self.iva.setRange(0, 100)
        self.iva.setDecimals(2)
        self.iva.setSuffix(" %")
        self.iva.setValue(row["iva_defecto"])
        imp_row = QHBoxLayout()
        imp_row.addWidget(self.impuesto, 1)
        imp_row.addWidget(QLabel("por defecto:"))
        imp_row.addWidget(self.iva, 1)

        self.anticipo = QDoubleSpinBox()
        self.anticipo.setRange(0, 100)
        self.anticipo.setSuffix(" %")
        self.anticipo.setValue(row["anticipo_pct"])
        self.anticipo.setToolTip("Anticipo que se pide en presupuestos y órdenes. "
                                 "0 = sin bloque de anticipo.")

        self.logo = QLineEdit(row["logo_path"])
        btn_logo = QPushButton("Examinar…")
        btn_logo.clicked.connect(self._elegir_logo)
        logo_row = QHBoxLayout()
        logo_row.addWidget(self.logo)
        logo_row.addWidget(btn_logo)

        self.pie = QPlainTextEdit(row["pie_documento"])
        self.pie.setFixedHeight(48)
        self.pie.setPlaceholderText("Vacío = se compone con los datos del taller")

        self.form.addRow("Nombre del taller *", self.nombre)
        self.form.addRow("NIF / CIF", self.nif)
        self.form.addRow("Dirección", self.direccion)
        self.form.addRow("Código postal", self.cp)
        self.form.addRow("Población", self.poblacion)
        self.form.addRow("Provincia", self.provincia)
        self.form.addRow("Teléfono", self.telefono)
        self.form.addRow("Email", self.email)
        self.form.addRow("IBAN (para facturas)", self.iban)
        self.form.addRow("Impuesto", imp_row)
        self.form.addRow("Anticipo presupuesto/orden", self.anticipo)
        self.form.addRow("Logo", logo_row)
        self.form.addRow("Pie de página", self.pie)

        # --- textos de condiciones por tipo de documento ---
        self.cond = {}
        tabs = QTabWidget()
        for clave, etiqueta in [
            ("cond_presupuesto", "Presupuesto"), ("cond_orden", "Orden"),
            ("cond_albaran", "Albarán"), ("cond_factura", "Factura"),
        ]:
            edit = QPlainTextEdit(row[clave])
            edit.setPlaceholderText("Texto de condiciones que aparece en el documento…")
            self.cond[clave] = edit
            tabs.addTab(edit, etiqueta)
        tabs.setFixedHeight(120)
        self.form.addRow("Textos de condiciones", tabs)

        btn_cond = QPushButton("Restaurar textos por defecto")
        btn_cond.clicked.connect(self._restaurar_condiciones)
        self.form.addRow("", btn_cond)
        self.setMinimumWidth(620)

    def _elegir_logo(self) -> None:
        ruta, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar logo", "", "Imágenes (*.png *.jpg *.jpeg)"
        )
        if ruta:
            self.logo.setText(ruta)

    def _restaurar_condiciones(self) -> None:
        defecto = domain.condiciones_por_defecto(self.anticipo.value() or 50)
        mapa = {
            "cond_presupuesto": domain.PRESUPUESTO, "cond_orden": domain.ORDEN,
            "cond_albaran": domain.ALBARAN, "cond_factura": domain.FACTURA,
        }
        for clave, tipo in mapa.items():
            self.cond[clave].setPlainText(defecto[tipo])

    def _on_accept(self) -> None:
        if not self.nombre.text().strip():
            QMessageBox.warning(self, "Falta un dato", "El nombre del taller es obligatorio.")
            return
        iva_anterior = float(self.repo.get_empresa()["iva_defecto"])
        self.repo.save_empresa({
            "nombre": self.nombre.text().strip(),
            "nif": self.nif.text().strip(),
            "direccion": self.direccion.text().strip(),
            "cp": self.cp.text().strip(),
            "poblacion": self.poblacion.text().strip(),
            "provincia": self.provincia.text().strip(),
            "telefono": self.telefono.text().strip(),
            "email": self.email.text().strip(),
            "iban": self.iban.text().strip(),
            "iva_defecto": self.iva.value(),
            "impuesto_nombre": self.impuesto.currentText().strip() or "IVA",
            "anticipo_pct": self.anticipo.value(),
            "logo_path": self.logo.text().strip(),
            "pie_documento": self.pie.toPlainText().strip(),
            "cond_presupuesto": self.cond["cond_presupuesto"].toPlainText().strip(),
            "cond_orden": self.cond["cond_orden"].toPlainText().strip(),
            "cond_albaran": self.cond["cond_albaran"].toPlainText().strip(),
            "cond_factura": self.cond["cond_factura"].toPlainText().strip(),
        })

        nuevo_iva = self.iva.value()
        if abs(nuevo_iva - iva_anterior) > 0.001:
            pendientes = self.repo.contar_articulos_con_iva_distinto(nuevo_iva)
            imp = self.impuesto.currentText().strip() or "IVA"
            if pendientes and QMessageBox.question(
                self, "Impuesto de los artículos",
                f"Has cambiado el impuesto por defecto a {imp} {nuevo_iva:g}%.\n\n"
                f"Hay {pendientes} artículo(s) con otro tipo. "
                "¿Aplicarles también el nuevo impuesto?",
            ) == QMessageBox.StandardButton.Yes:
                self.repo.aplicar_impuesto_a_articulos(nuevo_iva)
        self.accept()


class IntervencionDialog(_BaseDialog):
    """Alta/edición de una intervención del historial de un vehículo."""

    def __init__(self, repo: Repository, parent=None, *, vehiculo_id: int | None = None,
                 intervencion_id: int | None = None, datos: dict | None = None) -> None:
        super().__init__(parent, "Intervención en el vehículo")
        self.repo = repo
        self.intervencion_id = intervencion_id
        self.vehiculo_id = vehiculo_id

        origen = {}
        if intervencion_id:
            row = repo.get_intervencion(intervencion_id)
            origen = dict(row) if row else {}
            self.vehiculo_id = origen.get("vehiculo_id", self.vehiculo_id)
        elif datos:
            origen = dict(datos)
            self.vehiculo_id = origen.get("vehiculo_id", self.vehiculo_id)

        self.fecha = QDateEdit()
        self.fecha.setCalendarPopup(True)
        self.fecha.setDisplayFormat("dd/MM/yyyy")
        self.fecha.setDate(_qdate(origen.get("fecha")) or QDate.currentDate())

        self.kms = QSpinBox()
        self.kms.setRange(0, 9_999_999)
        self.kms.setSpecialValueText(" ")
        self.kms.setSuffix(" km")
        self.kms.setValue(int(origen.get("kms") or 0))

        self.tipo = QComboBox()
        for k, v in domain.INTERVENCION_TIPOS.items():
            self.tipo.addItem(v, k)
        idx = self.tipo.findData(origen.get("tipo", "reparacion"))
        self.tipo.setCurrentIndex(max(idx, 0))

        self.titulo = QLineEdit(str(origen.get("titulo", "") or ""))
        self.detalle = QPlainTextEdit(str(origen.get("detalle", "") or ""))
        self.detalle.setPlaceholderText("Trabajos realizados, piezas sustituidas, observaciones…")
        self.detalle.setFixedHeight(110)

        self.documento = QComboBox()
        self.documento.addItem("— Sin documento —", None)
        if self.vehiculo_id:
            for d in repo.documentos_de_vehiculo(self.vehiculo_id):
                self.documento.addItem(f"{d['numero']}  ({d['fecha']})", d["id"])
        didx = self.documento.findData(origen.get("documento_id"))
        self.documento.setCurrentIndex(max(didx, 0))
        btn_copiar = QPushButton("Copiar trabajos del documento")
        btn_copiar.clicked.connect(self._copiar_de_documento)
        doc_row = QHBoxLayout()
        doc_row.addWidget(self.documento, 1)
        doc_row.addWidget(btn_copiar)

        self.prox_check = QCheckBox("Programar próxima revisión")
        self.prox_fecha = QDateEdit()
        self.prox_fecha.setCalendarPopup(True)
        self.prox_fecha.setDisplayFormat("dd/MM/yyyy")
        self.prox_fecha.setDate(_qdate(origen.get("prox_fecha")) or QDate.currentDate().addYears(1))
        self.prox_kms = QSpinBox()
        self.prox_kms.setRange(0, 9_999_999)
        self.prox_kms.setSpecialValueText(" ")
        self.prox_kms.setSuffix(" km")
        self.prox_kms.setValue(int(origen.get("prox_kms") or 0))
        tiene_prox = bool(origen.get("prox_fecha") or origen.get("prox_kms"))
        self.prox_check.setChecked(tiene_prox)
        self.prox_check.toggled.connect(self._toggle_prox)
        prox_row = QHBoxLayout()
        prox_row.addWidget(self.prox_fecha)
        prox_row.addWidget(self.prox_kms)

        self.form.addRow("Fecha", self.fecha)
        self.form.addRow("Kilómetros", self.kms)
        self.form.addRow("Tipo", self.tipo)
        self.form.addRow("Título *", self.titulo)
        self.form.addRow("Detalle", self.detalle)
        self.form.addRow("Documento", doc_row)
        self.form.addRow("", self.prox_check)
        self.form.addRow("Próx. revisión (fecha / kms)", prox_row)
        self.setMinimumWidth(560)
        self._toggle_prox(self.prox_check.isChecked())

    def _toggle_prox(self, activo: bool) -> None:
        self.prox_fecha.setEnabled(activo)
        self.prox_kms.setEnabled(activo)

    def _copiar_de_documento(self) -> None:
        doc_id = self.documento.currentData()
        if not doc_id:
            QMessageBox.information(self, "Sin documento",
                                   "Seleccione primero un documento en la lista.")
            return
        datos = self.repo.intervencion_desde_documento(doc_id)
        if not self.titulo.text().strip():
            self.titulo.setText(datos["titulo"])
        texto = self.detalle.toPlainText().strip()
        self.detalle.setPlainText((texto + "\n" if texto else "") + datos["detalle"])
        if datos.get("kms") and not self.kms.value():
            self.kms.setValue(datos["kms"])

    def _on_accept(self) -> None:
        if not self.vehiculo_id:
            QMessageBox.warning(self, "Sin vehículo", "No hay un vehículo asociado.")
            return
        if not self.titulo.text().strip():
            QMessageBox.warning(self, "Falta un dato",
                                "Escriba un título para la intervención "
                                "(p. ej. «Revisión de 90.000 km»).")
            return
        prox_on = self.prox_check.isChecked()
        data = {
            "id": self.intervencion_id,
            "vehiculo_id": self.vehiculo_id,
            "fecha": self.fecha.date().toString("yyyy-MM-dd"),
            "kms": self.kms.value() or None,
            "tipo": self.tipo.currentData(),
            "titulo": self.titulo.text().strip(),
            "detalle": self.detalle.toPlainText().strip(),
            "documento_id": self.documento.currentData(),
            "prox_fecha": self.prox_fecha.date().toString("yyyy-MM-dd") if prox_on else None,
            "prox_kms": (self.prox_kms.value() or None) if prox_on else None,
        }
        self.result_id = self.repo.save_intervencion(data)
        self.accept()


def _qdate(iso: str | None):
    if not iso:
        return None
    d = QDate.fromString(str(iso)[:10], "yyyy-MM-dd")
    return d if d.isValid() else None
