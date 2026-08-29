"""Pantalla de carga inicial."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QApplication, QSplashScreen

from .. import APP_NAME, __version__
from . import theme

_RECURSOS = Path(__file__).resolve().parent.parent / "resources"


def _pixmap(tema: str) -> QPixmap:
    w, h = 560, 320
    escala = 2  # nitidez en pantallas HiDPI
    pm = QPixmap(w * escala, h * escala)
    pm.setDevicePixelRatio(escala)
    pm.fill(Qt.GlobalColor.transparent)

    c_bg = QColor(theme.color(tema, "surface"))
    c_border = QColor(theme.color(tema, "border"))
    c_text = QColor(theme.color(tema, "text"))
    c_muted = QColor(theme.color(tema, "text_muted"))
    c_accent = QColor(theme.color(tema, "accent"))

    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    tarjeta = QRectF(12, 12, w - 24, h - 24)
    ruta = QPainterPath()
    ruta.addRoundedRect(tarjeta, 20, 20)
    p.fillPath(ruta, c_bg)
    p.setPen(c_border)
    p.drawPath(ruta)

    # franja de acento a la izquierda
    barra = QPainterPath()
    barra.addRoundedRect(QRectF(12, 12, 7, h - 24), 3.5, 3.5)
    p.setClipPath(ruta)
    p.fillPath(barra, c_accent)
    p.setClipping(False)

    logo_file = _RECURSOS / "logo_ui.png"
    if not logo_file.is_file():
        logo_file = _RECURSOS / "logo.png"
    if logo_file.is_file():
        logo = QPixmap(str(logo_file))
        if not logo.isNull():
            lw = 288
            lh = int(logo.height() * lw / logo.width())
            p.drawPixmap(QRectF((w - lw) / 2 + 4, 64, lw, lh),
                         logo, QRectF(logo.rect()))

    p.setPen(c_text)
    p.setFont(QFont("Helvetica", 20, QFont.Weight.Bold))
    p.drawText(QRectF(0, 162, w, 38), Qt.AlignmentFlag.AlignHCenter, APP_NAME)

    p.setPen(c_muted)
    p.setFont(QFont("Helvetica", 10))
    p.drawText(QRectF(0, 202, w, 22), Qt.AlignmentFlag.AlignHCenter,
               "Presupuestos · Órdenes · Albaranes · Facturas")

    p.setPen(c_accent)
    p.setFont(QFont("Helvetica", 10, QFont.Weight.Bold))
    p.drawText(QRectF(0, h - 56, w - 34, 20),
               Qt.AlignmentFlag.AlignRight, f"v{__version__}")
    p.end()
    return pm


class Splash(QSplashScreen):
    def __init__(self, tema: str) -> None:
        super().__init__(_pixmap(tema))
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._tema = tema

    def estado(self, texto: str) -> None:
        self.showMessage(
            "   " + texto,
            Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignLeft,
            QColor(theme.color(self._tema, "text_muted")),
        )
        QApplication.processEvents()
