"""Diálogos de configuración de correo y de envío de documentos por email."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from .. import email_envio as mail
from ..repository import Repository


class CorreoConfigDialog(QDialog):
    """Configura el servidor SMTP y las plantillas de asunto/cuerpo."""

    def __init__(self, repo: Repository, parent=None) -> None:
        super().__init__(parent)
        self.repo = repo
        self.setWindowTitle("Configurar correo electrónico")
        self.setMinimumWidth(560)
        row = repo.get_empresa()
        cfg = mail.ConfigCorreo.desde_empresa(row)

        lay = QVBoxLayout(self)
        form = QFormLayout()
        lay.addLayout(form)

        self._aplicando = False
        self._presets_usuario: dict = {}
        self.preset = QComboBox()
        b_guardar_prov = QPushButton("Guardar proveedor…")
        b_guardar_prov.setToolTip("Guarda el servidor y puerto de abajo como un proveedor "
                                  "reutilizable")
        b_guardar_prov.clicked.connect(self._guardar_preset)
        self.b_borrar_prov = QPushButton("Eliminar")
        self.b_borrar_prov.clicked.connect(self._borrar_preset)
        prov_row = QHBoxLayout()
        prov_row.addWidget(self.preset, 1)
        prov_row.addWidget(b_guardar_prov)
        prov_row.addWidget(self.b_borrar_prov)
        form.addRow("Proveedor", prov_row)

        self.host = QLineEdit(cfg.host)
        self.host.setPlaceholderText("p. ej. smtp.midominio.com")
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(cfg.port)
        self.seguridad = QComboBox()
        for k, v in mail.SEGURIDAD.items():
            self.seguridad.addItem(v, k)
        i = self.seguridad.findData(cfg.seguridad)
        self.seguridad.setCurrentIndex(max(i, 0))

        # Selecciona el proveedor que coincida con el servidor ya configurado.
        coincidente = next(
            (n for n, p in mail.todos_los_presets().items()
             if p["smtp_host"].lower() == cfg.host.strip().lower()), None)
        self._recargar_presets(seleccionar=coincidente)
        self.preset.currentIndexChanged.connect(self._aplicar_preset)
        self.seguridad.currentIndexChanged.connect(self._sync_puerto)
        # Al tocar los campos a mano, el proveedor pasa a "Otro (manual)".
        self.host.textEdited.connect(self._marcar_manual)
        self.port.valueChanged.connect(self._marcar_manual)
        self.seguridad.activated.connect(self._marcar_manual)

        self.usuario = QLineEdit(cfg.usuario)
        self.usuario.setPlaceholderText("normalmente tu dirección de correo completa")
        self.password = QLineEdit(cfg.password)
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        ver = QPushButton("👁")
        ver.setCheckable(True)
        ver.setFixedWidth(34)
        ver.toggled.connect(lambda on: self.password.setEchoMode(
            QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password))
        pass_row = QHBoxLayout()
        pass_row.addWidget(self.password)
        pass_row.addWidget(ver)
        self.remitente = QLineEdit(cfg.remitente)
        self.remitente.setPlaceholderText("dirección que verá el cliente (vacío = usuario)")

        form.addRow("Servidor SMTP", self.host)
        form.addRow("Puerto", self.port)
        form.addRow("Seguridad", self.seguridad)
        form.addRow("Usuario", self.usuario)
        form.addRow("Contraseña", pass_row)
        form.addRow("Remitente (De:)", self.remitente)

        guardado = ("en el <b>llavero del sistema</b>" if mail.password_en_llavero()
                    else "ofuscada en la base de datos local (no es cifrado fuerte)")
        aviso = QLabel(
            "Con <b>Gmail</b> y <b>Outlook/Office 365</b> se necesita una "
            "<b>contraseña de aplicación</b> (no la de la cuenta) y tener activada la "
            "verificación en dos pasos. Con el correo de un dominio propio o del hosting "
            "suele valer la contraseña normal: elige «Otro (configuración manual)».<br>"
            f"La contraseña se guarda {guardado}."
        )
        aviso.setWordWrap(True)
        aviso.setStyleSheet("color:#555; font-size:11px;")
        form.addRow("", aviso)

        self.asunto = QLineEdit(cfg.asunto)
        self.cuerpo = QPlainTextEdit(cfg.cuerpo)
        self.cuerpo.setFixedHeight(140)
        form.addRow("Asunto (plantilla)", self.asunto)
        form.addRow("Cuerpo (plantilla)", self.cuerpo)
        ayuda = QLabel("Marcadores disponibles: {tipo} {numero} {fecha} {cliente} "
                       "{matricula} {total} {taller} {telefono}")
        ayuda.setWordWrap(True)
        ayuda.setStyleSheet("color:#555; font-size:11px;")
        form.addRow("", ayuda)

        botones = QDialogButtonBox()
        b_probar = botones.addButton("Probar conexión", QDialogButtonBox.ButtonRole.ActionRole)
        b_probar.clicked.connect(self._probar)
        botones.addButton(QDialogButtonBox.StandardButton.Save)
        botones.addButton(QDialogButtonBox.StandardButton.Cancel)
        botones.button(QDialogButtonBox.StandardButton.Save).setText("Guardar")
        botones.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        botones.accepted.connect(self._guardar)
        botones.rejected.connect(self.reject)
        lay.addWidget(botones)

    def _recargar_presets(self, seleccionar: str | None = None) -> None:
        actual = seleccionar or self.preset.currentData()
        self.preset.blockSignals(True)
        self.preset.clear()
        self.preset.addItem("Otro (configuración manual)", None)
        self._presets_usuario = mail.cargar_presets_usuario()
        for nombre in mail.PRESETS_INTEGRADOS:
            self.preset.addItem(nombre, nombre)
        if self._presets_usuario:
            self.preset.insertSeparator(self.preset.count())
            for nombre in self._presets_usuario:
                self.preset.addItem(f"{nombre}  (guardado)", nombre)
        idx = self.preset.findData(actual) if actual else 0
        self.preset.setCurrentIndex(max(idx, 0))
        self.preset.blockSignals(False)
        self._actualizar_boton_borrar()

    def _actualizar_boton_borrar(self) -> None:
        clave = self.preset.currentData()
        self.b_borrar_prov.setEnabled(bool(clave and clave in self._presets_usuario))

    def _aplicar_preset(self) -> None:
        self._actualizar_boton_borrar()
        clave = self.preset.currentData()
        if not clave:
            return
        p = mail.todos_los_presets().get(clave)
        if not p:
            return
        self._aplicando = True
        self.host.setText(p["smtp_host"])
        self.port.setValue(p["smtp_port"])
        idx = self.seguridad.findData(p["smtp_seguridad"])
        self.seguridad.setCurrentIndex(max(idx, 0))
        self._aplicando = False

    def _marcar_manual(self, *_a) -> None:
        if getattr(self, "_aplicando", False):
            return
        if self.preset.currentData() is not None:
            self.preset.blockSignals(True)
            self.preset.setCurrentIndex(0)  # "Otro (configuración manual)"
            self.preset.blockSignals(False)
            self._actualizar_boton_borrar()

    def _guardar_preset(self) -> None:
        if not self.host.text().strip():
            QMessageBox.information(self, "Guardar proveedor",
                                   "Escribe primero el servidor SMTP.")
            return
        nombre, ok = QInputDialog.getText(
            self, "Guardar proveedor",
            "Nombre para este proveedor (p. ej. «Correo de mi dominio»):")
        if not ok or not nombre.strip():
            return
        try:
            mail.guardar_preset_usuario(nombre, self.host.text(), self.port.value(),
                                        self.seguridad.currentData())
        except ValueError as e:
            QMessageBox.warning(self, "Guardar proveedor", str(e))
            return
        self._recargar_presets(seleccionar=nombre.strip())

    def _borrar_preset(self) -> None:
        clave = self.preset.currentData()
        if not clave or clave not in self._presets_usuario:
            return
        if QMessageBox.question(self, "Eliminar proveedor",
                                f"¿Quitar «{clave}» de la lista?") \
                == QMessageBox.StandardButton.Yes:
            mail.eliminar_preset_usuario(clave)
            self._recargar_presets(seleccionar=None)

    def _sync_puerto(self) -> None:
        seg = self.seguridad.currentData()
        if seg == "ssl" and self.port.value() == 587:
            self.port.setValue(465)
        elif seg == "starttls" and self.port.value() == 465:
            self.port.setValue(587)

    def _config_actual(self) -> mail.ConfigCorreo:
        return mail.ConfigCorreo(
            host=self.host.text().strip(),
            port=self.port.value(),
            seguridad=self.seguridad.currentData(),
            usuario=self.usuario.text().strip(),
            password=self.password.text(),
            remitente=self.remitente.text().strip() or self.usuario.text().strip(),
            nombre_remitente=self.repo.get_empresa()["nombre"],
            asunto=self.asunto.text().strip() or mail.ASUNTO_DEFECTO,
            cuerpo=self.cuerpo.toPlainText().strip() or mail.CUERPO_DEFECTO,
        )

    def _probar(self) -> None:
        self.setCursor(Qt.CursorShape.WaitCursor)
        try:
            mail.probar_conexion(self._config_actual())
        except Exception as e:  # noqa: BLE001
            self.unsetCursor()
            QMessageBox.warning(self, "Prueba de conexión", str(e))
            return
        self.unsetCursor()
        QMessageBox.information(self, "Prueba de conexión",
                               "Conexión correcta. El correo está listo para enviar.")

    def _guardar(self) -> None:
        cfg = self._config_actual()
        self.repo.save_empresa({
            "smtp_host": cfg.host,
            "smtp_port": cfg.port,
            "smtp_seguridad": cfg.seguridad,
            "smtp_usuario": cfg.usuario,
            "smtp_password": mail.guardar_password(cfg.usuario, cfg.password),
            "smtp_remitente": cfg.remitente,
            "email_asunto": cfg.asunto,
            "email_cuerpo": cfg.cuerpo,
        })
        self.accept()


class _EnvioWorker(QObject):
    terminado = Signal()
    fallo = Signal(str)

    def __init__(self, config, destinatarios, asunto, cuerpo, adjuntos) -> None:
        super().__init__()
        self._args = (config, destinatarios, asunto, cuerpo, adjuntos)

    def run(self) -> None:
        try:
            mail.enviar(*self._args)
        except Exception as e:  # noqa: BLE001
            self.fallo.emit(str(e))
        else:
            self.terminado.emit()


class EnviarCorreoDialog(QDialog):
    """Compone y envía un documento (PDF ya generado) por correo."""

    def __init__(self, repo: Repository, parent, *, pdf: Path, contexto: dict,
                 destinatario: str = "") -> None:
        super().__init__(parent)
        self.repo = repo
        self.pdf = Path(pdf)
        self.setWindowTitle("Enviar por correo")
        self.setMinimumWidth(560)
        self._hilo: QThread | None = None

        cfg = mail.ConfigCorreo.desde_empresa(repo.get_empresa())
        self._config = cfg

        lay = QVBoxLayout(self)
        form = QFormLayout()
        lay.addLayout(form)

        self.para = QLineEdit(destinatario)
        self.para.setPlaceholderText("varias direcciones separadas por comas")
        self.asunto = QLineEdit(mail.aplicar_plantilla(cfg.asunto, contexto))
        self.cuerpo = QPlainTextEdit(mail.aplicar_plantilla(cfg.cuerpo, contexto))
        self.cuerpo.setFixedHeight(180)

        form.addRow("Para", self.para)
        form.addRow("Asunto", self.asunto)
        form.addRow("Mensaje", self.cuerpo)
        form.addRow("Adjunto", QLabel(f"📎 {self.pdf.name}"))
        form.addRow("Enviado desde", QLabel(cfg.remitente or "(sin configurar)"))

        self.estado = QLabel()
        self.estado.setStyleSheet("color:#555;")
        lay.addWidget(self.estado)

        self.botones = QDialogButtonBox()
        self.b_enviar = self.botones.addButton("Enviar", QDialogButtonBox.ButtonRole.AcceptRole)
        self.b_enviar.setProperty("primary", "true")
        self.botones.addButton(QDialogButtonBox.StandardButton.Cancel)
        self.botones.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        self.b_enviar.clicked.connect(self._enviar)
        self.botones.rejected.connect(self.reject)
        lay.addWidget(self.botones)

        if not cfg.configurado:
            self.estado.setText("⚠  El correo no está configurado. "
                                "Ve a Archivo → Configurar correo electrónico.")
            self.b_enviar.setEnabled(False)

    def _enviar(self) -> None:
        destinatarios = [d.strip() for d in self.para.text().split(",") if d.strip()]
        if not destinatarios:
            QMessageBox.warning(self, "Falta el destinatario",
                                "Escribe al menos una dirección de correo.")
            return
        self.b_enviar.setEnabled(False)
        self.estado.setText("Enviando…")
        self.setCursor(Qt.CursorShape.WaitCursor)

        self._hilo = QThread(self)
        self._worker = _EnvioWorker(self._config, destinatarios,
                                    self.asunto.text().strip(),
                                    self.cuerpo.toPlainText(), [self.pdf])
        self._worker.moveToThread(self._hilo)
        self._hilo.started.connect(self._worker.run)
        self._worker.terminado.connect(self._ok)
        self._worker.fallo.connect(self._error)
        self._hilo.start()

    def _cerrar_hilo(self) -> None:
        self.unsetCursor()
        if self._hilo:
            self._hilo.quit()
            self._hilo.wait(3000)
            self._hilo = None

    def _ok(self) -> None:
        self._cerrar_hilo()
        QMessageBox.information(self, "Correo enviado",
                               "El documento se ha enviado correctamente.")
        self.accept()

    def _error(self, mensaje: str) -> None:
        self._cerrar_hilo()
        self.estado.setText("")
        self.b_enviar.setEnabled(True)
        QMessageBox.critical(self, "No se pudo enviar", mensaje)

    def reject(self) -> None:  # noqa: D102
        if self._hilo and self._hilo.isRunning():
            return  # no cerrar mientras se envía
        super().reject()
