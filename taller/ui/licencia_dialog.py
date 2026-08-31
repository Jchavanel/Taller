"""Diálogo de licencia: ver el estado, activar una licencia y copiar la huella del equipo."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from .. import licencia as lic


class LicenciaDialog(QDialog):
    def __init__(self, repo, parent=None) -> None:
        super().__init__(parent)
        self.repo = repo
        self.setWindowTitle("Licencia del programa")
        self.setMinimumWidth(560)
        self._cambiada = False

        root = QVBoxLayout(self)

        self.lbl_estado = QLabel()
        self.lbl_estado.setWordWrap(True)
        self.lbl_estado.setTextFormat(Qt.TextFormat.RichText)
        root.addWidget(self.lbl_estado)

        # --- activar licencia ---
        caja = QGroupBox("Activar / renovar licencia")
        cl = QVBoxLayout(caja)
        cl.addWidget(QLabel("Pega aquí el código de licencia que te han enviado:"))
        self.txt = QPlainTextEdit()
        self.txt.setPlaceholderText("eyJ…….  (una sola línea)")
        self.txt.setFixedHeight(90)
        cl.addWidget(self.txt)
        b_activar = QPushButton("Activar licencia")
        b_activar.setProperty("primary", "true")
        b_activar.clicked.connect(self._activar)
        cl.addWidget(b_activar, alignment=cl.alignment())
        root.addWidget(caja)

        # --- huella del equipo ---
        fila = QHBoxLayout()
        self.lbl_huella = QLabel(f"Huella de este equipo:  <code>{lic.huella_maquina()}</code>")
        self.lbl_huella.setTextFormat(Qt.TextFormat.RichText)
        b_copiar = QPushButton("Copiar")
        b_copiar.setToolTip("Cópiala y envíala al proveedor para que emita la licencia de "
                            "este equipo")
        b_copiar.clicked.connect(self._copiar_huella)
        fila.addWidget(self.lbl_huella, 1)
        fila.addWidget(b_copiar)
        root.addLayout(fila)

        botones = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        botones.rejected.connect(self.accept)
        root.addWidget(botones)

        self._refrescar_estado()

    # ------------------------------------------------------------------
    def _refrescar_estado(self) -> None:
        e = lic.evaluar(self.repo)
        color = {"ok": "#2e7d32", "aviso": "#a06a00", "bloqueo": "#b3261e"}[e.nivel]
        lineas = []
        if e.codigo == "desactivada":
            lineas.append("El control de licencia está <b>desactivado</b> en esta compilación.")
        else:
            if e.licencia:
                L = e.licencia
                lineas.append(f"Licencia de <b>{L.cliente}</b>"
                              + (f" ({L.nif})" if L.nif else ""))
                lineas.append(f"Válida hasta <b>{L.expira:%d/%m/%Y}</b>")
            titulo = e.titulo or {"activa": "Licencia activa"}.get(e.codigo, "")
            if titulo:
                lineas.append(f'<span style="color:{color}"><b>{titulo}</b></span>')
            if e.detalle:
                lineas.append(e.detalle.replace("\n", "<br>"))
            if not e.puede_operar:
                lineas.append("<i>El programa está en <b>modo consulta</b>: puedes ver, "
                              "imprimir y exportar, pero no crear ni modificar documentos.</i>")
        self.lbl_estado.setText("<br>".join(lineas))

    def _activar(self) -> None:
        try:
            L = lic.guardar_token(self.repo, self.txt.toPlainText())
        except ValueError as ex:
            QMessageBox.warning(self, "Licencia", str(ex))
            return
        self._cambiada = True
        self.txt.clear()
        self._refrescar_estado()
        QMessageBox.information(
            self, "Licencia activada",
            f"Licencia de «{L.cliente}» activada.\nVálida hasta {L.expira:%d/%m/%Y}.")

    def _copiar_huella(self) -> None:
        QApplication.clipboard().setText(lic.huella_maquina())
        QMessageBox.information(self, "Licencia",
                               "Huella del equipo copiada al portapapeles.")

    @property
    def licencia_cambiada(self) -> bool:
        return self._cambiada
