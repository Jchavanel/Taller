"""Mientras la app está abierta, pregunta cada cierto tiempo si el mecánico ha
cambiado el estado de algún vehículo desde el panel del móvil (Seguimiento online →
panel), y lo aplica a la orden de trabajo local. Sigue el mismo patrón que
``actualizador.py``: un ``QThread`` para la parte de red, resultado aplicado a la base
de datos y a la interfaz desde el hilo principal.
"""
from __future__ import annotations

import threading

from PySide6.QtCore import QObject, QThread, QTimer, Signal

from .. import seguimiento_cliente

_INTERVALO_MS = 45_000


class _HiloConsultar(QThread):
    listo = Signal(list)

    def __init__(self, url: str, api_key: str, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._url = url
        self._api_key = api_key

    def run(self) -> None:
        self.listo.emit(seguimiento_cliente.consultar_cambios(self._url, self._api_key))


class GestorSeguimiento(QObject):
    def __init__(self, ventana) -> None:
        super().__init__(ventana)
        self.ventana = ventana
        self._hilo: _HiloConsultar | None = None
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.comprobar)
        self._timer.start(_INTERVALO_MS)

    def comprobar(self) -> None:
        if self._hilo is not None:
            return
        empresa = self.ventana.repo.get_empresa()
        if not seguimiento_cliente.configurado(empresa):
            return
        url = empresa["seguimiento_url"].strip().rstrip("/")
        api_key = empresa["seguimiento_api_key"].strip()
        self._hilo = _HiloConsultar(url, api_key, self)
        self._hilo.listo.connect(self._con_cambios)
        self._hilo.finished.connect(self._limpiar)
        self._hilo.start()

    def _limpiar(self) -> None:
        self._hilo = None

    def _con_cambios(self, cambios: list) -> None:
        if not cambios:
            return
        from .documento_editor import DocumentoEditor

        aplicados = []
        for cambio in cambios:
            token = cambio.get("token") or ""
            nuevo = seguimiento_cliente.ESTADO_INTERNO_DESDE_CLIENTE.get(cambio.get("estado"))
            doc = self.ventana.repo.get_documento_por_token(token) if token else None
            if doc is not None and nuevo:
                self.ventana.repo.aplicar_cambio_remoto(doc["id"], nuevo)
                editor = DocumentoEditor.abierto_para(doc["id"])
                if editor is not None:
                    editor.aplicar_estado_remoto(nuevo)
            if "id" in cambio:
                aplicados.append(cambio["id"])

        if aplicados:
            empresa = self.ventana.repo.get_empresa()
            url = empresa["seguimiento_url"].strip().rstrip("/")
            api_key = empresa["seguimiento_api_key"].strip()
            threading.Thread(
                target=seguimiento_cliente.confirmar_cambios,
                args=(url, api_key, aplicados), daemon=True,
            ).start()

        self.ventana.tab_documentos.refrescar_todo()
