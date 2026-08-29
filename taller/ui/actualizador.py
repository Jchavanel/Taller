"""Interfaz para buscar e instalar actualizaciones (menú Ayuda y comprobación al arrancar)."""
from __future__ import annotations

import datetime as _dt
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtWidgets import QApplication, QMessageBox, QProgressDialog

from .. import __version__
from .. import actualizaciones as actu

_AJUSTE_FECHA = "actualizacion_ultima_comprobacion"


class _HiloComprobar(QThread):
    listo = Signal(object)   # dict | None
    fallo = Signal(str)

    def run(self) -> None:
        try:
            self.listo.emit(actu.comprobar())
        except actu.ErrorActualizacion as e:
            self.fallo.emit(str(e))


class _HiloDescargar(QThread):
    progreso = Signal(int, int)
    listo = Signal(str)
    fallo = Signal(str)

    def __init__(self, manifiesto: dict, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._manifiesto = manifiesto

    def run(self) -> None:
        def _cb(hecho: int, total: int) -> None:
            if self.isInterruptionRequested():
                raise actu.ErrorActualizacion("Descarga cancelada.")
            self.progreso.emit(hecho, total)

        try:
            ruta = actu.descargar(self._manifiesto, progreso=_cb)
            self.listo.emit(str(ruta))
        except actu.ErrorActualizacion as e:
            self.fallo.emit(str(e))


class GestorActualizaciones(QObject):
    """Mantiene vivos los hilos y encadena comprobar → preguntar → descargar → aplicar."""

    def __init__(self, ventana) -> None:
        super().__init__(ventana)
        self.ventana = ventana
        self._hilo_c: _HiloComprobar | None = None
        self._hilo_d: _HiloDescargar | None = None
        self._dlg: QProgressDialog | None = None

    # ---------------------------------------------------------------- comprobar
    def comprobar(self, silencioso: bool) -> None:
        if actu.SIN_CONFIGURAR:
            if not silencioso:
                QMessageBox.information(
                    self.ventana, "Actualizaciones",
                    "El sistema de actualizaciones no está configurado todavía "
                    "(falta el repositorio de GitHub).")
            return
        if self._hilo_c is not None:
            return
        self._silencioso = silencioso
        self._hilo_c = _HiloComprobar(self)
        self._hilo_c.listo.connect(self._con_resultado)
        self._hilo_c.fallo.connect(self._con_fallo_comprobar)
        self._hilo_c.finished.connect(self._limpiar_comprobar)
        self._hilo_c.start()

    def comprobar_al_arrancar(self) -> None:
        hoy = _dt.date.today().isoformat()
        if self.ventana.repo.get_ajuste(_AJUSTE_FECHA, "") == hoy:
            return
        self.ventana.repo.set_ajuste(_AJUSTE_FECHA, hoy)
        self.comprobar(silencioso=True)

    def _limpiar_comprobar(self) -> None:
        self._hilo_c = None

    def _con_fallo_comprobar(self, mensaje: str) -> None:
        if not self._silencioso:
            QMessageBox.warning(self.ventana, "Actualizaciones", mensaje)

    def _con_resultado(self, manifiesto) -> None:
        if manifiesto is None:
            if not self._silencioso:
                QMessageBox.information(
                    self.ventana, "Actualizaciones",
                    f"Ya tienes la última versión (v{__version__}).")
            return

        version = manifiesto.get("version", "?")
        notas = str(manifiesto.get("notas") or "").strip()

        modo = actu.modo_instalacion()
        if modo in ("git", "congelado"):
            extra = ("Esta copia se ejecuta desde un clon de git: actualízala con "
                     "«git pull»." if modo == "git" else
                     "Este ejecutable independiente no se actualiza solo: descarga la "
                     "versión nueva desde la página de releases de GitHub.")
            QMessageBox.information(
                self.ventana, "Actualización disponible",
                f"Hay una versión nueva (v{version}).\n\n{extra}")
            return

        texto = f"Hay una versión nueva: <b>v{version}</b> (tienes la v{__version__})."
        if notas:
            texto += "<br><br>" + notas.replace("\n", "<br>")
        texto += "<br><br>Se descargará, se instalará y la aplicación se reiniciará."

        caja = QMessageBox(self.ventana)
        caja.setWindowTitle("Actualización disponible")
        caja.setIcon(QMessageBox.Icon.Question)
        caja.setTextFormat(Qt.TextFormat.RichText)
        caja.setText(texto)
        b_si = caja.addButton("Instalar ahora", QMessageBox.ButtonRole.AcceptRole)
        caja.addButton("Ahora no", QMessageBox.ButtonRole.RejectRole)
        caja.exec()
        if caja.clickedButton() is b_si:
            self._descargar(manifiesto)

    # ---------------------------------------------------------------- descargar
    def _descargar(self, manifiesto: dict) -> None:
        self._dlg = QProgressDialog(
            "Descargando la actualización…", "Cancelar", 0, 100, self.ventana)
        self._dlg.setWindowTitle("Actualizando")
        self._dlg.setMinimumDuration(0)
        self._dlg.setAutoClose(False)
        self._dlg.setAutoReset(False)
        self._dlg.setValue(0)

        self._hilo_d = _HiloDescargar(manifiesto, self)
        self._hilo_d.progreso.connect(self._con_progreso)
        self._hilo_d.listo.connect(self._con_descarga)
        self._hilo_d.fallo.connect(self._con_fallo_descarga)
        self._hilo_d.finished.connect(self._limpiar_descargar)
        self._dlg.canceled.connect(self._hilo_d.requestInterruption)
        self._hilo_d.start()

    def _con_progreso(self, hecho: int, total: int) -> None:
        if not self._dlg:
            return
        if total > 0:
            self._dlg.setMaximum(total)
            self._dlg.setValue(hecho)
            self._dlg.setLabelText(
                f"Descargando la actualización…  {hecho // 1024} / {total // 1024} KB")
        else:
            self._dlg.setMaximum(0)  # barra indeterminada

    def _con_fallo_descarga(self, mensaje: str) -> None:
        if self._dlg:
            self._dlg.cancel()
        if "cancelada" not in mensaje.lower():
            QMessageBox.warning(self.ventana, "Actualización", mensaje)

    def _limpiar_descargar(self) -> None:
        self._hilo_d = None

    def _con_descarga(self, ruta: str) -> None:
        if self._dlg:
            self._dlg.setMaximum(1)
            self._dlg.setValue(1)
            self._dlg.close()
            self._dlg = None

        QMessageBox.information(
            self.ventana, "Instalar actualización",
            "La descarga ha terminado.\n\n"
            "La aplicación se cerrará y volverá a abrirse para completar la instalación.")

        try:
            from ..backup import hacer_copia
            hacer_copia(self.ventana.db, forzar=True)
        except Exception:  # noqa: BLE001
            pass

        try:
            actu.aplicar(Path(ruta), antes_de_reiniciar=self.ventana.db.close)
        except actu.ErrorActualizacion as e:
            QMessageBox.critical(
                self.ventana, "Actualización",
                f"No se pudo instalar la actualización:\n\n{e}\n\n"
                "La versión actual sigue funcionando.")
