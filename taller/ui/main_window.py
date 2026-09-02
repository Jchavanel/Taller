"""Ventana principal de la aplicación."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QLabel,
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

        from .. import licencia
        self.estado_licencia = licencia.evaluar(self.repo)
        licencia.fijar(self.estado_licencia)

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

        from PySide6.QtWidgets import QVBoxLayout, QWidget
        central = QWidget()
        cl = QVBoxLayout(central)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)
        self.banda_licencia = QLabel()
        self.banda_licencia.setProperty("clase", "aviso")
        self.banda_licencia.setWordWrap(True)
        self.banda_licencia.setContentsMargins(10, 6, 10, 6)
        self.banda_licencia.hide()
        cl.addWidget(self.banda_licencia)
        cl.addWidget(self.tabs)
        self.setCentralWidget(central)

        from .actualizador import GestorActualizaciones
        self._gestor_actu = GestorActualizaciones(self)

        self.setStatusBar(QStatusBar())
        self._construir_menu()
        self._preparar_primer_arranque()
        self._refrescar_todo()
        self._aplicar_licencia()
        self._avisar_datos_empresa()

        from PySide6.QtCore import QTimer
        QTimer.singleShot(1500, self._gestor_actu.comprobar_al_arrancar)
        QTimer.singleShot(300, self._avisar_licencia_arranque)
        QTimer.singleShot(3000, lambda: self._verifactu_enviar(silencioso=True))

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
        act_numeracion = QAction("Numeración de documentos…", self)
        act_numeracion.triggered.connect(self._editar_numeracion)
        m_archivo.addAction(act_numeracion)
        act_seed = QAction("Cargar artículos y servicios de ejemplo…", self)
        act_seed.triggered.connect(self._cargar_ejemplo)
        m_archivo.addAction(act_seed)
        from ..seed import hay_preconfiguracion
        if hay_preconfiguracion():
            act_taller = QAction("Cargar configuración inicial del taller…", self)
            act_taller.triggered.connect(self._precargar_taller)
            m_archivo.addAction(act_taller)
        m_archivo.addSeparator()
        m_copias = m_archivo.addMenu("Copias de seguridad")
        m_copias.addAction("Copia de seguridad ahora…", self._copia_seguridad)
        m_copias.addAction("Guardar copia en… (USB / disco externo)",
                           self._guardar_copia_en)
        m_copias.addSeparator()
        m_copias.addAction("Carpeta de copia automática (USB)…",
                           self._carpeta_copia_externa)
        m_copias.addSeparator()
        m_copias.addAction("Restaurar copia de seguridad…", self._restaurar_copia)
        act_carpeta = QAction("Abrir carpeta de datos…", self)
        act_carpeta.triggered.connect(self._abrir_carpeta_datos)
        m_archivo.addAction(act_carpeta)
        m_archivo.addSeparator()
        act_licencia = QAction("Licencia…", self)
        act_licencia.triggered.connect(self._abrir_licencia)
        m_archivo.addAction(act_licencia)
        act_vf = QAction("VeriFactu: estado del registro…", self)
        act_vf.triggered.connect(self._verifactu_estado)
        m_archivo.addAction(act_vf)
        self.act_vf_envio = QAction("VeriFactu: enviar registros pendientes a la AEAT", self)
        self.act_vf_envio.triggered.connect(lambda: self._verifactu_enviar(silencioso=False))
        m_archivo.addAction(self.act_vf_envio)
        m_archivo.addSeparator()
        act_salir = QAction("Salir", self)
        act_salir.setShortcut("Ctrl+Q")
        act_salir.triggered.connect(self.close)
        m_archivo.addAction(act_salir)

        self.m_nuevo = m_nuevo = barra.addMenu("&Nuevo")
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

    def _editar_numeracion(self) -> None:
        from .numeracion_dialog import NumeracionDialog
        if NumeracionDialog(self.repo, self).exec() == QDialog.DialogCode.Accepted:
            self.statusBar().showMessage("Numeración actualizada", 4000)
            self._refrescar_todo()

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
        from ..backup import (carpeta_copias, carpeta_externa, hacer_copia,
                              replicar_externa)
        ruta = hacer_copia(self.db, forzar=True)
        if not ruta:
            QMessageBox.warning(self, "Copia de seguridad",
                                "No se ha podido crear la copia (revisa el registro).")
            return
        lineas = [f"Copia creada: {ruta.name}", f"en {carpeta_copias()}"]
        if carpeta_externa(self.repo) is not None:
            ok, msg = replicar_externa(ruta, self.repo)
            lineas += ["", ("✓ Copiada también a:\n" + msg) if ok else ("⚠ " + msg)]
        QMessageBox.information(self, "Copia de seguridad", "\n".join(lineas))

    def _guardar_copia_en(self) -> None:
        from datetime import date

        from PySide6.QtWidgets import QFileDialog

        from ..backup import exportar_copia
        sugerido = f"taller-{date.today().isoformat()}.db"
        ruta, _ = QFileDialog.getSaveFileName(
            self, "Guardar copia de seguridad (elige el pendrive o disco externo)",
            sugerido, "Base de datos (*.db)")
        if not ruta:
            return
        try:
            p = exportar_copia(Path(ruta), self.db)
        except OSError as e:
            QMessageBox.critical(self, "Guardar copia", f"No se pudo guardar:\n{e}")
            return
        QMessageBox.information(self, "Guardar copia",
                               f"Copia guardada en:\n{p}")

    def _carpeta_copia_externa(self) -> None:
        from PySide6.QtWidgets import QFileDialog

        from ..backup import (carpeta_externa, hacer_copia, replicar_externa,
                              set_carpeta_externa)
        actual = carpeta_externa(self.repo)
        if actual is not None:
            r = QMessageBox.question(
                self, "Carpeta de copia automática",
                f"Ahora, cada copia de seguridad se guarda también en:\n{actual}\n\n"
                "¿Elegir otra carpeta?\n(«No» desactiva la copia automática externa.)",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                | QMessageBox.StandardButton.Cancel)
            if r == QMessageBox.StandardButton.Cancel:
                return
            if r == QMessageBox.StandardButton.No:
                set_carpeta_externa(self.repo, None)
                self.statusBar().showMessage("Copia automática externa desactivada", 5000)
                return
        carpeta = QFileDialog.getExistingDirectory(
            self, "Elegir carpeta para la copia automática (USB / disco externo)",
            str(actual) if actual else "")
        if not carpeta:
            return
        set_carpeta_externa(self.repo, carpeta)
        ruta = hacer_copia(self.db, forzar=True)
        ok, msg = replicar_externa(ruta, self.repo) if ruta else (False, "")
        if ok:
            QMessageBox.information(
                self, "Carpeta de copia automática",
                f"Configurada:\n{carpeta}\n\n"
                "Se ha guardado ahí una copia de prueba correctamente.\n"
                "A partir de ahora, cada copia de seguridad se guarda también en esa "
                "carpeta (si está disponible).")
        else:
            QMessageBox.warning(
                self, "Carpeta de copia automática",
                f"Carpeta guardada:\n{carpeta}\n\nPero la copia de prueba ha fallado:\n{msg}")

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

    # ------------------------------------------------------------- verifactu
    def _verifactu_enviar(self, silencioso: bool = True) -> None:
        from .. import verifactu
        if not verifactu.envia_a_aeat(self.repo.get_empresa()):
            if not silencioso:
                QMessageBox.information(
                    self, "VeriFactu",
                    "VeriFactu no está en modo de envío. Cámbialo a «Preproducción» o "
                    "«Producción» en Datos de mi taller → VeriFactu.")
            return
        if getattr(self, "_hilo_vf", None) is not None:
            return
        from PySide6.QtCore import QThread, Signal

        class _Hilo(QThread):
            hecho = Signal(dict)

            def run(self):  # noqa: D401
                try:
                    from ..database import Database
                    from ..repository import Repository
                    from .. import verifactu_envio
                    self.hecho.emit(verifactu_envio.enviar_pendientes(Repository(Database())))
                except Exception as e:  # noqa: BLE001
                    self.hecho.emit({"enviados": 0, "error": str(e)})

        self._hilo_vf = _Hilo(self)
        self._hilo_vf.hecho.connect(lambda r: self._verifactu_enviado(r, silencioso))
        self._hilo_vf.finished.connect(lambda: setattr(self, "_hilo_vf", None))
        self.statusBar().showMessage("VeriFactu: enviando registros a la AEAT…", 4000)
        self._hilo_vf.start()

    def _verifactu_enviado(self, r: dict, silencioso: bool) -> None:
        self.tab_documentos.refrescar_todo()
        if r.get("error"):
            self.statusBar().showMessage(f"VeriFactu: {r['error']}", 8000)
            if not silencioso:
                QMessageBox.warning(self, "VeriFactu", r["error"])
            return
        resumen = (f"Enviados {r.get('enviados', 0)}"
                   + (f", con errores {r['con_errores']}" if r.get("con_errores") else "")
                   + (f", rechazados {r['rechazados']}" if r.get("rechazados") else ""))
        self.statusBar().showMessage(f"VeriFactu: {resumen}", 8000)
        if not silencioso:
            QMessageBox.information(
                self, "VeriFactu",
                f"{resumen}.\nEstado del envío: {r.get('estado_envio', '-')}"
                + (f"\nCSV: {r['csv']}" if r.get("csv") else ""))

    def _verifactu_estado(self) -> None:
        from .. import verifactu
        emp = self.repo.get_empresa()
        modo = emp["verifactu_modo"] or "desactivado"
        n = self.db.query_one("SELECT COUNT(*) AS n FROM registro_facturacion")["n"]
        lineas = [f"Modo: <b>{modo}</b>", f"Registros de facturación: <b>{n}</b>"]
        if n:
            problemas = verifactu.verificar_cadena(self.db)
            if problemas:
                lineas.append('<span style="color:#b3261e"><b>⚠ La cadena de huellas '
                              "tiene problemas:</b></span>")
                lineas += [f"• {p}" for p in problemas[:10]]
            else:
                lineas.append('<span style="color:#2e7d32">✓ La cadena de huellas es '
                              "íntegra.</span>")
        evs = self.db.query("SELECT fecha, tipo, detalle FROM evento ORDER BY id DESC LIMIT 8")
        if evs:
            lineas.append("<br>Últimos eventos:")
            lineas += [f"<code>{e['fecha'][:19]}</code> {e['tipo']} — {e['detalle']}"
                       for e in evs]
        from PySide6.QtCore import Qt
        caja = QMessageBox(self)
        caja.setWindowTitle("VeriFactu — estado del registro")
        caja.setTextFormat(Qt.TextFormat.RichText)
        caja.setText("<br>".join(lineas))
        caja.exec()

    # ------------------------------------------------------------- licencia
    def _abrir_licencia(self) -> None:
        from .licencia_dialog import LicenciaDialog
        dlg = LicenciaDialog(self.repo, self)
        dlg.exec()
        if dlg.licencia_cambiada:
            self._reevaluar_licencia()

    def _reevaluar_licencia(self) -> None:
        from .. import licencia
        self.estado_licencia = licencia.evaluar(self.repo)
        licencia.fijar(self.estado_licencia)
        self._aplicar_licencia()

    def _aplicar_licencia(self) -> None:
        e = self.estado_licencia
        if e.nivel == "ok":
            self.banda_licencia.hide()
        else:
            self.banda_licencia.setText(
                f"{e.titulo}. " + e.detalle.replace(chr(10), " ")
                + ("   —  modo consulta (Archivo → Licencia)" if not e.puede_operar
                   else "   —  Archivo → Licencia"))
            self.banda_licencia.show()

        bloq = not e.puede_operar
        self.m_nuevo.setEnabled(not bloq)
        for tab in (self.tab_documentos, self.tab_clientes, self.tab_vehiculos,
                    self.tab_articulos):
            if hasattr(tab, "bloquear_edicion"):
                tab.bloquear_edicion(bloq)

    def _avisar_licencia_arranque(self) -> None:
        e = self.estado_licencia
        if e.nivel == "bloqueo":
            QMessageBox.warning(self, e.titulo or "Licencia",
                                e.detalle + "\n\nPuedes seguir consultando, imprimiendo y "
                                "exportando lo que ya tienes.")
            self._abrir_licencia()

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

    def closeEvent(self, evento) -> None:  # noqa: N802
        try:
            from .. import verifactu
            if verifactu.activo(self.repo.get_empresa()):
                verifactu.registrar_evento(self.db, "cierre", "")
        except Exception:  # noqa: BLE001
            pass
        super().closeEvent(evento)


def run() -> int:
    import sys
    import time

    from ..backup import hacer_copia, replicar_externa
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

    from .. import verifactu
    if verifactu.activo(Repository(db).get_empresa()):
        verifactu.registrar_evento(db, "arranque", f"v{__version__}")

    splash.estado("Copia de seguridad…")
    try:
        copia = hacer_copia(db)
        if copia:
            log().info("Copia diaria: %s", copia.name)
            ok, msg = replicar_externa(copia, Repository(db))
            if not ok and msg:
                log().warning("Copia externa: %s", msg.replace("\n", " "))
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
