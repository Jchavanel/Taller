"""Pestañas principales: clientes, vehículos, artículos y documentos."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QColor, QTextCharFormat
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCalendarWidget,
    QComboBox,
    QDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .. import domain
from .. import licencia as _lic
from ..pdf_export import generar_ficha_cliente, generar_pdf
from ..repository import Repository
from .dialogs import (
    ArticuloDialog,
    ClienteDialog,
    IntervencionDialog,
    VehiculoDialog,
    VehiculoFormDialog,
)
from .documento_editor import DocumentoEditor
from .historial import HistorialDialog
from .impresion import previsualizar_e_imprimir


def _exe_de_comando(cmd: str) -> str:
    """Extrae la ruta del ejecutable de una cadena de comando del registro."""
    cmd = (cmd or "").strip()
    if cmd.startswith('"'):
        return cmd[1:].split('"', 1)[0]
    return cmd.split(" ", 1)[0]


def _windows_tiene_visor_pdf() -> bool:
    """True si hay una aplicación asociada a .pdf y su ejecutable existe realmente."""
    import winreg

    progids: list[str] = []
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts\.pdf\UserChoice",
        ) as k:
            progids.append(winreg.QueryValueEx(k, "ProgId")[0])
    except OSError:
        pass
    try:
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, ".pdf") as k:
            progids.append(winreg.QueryValueEx(k, "")[0])
    except OSError:
        pass

    for progid in progids:
        if not progid:
            continue
        for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_CLASSES_ROOT):
            sub = (rf"Software\Classes\{progid}\shell\open\command"
                   if hive == winreg.HKEY_CURRENT_USER
                   else rf"{progid}\shell\open\command")
            try:
                with winreg.OpenKey(hive, sub) as k:
                    exe = _exe_de_comando(winreg.QueryValueEx(k, "")[0])
            except OSError:
                continue
            if not exe:
                continue
            exe = os.path.expandvars(exe)
            # comando sin ruta (activación de paquete/AppX) -> se asume válido
            if os.sep not in exe and "/" not in exe:
                return True
            if os.path.isfile(exe):
                return True
    return False


def _mostrar_en_carpeta(ruta: Path) -> bool:
    """Abre el explorador de archivos en la carpeta del documento."""
    ruta = Path(ruta)
    try:
        if sys.platform.startswith("win"):
            subprocess.Popen(["explorer", f"/select,{ruta}"])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", str(ruta)])
        else:
            subprocess.Popen(["xdg-open", str(ruta.parent)])
        return True
    except (OSError, ValueError):
        return False


def _lanzar(ruta: Path) -> bool:
    try:
        if sys.platform.startswith("win"):
            os.startfile(str(ruta))  # type: ignore[attr-defined]  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(ruta)])
        else:
            subprocess.Popen(["xdg-open", str(ruta)])
        return True
    except OSError:
        return False


def _abrir_ruta(ruta: Path) -> str:
    """Intenta abrir un fichero/carpeta. Devuelve 'archivo', 'carpeta' o 'no'."""
    ruta = Path(ruta)
    if not ruta.exists():
        return "no"
    if ruta.is_dir():
        return "archivo" if _lanzar(ruta) else "no"
    sin_visor = (ruta.suffix.lower() == ".pdf" and sys.platform.startswith("win")
                 and not _windows_tiene_visor_pdf())
    if not sin_visor and _lanzar(ruta):
        return "archivo"
    return "carpeta" if _mostrar_en_carpeta(ruta) else "no"


def _abrir_fichero(ruta: Path) -> bool:
    """Abre un fichero o carpeta con la aplicación predeterminada. True si lanzó algo."""
    return _abrir_ruta(ruta) != "no"


def _error_pdf(parent, exc: Exception) -> None:
    """Muestra un error de generación de PDF con el detalle técnico plegado."""
    import traceback
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Critical)
    box.setWindowTitle("Error al generar el PDF")
    box.setText("No se ha podido generar el PDF.")
    box.setInformativeText(str(exc) or exc.__class__.__name__)
    box.setDetailedText("".join(traceback.format_exception(exc)))
    box.exec()


def _entregar_pdf(parent, ruta: Path) -> None:
    """Abre el PDF generado; si no se puede, informa de dónde está y ofrece la carpeta."""
    ruta = Path(ruta)
    resultado = _abrir_ruta(ruta)
    if resultado == "archivo":
        try:
            parent.window().statusBar().showMessage(f"PDF generado: {ruta}", 8000)
        except (AttributeError, RuntimeError):
            pass
        return

    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Information)
    box.setWindowTitle("PDF generado")
    box.setText(f"El documento se ha guardado correctamente en:\n\n{ruta}")
    if resultado == "carpeta":
        box.setInformativeText(
            "No se ha podido abrir con un lector de PDF (puede que no haya ninguno "
            "asociado a los archivos .pdf en este equipo). Se ha abierto la carpeta "
            "que contiene el documento."
        )
    else:
        box.setInformativeText("Ábralo desde esa ubicación con tu lector de PDF.")
    btn_carpeta = box.addButton("Abrir carpeta", QMessageBox.ButtonRole.ActionRole)
    box.addButton("Cerrar", QMessageBox.ButtonRole.RejectRole)
    box.exec()
    if box.clickedButton() is btn_carpeta:
        _mostrar_en_carpeta(ruta)


def _config_columnas(tabla: QTableWidget, columnas: list[str],
                     expandibles: tuple[int, ...] | None) -> None:
    """Ajusta las columnas: las expandibles se estiran, el resto ancho fijo cómodo.

    Se evita ``ResizeToContents`` porque recorre todas las filas en cada cambio
    (lento con miles de registros).
    """
    anchos = {
        "Fecha": 95, "Estado": 95, "Total": 100, "Año": 60, "Kms": 80,
        "Teléfono": 120, "Precio": 100, "Activo": 65, "NIF/CIF": 110,
        "Número": 120, "Matrícula": 100, "Código": 90, "Tipo": 110,
    }
    hdr = tabla.horizontalHeader()
    if expandibles is None:
        expandibles = (len(columnas) - 1,) if columnas else ()
    hdr.setMinimumSectionSize(52)
    for i, nombre in enumerate(columnas):
        if i in expandibles:
            hdr.setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch)
        else:
            hdr.setSectionResizeMode(i, QHeaderView.ResizeMode.Interactive)
            ancho = 80 if nombre.endswith("%") else anchos.get(nombre, 115)
            hdr.resizeSection(i, ancho)
    hdr.setStretchLastSection(False)


class _TablaBase(QWidget):
    """Estructura común: barra de búsqueda + botones + tabla."""

    columnas: list[str] = []
    # Índice(s) de columna que se estiran para llenar el ancho. Si es None, la última.
    columnas_expandibles: tuple[int, ...] | None = None

    def __init__(self, repo: Repository, parent=None) -> None:
        super().__init__(parent)
        self.repo = repo
        # widgets/acciones que crean o modifican datos; se desactivan sin licencia
        self._acciones_edicion: list = []

        root = QVBoxLayout(self)
        barra = QHBoxLayout()
        self.busqueda = QLineEdit()
        self.busqueda.setPlaceholderText("Buscar…")
        self.busqueda.textChanged.connect(self.refrescar)
        barra.addWidget(self.busqueda, 1)
        self._añadir_botones(barra)
        root.addLayout(barra)

        self.tabla = QTableWidget(0, len(self.columnas))
        self.tabla.setHorizontalHeaderLabels(self.columnas)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.setWordWrap(False)
        self.tabla.doubleClicked.connect(lambda: self._doble_clic())
        _config_columnas(self.tabla, self.columnas, self.columnas_expandibles)
        root.addWidget(self.tabla)

    def _añadir_botones(self, barra: QHBoxLayout) -> None:
        b_nuevo = QPushButton("Nuevo")
        b_nuevo.clicked.connect(self.nuevo)
        b_editar = QPushButton("Editar")
        b_editar.clicked.connect(self.editar)
        b_borrar = QPushButton("Eliminar")
        b_borrar.clicked.connect(self.eliminar)
        for b in (b_nuevo, b_editar, b_borrar):
            barra.addWidget(b)
        self._acciones_edicion += [b_nuevo, b_editar, b_borrar]

    def bloquear_edicion(self, bloq: bool) -> None:
        for w in self._acciones_edicion:
            w.setEnabled(not bloq)

    def _id_seleccionado(self) -> int | None:
        fila = self.tabla.currentRow()
        if fila < 0:
            return None
        item = self.tabla.item(fila, 0)
        return int(item.data(Qt.ItemDataRole.UserRole)) if item else None

    def _set_fila(self, fila: int, obj_id: int, valores: list[str]) -> None:
        for col, val in enumerate(valores):
            item = QTableWidgetItem(val)
            if col == 0:
                item.setData(Qt.ItemDataRole.UserRole, obj_id)
            self.tabla.setItem(fila, col, item)

    def _doble_clic(self) -> None:
        """Acción al hacer doble clic en una fila (por defecto, editar)."""
        if not _lic.exigir_operar(self):
            return
        self.editar()

    # métodos a implementar
    def refrescar(self) -> None: ...
    def nuevo(self) -> None: ...
    def editar(self) -> None: ...
    def eliminar(self) -> None: ...


class ClientesTab(QWidget):
    """Vista maestro-detalle: lista de clientes a la izquierda, ficha completa a la derecha."""

    _VEH_COLS = ["Matrícula", "Marca", "Modelo", "Bastidor", "Año", "Kms", "Combustible"]

    def __init__(self, repo: Repository, parent=None) -> None:
        super().__init__(parent)
        self.repo = repo
        self._cliente_id: int | None = None
        self._bloqueo_licencia = False

        root = QVBoxLayout(self)
        barra = QHBoxLayout()
        self.busqueda = QLineEdit()
        self.busqueda.setPlaceholderText("Buscar cliente por nombre, NIF o teléfono…")
        self.busqueda.textChanged.connect(self.refrescar)
        self._b_cli_nuevo = QPushButton("Nuevo cliente")
        self._b_cli_nuevo.setProperty("primary", "true")
        self._b_cli_nuevo.clicked.connect(self.nuevo)
        self._b_cli_borrar = QPushButton("Eliminar cliente")
        self._b_cli_borrar.clicked.connect(self.eliminar)
        barra.addWidget(self.busqueda, 1)
        barra.addWidget(self._b_cli_nuevo)
        barra.addWidget(self._b_cli_borrar)
        root.addLayout(barra)

        split = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(split, 1)

        self.lista = QTableWidget(0, 2)
        self.lista.setHorizontalHeaderLabels(["Cliente", "Teléfono"])
        self.lista.verticalHeader().setVisible(False)
        self.lista.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.lista.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.lista.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.lista.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.lista.itemSelectionChanged.connect(self._on_seleccion)
        self.lista.doubleClicked.connect(self._editar_cliente)
        split.addWidget(self.lista)

        split.addWidget(self._build_ficha())
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 2)
        split.setSizes([320, 640])

        self.refrescar()

    # --------------------------------------------------------------- ficha
    def _build_ficha(self) -> QWidget:
        cont = QWidget()
        lay = QVBoxLayout(cont)

        self.f_nombre = QLabel("—")
        self.f_nombre.setStyleSheet("font-size: 16px; font-weight: bold;")
        lay.addWidget(self.f_nombre)

        self.f_datos = QLabel()
        self.f_datos.setTextFormat(Qt.TextFormat.RichText)
        self.f_datos.setWordWrap(True)
        self.f_datos.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(self.f_datos)

        self.f_notas = QLabel()
        self.f_notas.setWordWrap(True)
        self.f_notas.setStyleSheet("color: #555; font-style: italic;")
        lay.addWidget(self.f_notas)

        linea = QFrame()
        linea.setFrameShape(QFrame.Shape.HLine)
        lay.addWidget(linea)

        self.grupo_veh = QGroupBox("Vehículos")
        gl = QVBoxLayout(self.grupo_veh)
        self.tabla_veh = QTableWidget(0, len(self._VEH_COLS))
        self.tabla_veh.setHorizontalHeaderLabels(self._VEH_COLS)
        self.tabla_veh.verticalHeader().setVisible(False)
        self.tabla_veh.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla_veh.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla_veh.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tabla_veh.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        # Alta y edición de vehículos se hacen con los botones de abajo; el doble clic
        # abre el historial (qué se le ha hecho al coche), que es lo que se consulta más.
        self.tabla_veh.doubleClicked.connect(self._historial_vehiculo)
        gl.addWidget(self.tabla_veh)

        veh_barra = QHBoxLayout()
        self.b_veh_hist = QPushButton("Historial del vehículo")
        self.b_veh_hist.setProperty("primary", "true")
        self.b_veh_hist.setToolTip("Intervenciones y trabajos hechos a este vehículo "
                                   "(doble clic en la fila)")
        self.b_veh_hist.clicked.connect(self._historial_vehiculo)
        self.b_veh_add = QPushButton("Añadir vehículo")
        self.b_veh_add.clicked.connect(self._añadir_vehiculo)
        self.b_veh_edit = QPushButton("Editar vehículo")
        self.b_veh_edit.clicked.connect(self._editar_vehiculo)
        self.b_veh_del = QPushButton("Quitar vehículo")
        self.b_veh_del.clicked.connect(self._quitar_vehiculo)
        for b in (self.b_veh_hist, self.b_veh_add, self.b_veh_edit, self.b_veh_del):
            veh_barra.addWidget(b)
        veh_barra.addStretch(1)
        gl.addLayout(veh_barra)
        lay.addWidget(self.grupo_veh, 1)

        acc = QHBoxLayout()
        self.b_editar = QPushButton("Editar datos del cliente")
        self.b_editar.clicked.connect(self._editar_cliente)
        self.b_ficha = QPushButton("Imprimir ficha…")
        self.b_ficha.clicked.connect(self._imprimir_ficha)
        acc.addWidget(self.b_editar)
        acc.addWidget(self.b_ficha)
        acc.addStretch(1)
        lay.addLayout(acc)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(cont)
        self._habilitar_ficha(False)
        return scroll

    def _habilitar_ficha(self, activo: bool) -> None:
        for w in (self.grupo_veh, self.b_editar, self.b_ficha):
            w.setEnabled(activo)
        if activo and self._bloqueo_licencia:
            for w in (self.b_editar, self.b_veh_add, self.b_veh_edit, self.b_veh_del):
                w.setEnabled(False)

    def bloquear_edicion(self, bloq: bool) -> None:
        self._bloqueo_licencia = bloq
        self._b_cli_nuevo.setEnabled(not bloq)
        self._b_cli_borrar.setEnabled(not bloq)
        self._mostrar_ficha()  # re-aplica el estado de los botones de la ficha

    # ----------------------------------------------------------- selección
    def _fila_cliente_id(self) -> int | None:
        fila = self.lista.currentRow()
        if fila < 0:
            return None
        item = self.lista.item(fila, 0)
        return int(item.data(Qt.ItemDataRole.UserRole)) if item else None

    def _on_seleccion(self) -> None:
        self._cliente_id = self._fila_cliente_id()
        self._mostrar_ficha()

    def _mostrar_ficha(self) -> None:
        if self._cliente_id is None:
            self.f_nombre.setText("Seleccione un cliente")
            self.f_datos.clear()
            self.f_notas.clear()
            self.tabla_veh.setRowCount(0)
            self._habilitar_ficha(False)
            return
        c = self.repo.get_cliente(self._cliente_id)
        if c is None:
            return
        self.f_nombre.setText(c["nombre"])

        pob = " ".join(x for x in [c["cp"], c["poblacion"]] if x)
        if c["provincia"]:
            pob = f"{pob} ({c['provincia']})" if pob else c["provincia"]
        docs = self.repo.contar_documentos_cliente(self._cliente_id)
        resumen = "  ·  ".join(
            f"{domain.TIPO_NOMBRE[t]}: {docs[t]['n']}" for t in domain.TIPOS if t in docs
        )
        filas = [
            ("NIF / CIF", c["nif"]),
            ("Dirección", c["direccion"]),
            ("Población", pob),
            ("Teléfono", c["telefono"]),
            ("Email", c["email"]),
        ]
        html = "<table cellspacing='4'>"
        for etiqueta, valor in filas:
            if valor:
                html += (f"<tr><td style='color:#666'>{etiqueta}:&nbsp;&nbsp;</td>"
                         f"<td><b>{valor}</b></td></tr>")
        if resumen:
            html += (f"<tr><td style='color:#666'>Documentos:&nbsp;&nbsp;</td>"
                     f"<td>{resumen}</td></tr>")
        html += "</table>"
        self.f_datos.setText(html)
        self.f_notas.setText(f"Notas: {c['notas']}" if c["notas"] else "")

        vehiculos = self.repo.list_vehiculos(cliente_id=self._cliente_id)
        self.grupo_veh.setTitle(f"Vehículos ({len(vehiculos)})")
        self.tabla_veh.setRowCount(len(vehiculos))
        for i, v in enumerate(vehiculos):
            valores = [v["matricula"], v["marca"], v["modelo"], v["bastidor"],
                       str(v["anio"] or ""), f"{v['kms']:,}".replace(",", ".") if v["kms"] else "",
                       v["combustible"]]
            for col, val in enumerate(valores):
                item = QTableWidgetItem(val)
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, v["id"])
                self.tabla_veh.setItem(i, col, item)
        self._habilitar_ficha(True)

    def _veh_id_seleccionado(self) -> int | None:
        fila = self.tabla_veh.currentRow()
        if fila < 0:
            return None
        item = self.tabla_veh.item(fila, 0)
        return int(item.data(Qt.ItemDataRole.UserRole)) if item else None

    # -------------------------------------------------------------- acciones
    def refrescar(self) -> None:
        seleccionado = self._cliente_id
        filas = self.repo.list_clientes(self.busqueda.text().strip())
        self.lista.blockSignals(True)
        self.lista.setRowCount(len(filas))
        fila_sel = -1
        for i, c in enumerate(filas):
            it = QTableWidgetItem(c["nombre"])
            it.setData(Qt.ItemDataRole.UserRole, c["id"])
            self.lista.setItem(i, 0, it)
            self.lista.setItem(i, 1, QTableWidgetItem(c["telefono"]))
            if c["id"] == seleccionado:
                fila_sel = i
        self.lista.blockSignals(False)
        if fila_sel >= 0:
            self.lista.selectRow(fila_sel)
        elif filas:
            self.lista.selectRow(0)
        else:
            self._cliente_id = None
            self._mostrar_ficha()

    def nuevo(self) -> None:
        if not _lic.exigir_operar(self):
            return
        dlg = ClienteDialog(self.repo, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._cliente_id = dlg.result_id
            self.refrescar()

    def _editar_cliente(self) -> None:
        if self._cliente_id is None:
            return
        if not _lic.exigir_operar(self):
            return
        if ClienteDialog(self.repo, self, cliente_id=self._cliente_id).exec() \
                == QDialog.DialogCode.Accepted:
            self.refrescar()

    def eliminar(self) -> None:
        if self._cliente_id is None:
            return
        if not _lic.exigir_operar(self):
            return
        if self.repo.cliente_tiene_documentos(self._cliente_id):
            QMessageBox.warning(self, "No se puede eliminar",
                                "El cliente tiene documentos asociados.")
            return
        if QMessageBox.question(self, "Eliminar", "¿Eliminar el cliente y sus vehículos?") \
                == QMessageBox.StandardButton.Yes:
            self.repo.delete_cliente(self._cliente_id)
            self._cliente_id = None
            self.refrescar()

    def _añadir_vehiculo(self) -> None:
        if self._cliente_id is None:
            return
        dlg = VehiculoFormDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.datos:
            self.repo.save_vehiculo({**dlg.datos, "cliente_id": self._cliente_id})
            self._mostrar_ficha()

    def _editar_vehiculo(self) -> None:
        vid = self._veh_id_seleccionado()
        if vid is None:
            return
        v = self.repo.get_vehiculo(vid)
        datos = {k: v[k] for k in ("id", "matricula", "marca", "modelo", "bastidor",
                                   "anio", "color", "combustible", "kms", "notas")}
        dlg = VehiculoFormDialog(self, datos=datos)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.datos:
            self.repo.save_vehiculo({**dlg.datos, "cliente_id": self._cliente_id})
            self._mostrar_ficha()

    def _quitar_vehiculo(self) -> None:
        vid = self._veh_id_seleccionado()
        if vid is None:
            return
        if self.repo.vehiculo_tiene_documentos(vid):
            QMessageBox.warning(self, "No se puede quitar",
                                "El vehículo tiene documentos asociados.")
            return
        if QMessageBox.question(self, "Quitar", "¿Quitar el vehículo de este cliente?") \
                == QMessageBox.StandardButton.Yes:
            self.repo.delete_vehiculo(vid)
            self._mostrar_ficha()

    def _historial_vehiculo(self) -> None:
        vid = self._veh_id_seleccionado()
        if vid is None:
            QMessageBox.information(self, "Sin vehículo",
                                   "Seleccione un vehículo de la lista.")
            return
        HistorialDialog(self.repo, self, vehiculo_id=vid).exec()
        self._mostrar_ficha()

    def _imprimir_ficha(self) -> None:
        if self._cliente_id is None:
            return
        cliente = self.repo.get_cliente(self._cliente_id)
        vehiculos = self.repo.list_vehiculos(cliente_id=self._cliente_id)
        try:
            ruta = generar_ficha_cliente(cliente, vehiculos, self.repo.get_empresa())
        except Exception as e:  # noqa: BLE001
            _error_pdf(self, e)
            return
        previsualizar_e_imprimir(self, ruta, f"Ficha de {cliente['nombre']}")


class VehiculosTab(_TablaBase):
    columnas = ["Matrícula", "Marca", "Modelo", "Bastidor", "Año", "Kms", "Cliente"]
    columnas_expandibles = (2, 6)  # Modelo y Cliente

    def _añadir_botones(self, barra: QHBoxLayout) -> None:
        b_nuevo = QPushButton("Nuevo")
        b_nuevo.clicked.connect(self.nuevo)
        b_editar = QPushButton("Editar")
        b_editar.clicked.connect(self.editar)
        b_hist = QPushButton("Ver historial")
        b_hist.setProperty("primary", "true")
        b_hist.setToolTip("Intervenciones y trabajos hechos a este vehículo (doble clic en la fila)")
        b_hist.clicked.connect(self.historial)
        b_borrar = QPushButton("Eliminar")
        b_borrar.clicked.connect(self.eliminar)
        for b in (b_nuevo, b_editar, b_hist, b_borrar):
            barra.addWidget(b)
        self._acciones_edicion += [b_nuevo, b_editar, b_borrar]

    def _doble_clic(self) -> None:
        # Los vehículos se dan de alta desde la ficha del cliente; aquí el doble clic
        # muestra el historial (qué se le ha hecho al coche).
        self.historial()

    def historial(self) -> None:
        vid = self._id_seleccionado()
        if vid is None:
            return
        HistorialDialog(self.repo, self, vehiculo_id=vid).exec()

    def refrescar(self) -> None:
        filas = self.repo.list_vehiculos(filtro=self.busqueda.text().strip())
        self.tabla.setRowCount(len(filas))
        for i, v in enumerate(filas):
            self._set_fila(i, v["id"], [
                v["matricula"], v["marca"], v["modelo"], v["bastidor"],
                str(v["anio"] or ""), str(v["kms"] or ""), v["cliente_nombre"],
            ])

    def nuevo(self) -> None:
        if not _lic.exigir_operar(self):
            return
        if not self.repo.list_clientes():
            QMessageBox.information(self, "Sin clientes",
                                   "Cree primero un cliente al que asignar el vehículo.")
            return
        if VehiculoDialog(self.repo, self).exec() == QDialog.DialogCode.Accepted:
            self.refrescar()

    def editar(self) -> None:
        vid = self._id_seleccionado()
        if vid is None:
            return
        if not _lic.exigir_operar(self):
            return
        if VehiculoDialog(self.repo, self, vehiculo_id=vid).exec() == QDialog.DialogCode.Accepted:
            self.refrescar()

    def eliminar(self) -> None:
        vid = self._id_seleccionado()
        if vid is None:
            return
        if not _lic.exigir_operar(self):
            return
        if QMessageBox.question(self, "Eliminar", "¿Eliminar el vehículo?") \
                == QMessageBox.StandardButton.Yes:
            try:
                self.repo.delete_vehiculo(vid)
            except Exception as e:  # noqa: BLE001
                QMessageBox.warning(self, "No se puede eliminar",
                                    f"El vehículo está en uso en algún documento.\n\n{e}")
                return
            self.refrescar()


class ArticulosTab(_TablaBase):
    columnas = ["Código", "Descripción", "Tipo", "Precio base",
                "Impuesto %", "Precio con impuesto", "Activo"]
    columnas_expandibles = (1,)  # Descripción

    def _añadir_botones(self, barra: QHBoxLayout) -> None:
        b_nuevo = QPushButton("Nuevo")
        b_nuevo.setProperty("primary", "true")
        b_nuevo.clicked.connect(self.nuevo)
        b_editar = QPushButton("Editar")
        b_editar.clicked.connect(self.editar)
        b_borrar = QPushButton("Eliminar")
        b_borrar.clicked.connect(self.eliminar)
        self.b_impuesto = QPushButton("Aplicar impuesto por defecto")
        self.b_impuesto.setToolTip("Pone a todos los artículos el impuesto configurado "
                                   "en Datos de mi taller")
        self.b_impuesto.clicked.connect(self._aplicar_impuesto)
        for b in (b_nuevo, b_editar, b_borrar, self.b_impuesto):
            barra.addWidget(b)
        self._acciones_edicion += [b_nuevo, b_editar, b_borrar, self.b_impuesto]

    def refrescar(self) -> None:
        e = self.repo.get_empresa()
        imp = e["impuesto_nombre"] or "IVA"
        self.tabla.setHorizontalHeaderLabels(
            ["Código", "Descripción", "Tipo", "Precio base (sin imp.)",
             f"{imp} %", f"Precio con {imp}", "Activo"])
        self.b_impuesto.setText(f"Aplicar {imp} {e['iva_defecto']:g}% a todos")
        filas = self.repo.list_articulos(self.busqueda.text().strip(), solo_activos=False)
        self.tabla.setRowCount(len(filas))
        for i, a in enumerate(filas):
            self._set_fila(i, a["id"], [
                a["codigo"], a["descripcion"],
                domain.TIPO_LINEA_NOMBRE.get(a["tipo"], a["tipo"]),
                domain.formato_moneda(a["precio"]), f"{a['iva_pct']:g}",
                domain.formato_moneda(domain.con_impuesto(a["precio"], a["iva_pct"])),
                "Sí" if a["activo"] else "No",
            ])

    def _aplicar_impuesto(self) -> None:
        if not _lic.exigir_operar(self):
            return
        e = self.repo.get_empresa()
        iva = float(e["iva_defecto"])
        imp = e["impuesto_nombre"] or "IVA"
        pendientes = self.repo.contar_articulos_con_iva_distinto(iva)
        if pendientes == 0:
            QMessageBox.information(self, "Impuesto de artículos",
                                   f"Todos los artículos ya tienen {imp} {iva:g}%.")
            return
        if QMessageBox.question(
            self, "Aplicar impuesto",
            f"Se va a poner {imp} {iva:g}% a {pendientes} artículo(s) que ahora tienen "
            "otro tipo.\n\n¿Continuar?",
        ) == QMessageBox.StandardButton.Yes:
            n = self.repo.aplicar_impuesto_a_articulos(iva)
            self.refrescar()
            QMessageBox.information(self, "Impuesto de artículos",
                                   f"Actualizados {n} artículos a {imp} {iva:g}%.")

    def nuevo(self) -> None:
        if not _lic.exigir_operar(self):
            return
        if ArticuloDialog(self.repo, self).exec() == QDialog.DialogCode.Accepted:
            self.refrescar()

    def editar(self) -> None:
        aid = self._id_seleccionado()
        if aid is None:
            return
        if not _lic.exigir_operar(self):
            return
        if ArticuloDialog(self.repo, self, articulo_id=aid).exec() == QDialog.DialogCode.Accepted:
            self.refrescar()

    def eliminar(self) -> None:
        aid = self._id_seleccionado()
        if aid is None:
            return
        if not _lic.exigir_operar(self):
            return
        if QMessageBox.question(self, "Eliminar", "¿Eliminar el artículo?") \
                == QMessageBox.StandardButton.Yes:
            self.repo.delete_articulo(aid)
            self.refrescar()


class DocumentosTab(_TablaBase):
    columnas = ["Número", "Fecha", "Cliente", "Matrícula", "Vehículo", "Estado", "Total"]
    columnas_expandibles = (2, 4)  # Cliente y Vehículo

    _EN_CURSO = "__en_curso__"

    def __init__(self, repo: Repository, parent=None) -> None:
        self._filtro_tipo: str | None = self._EN_CURSO
        super().__init__(repo, parent)
        self.tabla.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tabla.customContextMenuRequested.connect(self._menu_contexto)

    def _añadir_botones(self, barra: QHBoxLayout) -> None:
        self.combo_tipo = QComboBox()
        self.combo_tipo.addItem("En curso", self._EN_CURSO)
        self.combo_tipo.addItem("Todos", None)
        for t in domain.TIPOS:
            self.combo_tipo.addItem(domain.TIPO_NOMBRE[t], t)
        self.combo_tipo.setToolTip(
            "«En curso»: presupuestos pendientes de aceptar y órdenes sin terminar.\n"
            "Las facturas se consultan en la pestaña Calendario o en el historial.")
        self.combo_tipo.currentIndexChanged.connect(self._cambiar_tipo)
        barra.addWidget(self.combo_tipo)

        self.btn_nuevo = QPushButton("Nuevo presupuesto")
        self.btn_nuevo.setProperty("primary", "true")
        self.btn_nuevo.clicked.connect(self.nuevo)
        b_editar = QPushButton("Abrir")
        b_editar.clicked.connect(self.editar)
        b_imprimir = QPushButton("Imprimir…")
        b_imprimir.setToolTip("Vista previa e impresión directa")
        b_imprimir.clicked.connect(self.imprimir)
        b_correo = QPushButton("Enviar por correo…")
        b_correo.clicked.connect(self.enviar_correo)

        b_mas = QToolButton()
        b_mas.setText("Más  ▾")
        b_mas.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(b_mas)
        menu.addAction("Guardar PDF", self.exportar_pdf)
        a_conv = menu.addAction("Convertir…", self._convertir_dialogo)
        menu.addSeparator()
        a_hist = menu.addAction("Añadir al historial del vehículo", self._al_historial)
        menu.addAction("Ver historial del vehículo", self._ver_historial)
        menu.addSeparator()
        a_anul = menu.addAction("Anular…", self.anular)
        a_elim = menu.addAction("Eliminar", self.eliminar)
        b_mas.setMenu(menu)

        for b in (self.btn_nuevo, b_editar, b_imprimir, b_correo, b_mas):
            barra.addWidget(b)
        self._acciones_edicion += [self.btn_nuevo, a_conv, a_hist, a_anul, a_elim]

    def _doble_clic(self) -> None:
        # abrir siempre está permitido; el editor se abre en solo lectura sin licencia
        self.editar()

    def _cambiar_tipo(self) -> None:
        self._filtro_tipo = self.combo_tipo.currentData()
        if self._filtro_tipo and self._filtro_tipo != self._EN_CURSO:
            self.btn_nuevo.setText(f"Nuevo: {domain.TIPO_NOMBRE[self._filtro_tipo]}")
        else:
            self.btn_nuevo.setText("Nuevo presupuesto")
        self.refrescar()

    _LIMITE = 500

    def refrescar(self) -> None:
        filtro = self.busqueda.text().strip()
        en_curso = self._filtro_tipo == self._EN_CURSO
        tipo = None if (en_curso or not self._filtro_tipo) else self._filtro_tipo
        filas = self.repo.list_documentos(tipo, filtro, limite=self._LIMITE,
                                          en_curso=en_curso)
        self.tabla.setRowCount(len(filas))
        for i, d in enumerate(filas):
            vehiculo = " ".join(x for x in [d["marca"], d["modelo"]] if x)
            self._set_fila(i, d["id"], [
                d["numero"], d["fecha"], d["cliente_nombre"] or "", d["matricula"] or "",
                vehiculo, d["estado"], domain.formato_moneda(d["total"]),
            ])
        if en_curso and not filtro and not filas:
            self.busqueda.setPlaceholderText("No hay trabajos en curso — todo al día 👍")
        elif len(filas) >= self._LIMITE and not filtro:
            self.busqueda.setPlaceholderText(
                f"Mostrando los {self._LIMITE} más recientes — escribe para buscar otros…")
        else:
            self.busqueda.setPlaceholderText("Buscar…")

    def refrescar_todo(self) -> None:
        """Refresca este listado y, si existe, la pestaña de calendario."""
        self.refrescar()
        cal = getattr(self.window(), "tab_calendario", None)
        if cal is not None:
            cal.refrescar()

    def nuevo(self) -> None:
        if not _lic.exigir_operar(self):
            return
        tipo = self._filtro_tipo
        if not tipo or tipo == self._EN_CURSO:
            tipo = domain.PRESUPUESTO
        dlg = DocumentoEditor(self.repo, self, tipo=tipo)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.refrescar_todo()

    def editar(self) -> None:
        did = self._id_seleccionado()
        if did is None:
            return
        dlg = DocumentoEditor(self.repo, self, documento_id=did)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.refrescar_todo()

    def eliminar(self) -> None:
        did = self._id_seleccionado()
        if did is None:
            return
        if not _lic.exigir_operar(self):
            return
        doc = self.repo.get_documento(did)
        if doc["tipo"] == domain.FACTURA:
            QMessageBox.information(
                self, "No se puede eliminar",
                "Una factura no se elimina (se perdería su número). Usa «Anular factura»: "
                "se conserva el número y queda registrada como anulada.")
            return
        if QMessageBox.question(
            self, "Eliminar", f"¿Eliminar {doc['numero']}?"
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            self.repo.delete_documento(did)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "No se puede eliminar", str(e))
            return
        self.refrescar_todo()

    def anular(self) -> None:
        did = self._id_seleccionado()
        if did is None:
            return
        if not _lic.exigir_operar(self):
            return
        doc = self.repo.get_documento(did)
        if doc["estado"] == "anulado":
            QMessageBox.information(self, "Anular", f"{doc['numero']} ya está anulado.")
            return
        from PySide6.QtWidgets import QInputDialog
        motivo, ok = QInputDialog.getText(
            self, "Anular documento",
            f"Vas a anular {doc['numero']}. Se conserva íntegro y con su número, "
            "pero queda marcado como anulado.\n\nMotivo (opcional):")
        if not ok:
            return
        try:
            self.repo.anular_documento(did, motivo.strip())
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Anular", str(e))
            return
        self.refrescar_todo()

    def _pdf_del_seleccionado(self) -> tuple[Path, str] | None:
        did = self._id_seleccionado()
        if did is None:
            return None
        doc = self.repo.get_documento(did)
        lineas = self.repo.get_lineas(did)
        cliente = self.repo.get_cliente(doc["cliente_id"]) if doc["cliente_id"] else None
        vehiculo = self.repo.get_vehiculo(doc["vehiculo_id"]) if doc["vehiculo_id"] else None
        try:
            ruta = generar_pdf(doc, lineas, cliente, vehiculo, self.repo.get_empresa())
        except Exception as e:  # noqa: BLE001
            _error_pdf(self, e)
            return None
        return ruta, doc["numero"]

    def exportar_pdf(self, *, abrir: bool = True) -> Path | None:
        r = self._pdf_del_seleccionado()
        if r is None:
            return None
        ruta, _numero = r
        if abrir:
            _entregar_pdf(self, ruta)
        return ruta

    def imprimir(self) -> None:
        r = self._pdf_del_seleccionado()
        if r is None:
            return
        ruta, numero = r
        previsualizar_e_imprimir(self, ruta, numero)

    def enviar_correo(self) -> None:
        did = self._id_seleccionado()
        if did is None:
            return
        doc = self.repo.get_documento(did)
        cliente = self.repo.get_cliente(doc["cliente_id"]) if doc["cliente_id"] else None
        vehiculo = self.repo.get_vehiculo(doc["vehiculo_id"]) if doc["vehiculo_id"] else None
        try:
            ruta = generar_pdf(doc, self.repo.get_lineas(did), cliente, vehiculo,
                               self.repo.get_empresa())
        except Exception as e:  # noqa: BLE001
            _error_pdf(self, e)
            return
        from .. import email_envio as mail
        from .correo import EnviarCorreoDialog
        ctx = mail.contexto_documento(doc, cliente, vehiculo, self.repo.get_empresa())
        dest = cliente["email"] if cliente and cliente["email"] else ""
        EnviarCorreoDialog(self.repo, self, pdf=ruta, contexto=ctx,
                           destinatario=dest).exec()

    def _convertir_dialogo(self) -> None:
        did = self._id_seleccionado()
        if did is None:
            return
        if not _lic.exigir_operar(self):
            return
        doc = self.repo.get_documento(did)
        destinos = domain.CONVERSIONES.get(doc["tipo"], [])
        if not destinos:
            QMessageBox.information(self, "Sin conversiones",
                                   "Una factura no se convierte en otro documento.")
            return
        menu = QMenu(self)
        for t in destinos:
            menu.addAction(domain.TIPO_NOMBRE[t],
                           lambda t=t: self._convertir(did, t))
        menu.exec(self.cursor().pos())

    def _al_historial(self) -> None:
        did = self._id_seleccionado()
        if did is None:
            return
        if not _lic.exigir_operar(self):
            return
        doc = self.repo.get_documento(did)
        if not doc["vehiculo_id"]:
            QMessageBox.information(
                self, "Sin vehículo",
                "El documento no tiene un vehículo asignado. Asígnale uno para poder "
                "registrarlo en el historial.",
            )
            return
        datos = self.repo.intervencion_desde_documento(did)
        dlg = IntervencionDialog(self.repo, self, vehiculo_id=doc["vehiculo_id"], datos=datos)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            QMessageBox.information(self, "Historial",
                                   "Intervención añadida al historial del vehículo.")

    def _ver_historial(self) -> None:
        did = self._id_seleccionado()
        if did is None:
            return
        doc = self.repo.get_documento(did)
        if not doc["vehiculo_id"]:
            QMessageBox.information(self, "Sin vehículo",
                                   "El documento no tiene un vehículo asignado.")
            return
        HistorialDialog(self.repo, self, vehiculo_id=doc["vehiculo_id"]).exec()

    def _menu_contexto(self, pos) -> None:
        did = self._id_seleccionado()
        if did is None:
            return
        doc = self.repo.get_documento(did)
        menu = QMenu(self)
        menu.addAction("Abrir", self.editar)
        menu.addAction("Imprimir…", self.imprimir)
        menu.addAction("Enviar por correo…", self.enviar_correo)
        menu.addAction("Guardar PDF", self.exportar_pdf)
        destinos = domain.CONVERSIONES.get(doc["tipo"], [])
        if destinos:
            sub = menu.addMenu("Convertir en")
            for t in destinos:
                sub.addAction(domain.TIPO_NOMBRE[t], lambda t=t: self._convertir(did, t))
        menu.addSeparator()
        menu.addAction("Añadir al historial del vehículo", self._al_historial)
        menu.addAction("Ver historial del vehículo", self._ver_historial)
        menu.addSeparator()
        if doc["tipo"] == domain.FACTURA:
            menu.addAction("Anular…", self.anular)
        else:
            menu.addAction("Anular…", self.anular)
            menu.addAction("Eliminar", self.eliminar)
        menu.exec(self.tabla.viewport().mapToGlobal(pos))

    def _convertir(self, documento_id: int, nuevo_tipo: str) -> None:
        try:
            nuevo_id = self.repo.convertir_documento(documento_id, nuevo_tipo)
        except ValueError as e:
            QMessageBox.warning(self, "No se puede convertir", str(e))
            return
        # si el resultado es una factura ya no está "en curso": muéstrala un momento
        if nuevo_tipo == domain.FACTURA:
            idx = self.combo_tipo.findData(domain.FACTURA)
            if idx >= 0:
                self.combo_tipo.setCurrentIndex(idx)
        self.refrescar_todo()
        dlg = DocumentoEditor(self.repo, self, documento_id=nuevo_id)
        dlg.exec()
        self.refrescar_todo()


class CalendarioTab(QWidget):
    """Consulta de documentos por día (sobre todo facturas)."""

    _COLS = ["Número", "Tipo", "Cliente", "Matrícula", "Estado", "Total"]

    def __init__(self, repo: Repository, parent=None) -> None:
        super().__init__(parent)
        self.repo = repo

        root = QHBoxLayout(self)
        split = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(split)

        izq = QWidget()
        il = QVBoxLayout(izq)
        self.calendario = QCalendarWidget()
        self.calendario.setGridVisible(True)
        self.calendario.setVerticalHeaderFormat(
            QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader)
        self.calendario.selectionChanged.connect(self._dia_cambiado)
        self.calendario.currentPageChanged.connect(lambda *_: self._marcar_mes())
        il.addWidget(self.calendario)
        leyenda = QLabel(
            '<span style="background:#FBE0A8;">&nbsp;&nbsp;</span> día con factura&nbsp;&nbsp;&nbsp;'
            '<span style="background:#F6DAD3;">&nbsp;&nbsp;</span> día con otros documentos')
        leyenda.setStyleSheet("color:#777; font-size:11px;")
        il.addWidget(leyenda)
        self.resumen_mes = QLabel()
        self.resumen_mes.setStyleSheet("color:#777;")
        il.addWidget(self.resumen_mes)
        il.addStretch(1)
        split.addWidget(izq)

        der = QWidget()
        dl = QVBoxLayout(der)
        self.titulo_dia = QLabel()
        self.titulo_dia.setStyleSheet("font-size:15px; font-weight:bold;")
        dl.addWidget(self.titulo_dia)
        self.resumen_dia = QLabel()
        self.resumen_dia.setStyleSheet("color:#777;")
        dl.addWidget(self.resumen_dia)

        self.tabla = QTableWidget(0, len(self._COLS))
        self.tabla.setHorizontalHeaderLabels(self._COLS)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        _config_columnas(self.tabla, self._COLS, (2,))
        self.tabla.doubleClicked.connect(self._abrir)
        dl.addWidget(self.tabla, 1)

        barra = QHBoxLayout()
        b_abrir = QPushButton("Abrir")
        b_abrir.clicked.connect(self._abrir)
        b_imp = QPushButton("Imprimir…")
        b_imp.clicked.connect(self._imprimir)
        b_pdf = QPushButton("Guardar PDF")
        b_pdf.clicked.connect(self._pdf)
        b_hoy = QPushButton("Hoy")
        b_hoy.clicked.connect(lambda: self.calendario.setSelectedDate(QDate.currentDate()))
        for b in (b_abrir, b_imp, b_pdf):
            barra.addWidget(b)
        barra.addStretch(1)
        barra.addWidget(b_hoy)
        dl.addLayout(barra)
        split.addWidget(der)
        split.setSizes([360, 700])

        self._marcar_mes()
        self._dia_cambiado()

    # ------------------------------------------------------------------ datos
    def refrescar(self) -> None:
        self._marcar_mes()
        self._dia_cambiado()

    def _fecha_sel(self) -> str:
        return self.calendario.selectedDate().toString("yyyy-MM-dd")

    def _marcar_mes(self) -> None:
        anio = self.calendario.yearShown()
        mes = self.calendario.monthShown()
        datos = self.repo.fechas_con_documentos(anio, mes)
        normal = QTextCharFormat()
        con_docs = QTextCharFormat()
        con_docs.setFontWeight(75)
        con_docs.setBackground(QColor("#F6DAD3"))
        con_fac = QTextCharFormat()
        con_fac.setFontWeight(75)
        con_fac.setBackground(QColor("#FBE0A8"))
        # limpiar el mes anterior y volver a marcar
        d = QDate(anio, mes, 1)
        while d.month() == mes:
            iso = d.toString("yyyy-MM-dd")
            if iso in datos:
                fmt = con_fac if datos[iso]["facturas"] else con_docs
            else:
                fmt = normal
            self.calendario.setDateTextFormat(d, fmt)
            d = d.addDays(1)
        n_fac = sum(v["facturas"] for v in datos.values())
        n_doc = sum(v["n"] for v in datos.values())
        self.resumen_mes.setText(
            f"Este mes: {n_doc} documento(s), {n_fac} factura(s)." if datos
            else "Este mes no hay documentos.")

    def _dia_cambiado(self) -> None:
        iso = self._fecha_sel()
        filas = self.repo.documentos_de_fecha(iso)
        self.titulo_dia.setText(self.calendario.selectedDate().toString("dddd d 'de' MMMM yyyy"))
        self.tabla.setRowCount(len(filas))
        total_fac = 0.0
        for i, d in enumerate(filas):
            if d["tipo"] == domain.FACTURA and d["estado"] != "anulado":
                total_fac += d["total"] or 0
            valores = [d["numero"], domain.TIPO_NOMBRE.get(d["tipo"], d["tipo"]),
                       d["cliente_nombre"] or "", d["matricula"] or "", d["estado"],
                       domain.formato_moneda(d["total"])]
            for col, val in enumerate(valores):
                item = QTableWidgetItem(val)
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, d["id"])
                self.tabla.setItem(i, col, item)
        if not filas:
            self.resumen_dia.setText("Sin documentos este día.")
        else:
            self.resumen_dia.setText(
                f"{len(filas)} documento(s)  ·  facturado hoy: "
                f"{domain.formato_moneda(total_fac)}")

    def _id_sel(self) -> int | None:
        fila = self.tabla.currentRow()
        if fila < 0:
            return None
        item = self.tabla.item(fila, 0)
        return int(item.data(Qt.ItemDataRole.UserRole)) if item else None

    # ---------------------------------------------------------------- acciones
    def _abrir(self) -> None:
        did = self._id_sel()
        if did is None:
            return
        DocumentoEditor(self.repo, self, documento_id=did).exec()
        self.refrescar()

    def _doc_pdf(self):
        did = self._id_sel()
        if did is None:
            return None
        doc = self.repo.get_documento(did)
        cli = self.repo.get_cliente(doc["cliente_id"]) if doc["cliente_id"] else None
        veh = self.repo.get_vehiculo(doc["vehiculo_id"]) if doc["vehiculo_id"] else None
        try:
            return generar_pdf(doc, self.repo.get_lineas(did), cli, veh,
                               self.repo.get_empresa()), doc["numero"]
        except Exception as e:  # noqa: BLE001
            _error_pdf(self, e)
            return None

    def _imprimir(self) -> None:
        r = self._doc_pdf()
        if r:
            previsualizar_e_imprimir(self, r[0], r[1])

    def _pdf(self) -> None:
        r = self._doc_pdf()
        if r:
            _entregar_pdf(self, r[0])
