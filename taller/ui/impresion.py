"""Vista previa e impresión directa de los PDF generados."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRectF, QSize
from PySide6.QtGui import QPageSize, QPainter
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPrintSupport import QPrinter, QPrintPreviewDialog
from PySide6.QtWidgets import QMessageBox

_MAX_DPI = 300  # suficiente para A4; más resolución dispara el consumo de memoria


def _render_en_impresora(doc: QPdfDocument, printer: QPrinter) -> None:
    painter = QPainter(printer)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    dpi = min(printer.resolution() or _MAX_DPI, _MAX_DPI)
    for i in range(doc.pageCount()):
        if i > 0:
            printer.newPage()
        pt = doc.pagePointSize(i)
        img = doc.render(
            i, QSize(max(1, round(pt.width() / 72.0 * dpi)),
                     max(1, round(pt.height() / 72.0 * dpi))))
        if img.isNull():
            continue
        destino = printer.pageRect(QPrinter.Unit.DevicePixel)
        escala = min(destino.width() / img.width(), destino.height() / img.height())
        w, h = img.width() * escala, img.height() * escala
        x = destino.x() + (destino.width() - w) / 2
        y = destino.y() + (destino.height() - h) / 2
        painter.drawImage(QRectF(x, y, w, h), img)
    painter.end()


def previsualizar_e_imprimir(parent, ruta_pdf: Path | str, titulo: str = "Documento") -> bool:
    """Abre una ventana de vista previa desde la que se puede imprimir.

    El PDF ya generado se muestra tal cual; la ventana incluye zoom, navegación de
    páginas, selección de impresora y «Imprimir a PDF». Devuelve False si no se pudo
    cargar el PDF.
    """
    ruta_pdf = Path(ruta_pdf)
    dlg = QPrintPreviewDialog(parent)
    doc = QPdfDocument(dlg)  # ligado al diálogo: se libera al cerrarlo
    if doc.load(str(ruta_pdf)) != QPdfDocument.Error.None_ or doc.pageCount() == 0:
        QMessageBox.critical(parent, "Impresión",
                             "No se ha podido abrir el documento para imprimir.")
        dlg.deleteLater()
        return False

    printer = dlg.printer()
    printer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    printer.setDocName(titulo)

    dlg.setWindowTitle(f"Vista previa e impresión — {titulo}")
    dlg.paintRequested.connect(lambda pr: _render_en_impresora(doc, pr))
    dlg.resize(940, 1000)
    dlg.exec()
    dlg.deleteLater()
    return True
