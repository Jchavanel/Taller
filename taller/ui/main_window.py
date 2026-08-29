"""Ventana principal de la aplicación."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QMainWindow,
    QMessageBox,
    QStatusBar,
    QTabWidget,
)

from .. import APP_NAME, __version__
from ..database import Database
from ..paths import data_dir, db_path, migrar_datos_antiguos
from ..repository import Repository
from .dialogs import EmpresaDialog
from .tabs import (
    ArticulosTab,
    CalendarioTab,
    ClientesTab,
    DocumentosTab,
    VehiculosTab,
)


class MainWindow(QMainWindow):
    def __init__(self, db: Database) -> None:
        super().__init__()
        self.db = db
        self.repo = Repository(db)

        self.setWindowTitle(f"{APP_NAME}  v{__version__}")
        icono = Path(__file__).resolve().parent.parent / "resources" / "icono.png"
        if icono.is_file():
            self.setWindowIcon(QIcon(str(icono)))
        self.resize(1040, 640)

        self.tabs = QTabWidget()
        self.tab_documentos = DocumentosTab(self.repo)
        self.tab_calendario = CalendarioTab(self.repo)
        self.tab_clientes = ClientesTab(self.repo)
        self.tab_vehiculos = VehiculosTab(self.repo)
        self.tab_articulos = ArticulosTab(self.repo)
        self.tabs.addTab(self.tab_documentos, "Documentos")
        self.tabs.addTab(self.tab_calendario, "Calendario")
        self.tabs.addTab(self.tab_clientes, "Clientes")
        self.tabs.addTab(self.tab_vehiculos, "Vehículos")
        self.tabs.addTab(self.tab_articulos, "Artículos y servicios")
        self.tabs.currentChanged.connect(self._refrescar_actual)
        self.setCentralWidget(self.tabs)

        from .actualizador import GestorActualizaciones
        self._gestor_actu = GestorActualizaciones(self)

        self.setStatusBar(QStatusBar())
        self._construir_menu()
        self._preparar_primer_arranque()
        self._refrescar_todo()
        self._avisar_datos_empresa()

        from PySide6.QtCore import QTimer
        QTimer.singleShot(1500, self._gestor_actu.comprobar_al_arrancar)

    # --------------------------------------------------------------- menú
    def _construir_menu(self) -> None:
        barra = self.menuBar()

        m_archivo = barra.addMenu("&Archivo")
        act_empresa = QAction("Datos de mi taller…", self)
        act_empresa.triggered.connect(self._editar_empresa)
        m_archivo.addAction(act_empresa)
        act_correo = QAction("Configurar correo electrónico…", self)
        act_correo.triggered.connect(self._configurar_correo)
        m_archivo.addAction(act_correo)
        act_seed = QAction("Cargar artículos y servicios de ejemplo…", self)
        act_seed.triggered.connect(self._cargar_ejemplo)
        m_archivo.addAction(act_seed)
        from ..seed import hay_preconfiguracion
        if hay_preconfiguracion():
            act_taller = QAction("Cargar configuración inicial del taller…", self)
            act_taller.triggered.connect(self._precargar_taller)
            m_archivo.addAction(act_taller)
        m_archivo.addSeparator()
        act_copia = QAction("Copia de seguridad ahora…", self)
        act_copia.triggered.connect(self._copia_seguridad)
        m_archivo.addAction(act_copia)
        act_restaurar = QAction("Restaurar copia de seguridad…", self)
        act_restaurar.triggered.connect(self._restaurar_copia)
        m_archivo.addAction(act_restaurar)
        act_carpeta = QAction("Abrir carpeta de datos…", self)
        act_carpeta.triggered.connect(self._abrir_carpeta_datos)
        m_archivo.addAction(act_carpeta)
        m_archivo.addSeparator()
        act_salir = QAction("Salir", self)
        act_salir.setShortcut("Ctrl+Q")
        act_salir.triggered.connect(self.close)
        m_archivo.addAction(act_salir)

        m_nuevo = barra.addMenu("&Nuevo")
        for etiqueta, tipo in [
            ("Presupuesto", "presupuesto"), ("Orden de trabajo", "orden"),
            ("Albarán", "albaran"), ("Factura", "factura"),
        ]:
            a = QAction(etiqueta, self)
            a.triggered.connect(lambda _c=False, t=tipo: self._nuevo_documento(t))
            m_nuevo.addAction(a)
        m_nuevo.addSeparator()
        for etiqueta, slot in [
            ("Cliente", self.tab_clientes.nuevo),
            ("Vehículo", self.tab_vehiculos.nuevo),
            ("Artículo / servicio", self.tab_articulos.nuevo),
        ]:
            a = QAction(etiqueta, self)
            a.triggered.connect(lambda _c=False, s=slot: (s(), self._refrescar_todo()))
            m_nuevo.addAction(a)

        m_ver = barra.addMenu("&Ver")
        m_tema = m_ver.addMenu("Tema")
        from PySide6.QtGui import QActionGroup

        from . import theme
        self._grupo_tema = QActionGroup(self)
        self._grupo_tema.setExclusive(True)
        actual = self.repo.get_ajuste("tema", theme.CLARO)
        for clave, etiqueta in theme.TEMAS.items():
            a = QAction(etiqueta, self, checkable=True)
            a.setData(clave)
            a.setChecked(clave == actual)
            a.triggered.connect(lambda _c=False, k=clave: self._cambiar_tema(k))
            self._grupo_tema.addAction(a)
            m_tema.addAction(a)

        m_ayuda = barra.addMenu("A&yuda")
        act_actu = QAction("Buscar actualizaciones…", self)
        act_actu.triggered.connect(lambda: self._gestor_actu.comprobar(silencioso=False))
        m_ayuda.addAction(act_actu)
        act_acerca = QAction("Acerca de…", self)
        act_acerca.triggered.connect(self._acerca_de)
        m_ayuda.addAction(act_acerca)

    # ------------------------------------------------------------- acciones
    def _nuevo_documento(self, tipo: str) -> None:
        self.tabs.setCurrentWidget(self.tab_documentos)
        idx = self.tab_documentos.combo_tipo.findData(tipo)
        if idx >= 0:
            self.tab_documentos.combo_tipo.setCurrentIndex(idx)
        self.tab_documentos.nuevo()

    def _cambiar_tema(self, clave: str) -> None:
        from . import theme
        self.repo.set_ajuste("tema", clave)
        app = QApplication.instance()
        if app is not None:
            theme.aplicar_tema(app, clave)
        self.statusBar().showMessage(f"Tema: {theme.TEMAS.get(clave, clave)}", 3000)

    def _editar_empresa(self) -> None:
        if EmpresaDialog(self.repo, self).exec() == QDialog.DialogCode.Accepted:
            self.statusBar().showMessage("Datos del taller guardados", 4000)

    def _configurar_correo(self) -> None:
        from .correo import CorreoConfigDialog
        if CorreoConfigDialog(self.repo, self).exec() == QDialog.DialogCode.Accepted:
            self.statusBar().showMessage("Configuración de correo guardada", 4000)

    def _cargar_ejemplo(self) -> None:
        from ..seed import cargar_articulos_ejemplo
        n = cargar_articulos_ejemplo(self.repo)
        self.tab_articulos.refrescar()
        QMessageBox.information(self, "Datos de ejemplo",
                               f"Se han añadido {n} artículos/servicios al catálogo.")

    def _precargar_taller(self) -> None:
        if self.repo.get_empresa()["nombre"] and QMessageBox.question(
            self, "Sobrescribir",
            "Ya hay datos de taller guardados. ¿Reemplazarlos por la configuración inicial?",
        ) != QMessageBox.StandardButton.Yes:
            return
        from ..seed import precargar_taller
        precargar_taller(self.repo)
        self._refrescar_todo()
        self.statusBar().showMessage("Configuración inicial cargada", 5000)

    def _preparar_primer_arranque(self) -> None:
        """Base de datos recién creada y vacía: aplica la configuración inicial si la hay."""
        from ..seed import hay_preconfiguracion, precargar_taller
        e = self.repo.get_empresa()
        vacia = (
            not e["nombre"]
            and self.repo.estadisticas()["clientes"] == 0
            and not self.repo.list_documentos()
        )
        if vacia and hay_preconfiguracion():
            precargar_taller(self.repo)

    def _copia_seguridad(self) -> None:
        from ..backup import carpeta_copias, hacer_copia
        ruta = hacer_copia(self.db, forzar=True)
        if ruta:
            QMessageBox.information(
                self, "Copia de seguridad",
                f"Copia creada:\n{ruta.name}\n\nen {carpeta_copias()}")
        else:
            QMessageBox.warning(self, "Copia de seguridad",
                                "No se ha podido crear la copia (revisa el registro).")

    def _restaurar_copia(self) -> None:
        from ..backup import carpeta_copias, listar_copias, restaurar
        copias = listar_copias()
        if not copias:
            QMessageBox.information(self, "Restaurar copia",
                                   "Todavía no hay ninguna copia de seguridad.")
            return
        from PySide6.QtWidgets import QFileDialog
        ruta, _ = QFileDialog.getOpenFileName(
            self, "Elegir copia de seguridad", str(carpeta_copias()),
            "Base de datos (*.db)")
        if not ruta:
            return
        if QMessageBox.warning(
            self, "Restaurar copia",
            "Se sustituirá la base de datos actual por la copia elegida.\n"
            "Se guardará antes una copia del estado actual.\n\n"
            "La aplicación se cerrará; vuelve a abrirla después.\n\n¿Continuar?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            restaurar(Path(ruta), self.db)
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "Restaurar copia", f"No se pudo restaurar:\n{e}")
            return
        QMessageBox.information(self, "Restaurar copia",
                               "Base de datos restaurada. La aplicación se cerrará ahora.")
        QApplication.instance().quit()

    def _abrir_carpeta_datos(self) -> None:
        from .tabs import _abrir_fichero
        _abrir_fichero(data_dir())

    def _avisar_datos_empresa(self) -> None:
        if self.repo.get_empresa()["nombre"]:
            return
        from ..seed import hay_preconfiguracion, precargar_taller
        if hay_preconfiguracion() and QMessageBox.question(
            self, "Datos del taller",
            "Todavía no hay datos de taller configurados.\n\n"
            "¿Cargar la configuración inicial incluida (datos fiscales, IBAN, logo, "
            "impuesto y textos)?\n\n"
            "Podrás cambiarlos luego en Archivo → Datos de mi taller.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        ) == QMessageBox.StandardButton.Yes:
            precargar_taller(self.repo)
            self._refrescar_todo()
            self.statusBar().showMessage("Configuración inicial cargada", 5000)
        else:
            QMessageBox.information(
                self, "Configura tu taller",
                "Rellena los datos de tu taller en Archivo → Datos de mi taller "
                "antes de emitir documentos.",
            )

    def _acerca_de(self) -> None:
        QMessageBox.about(
            self, "Acerca de",
            f"<b>{APP_NAME}</b> v{__version__}<br><br>"
            "Gestión local de presupuestos, órdenes de trabajo, albaranes y facturas "
            "para talleres de automoción.<br><br>"
            f"Base de datos:<br><code>{db_path()}</code><br><br>"
            "Los datos se guardan únicamente en este equipo.",
        )

    # ----------------------------------------------------------- refresco
    def _refrescar_actual(self) -> None:
        w = self.tabs.currentWidget()
        if hasattr(w, "refrescar"):
            w.refrescar()

    def _refrescar_todo(self) -> None:
        for w in (self.tab_documentos, self.tab_calendario, self.tab_clientes,
                  self.tab_vehiculos, self.tab_articulos):
            w.refrescar()


def run() -> int:
    import sys
    import time

    from ..backup import hacer_copia
    from ..errores import configurar_logging, instalar_excepthook, log
    from . import theme
    from .splash import Splash

    configurar_logging()
    instalar_excepthook()

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    icono = Path(__file__).resolve().parent.parent / "resources" / "icono.png"
    if icono.is_file():
        app.setWindowIcon(QIcon(str(icono)))

    _inicio = time.monotonic()

    # IMPORTANTE: la migración debe ir ANTES de tocar la base de datos nueva
    # (abrirla o incluso consultarla crea el fichero y anularía la migración).
    origen_migrado = migrar_datos_antiguos()

    tema_inicial = _leer_tema_rapido()
    theme.aplicar_tema(app, tema_inicial)

    splash = Splash(theme.resolver(tema_inicial))
    splash.show()
    splash.estado("Iniciando…")
    app.processEvents()

    splash.estado("Abriendo la base de datos…")
    db = Database()

    splash.estado("Copia de seguridad…")
    try:
        copia = hacer_copia(db)
        if copia:
            log().info("Copia diaria: %s", copia.name)
    except Exception:  # noqa: BLE001
        log().exception("Fallo al hacer la copia de seguridad de arranque")

    tema = db.query_one("SELECT valor FROM meta WHERE clave = 'tema'")
    tema = tema["valor"] if tema else theme.CLARO
    if tema != tema_inicial:
        theme.aplicar_tema(app, tema)
        splash.repaint()

    splash.estado("Preparando la ventana…")
    win = MainWindow(db)

    # deja ver el splash al menos un momento
    restante = 0.9 - (time.monotonic() - _inicio)
    if restante > 0:
        time.sleep(restante)

    win.show()
    splash.finish(win)

    if origen_migrado is not None:
        QMessageBox.information(
            win, "Datos trasladados",
            "Se han copiado tus datos anteriores a la nueva carpeta, dentro de la "
            f"carpeta del programa:\n\n{data_dir()}\n\n"
            f"(Copia conservada en {origen_migrado}.)",
        )
    return app.exec()


def _leer_tema_rapido() -> str:
    """Lee el tema guardado sin abrir toda la app (para pintar el splash ya con color).

    NO debe crear el fichero de base de datos si no existe (rompería la migración).
    """
    import sqlite3

    from . import theme

    ruta = db_path()
    if not ruta.is_file():
        return theme.CLARO
    try:
        con = sqlite3.connect(f"file:{ruta}?mode=ro", uri=True)
        row = con.execute("SELECT valor FROM meta WHERE clave = 'tema'").fetchone()
        con.close()
        if row and row[0] in (theme.CLARO, theme.OSCURO, theme.AUTO):
            return row[0]
    except sqlite3.Error:
        pass
    return theme.CLARO
