"""Mientras la app está abierta, pregunta cada cierto tiempo si desde el panel del
móvil (Seguimiento online → panel) se ha cambiado el estado de algún vehículo o se
ha dado de alta una orden nueva, y lo aplica en local. Sigue el mismo patrón que
``actualizador.py``: un ``QThread`` por cada consulta de red, resultado aplicado a la
base de datos y a la interfaz desde el hilo principal.
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


class _HiloConsultarOrdenes(QThread):
    listo = Signal(list)

    def __init__(self, url: str, api_key: str, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._url = url
        self._api_key = api_key

    def run(self) -> None:
        self.listo.emit(seguimiento_cliente.consultar_ordenes_nuevas(self._url, self._api_key))


class GestorSeguimiento(QObject):
    def __init__(self, ventana) -> None:
        super().__init__(ventana)
        self.ventana = ventana
        self._hilo: _HiloConsultar | None = None
        self._hilo_ordenes: _HiloConsultarOrdenes | None = None
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.comprobar)
        self._timer.start(_INTERVALO_MS)

    def comprobar(self) -> None:
        empresa = self.ventana.repo.get_empresa()
        if not seguimiento_cliente.configurado(empresa):
            return
        url = empresa["seguimiento_url"].strip().rstrip("/")
        api_key = empresa["seguimiento_api_key"].strip()

        if self._hilo is None:
            self._hilo = _HiloConsultar(url, api_key, self)
            self._hilo.listo.connect(self._con_cambios)
            self._hilo.finished.connect(self._limpiar)
            self._hilo.start()

        if self._hilo_ordenes is None:
            self._hilo_ordenes = _HiloConsultarOrdenes(url, api_key, self)
            self._hilo_ordenes.listo.connect(self._con_ordenes_nuevas)
            self._hilo_ordenes.finished.connect(self._limpiar_ordenes)
            self._hilo_ordenes.start()

    def _limpiar(self) -> None:
        self._hilo = None

    def _limpiar_ordenes(self) -> None:
        self._hilo_ordenes = None

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

    def _con_ordenes_nuevas(self, ordenes: list) -> None:
        if not ordenes:
            return
        aplicadas = []
        creadas = []
        for orden in ordenes:
            try:
                self.ventana.repo.crear_orden_desde_movil(orden)
                creadas.append(orden)
            except Exception:  # noqa: BLE001
                from ..errores import log
                log().exception("No se pudo crear la orden recibida del móvil: %r", orden)
                continue
            if "id" in orden:
                aplicadas.append(orden["id"])

        if aplicadas:
            empresa = self.ventana.repo.get_empresa()
            url = empresa["seguimiento_url"].strip().rstrip("/")
            api_key = empresa["seguimiento_api_key"].strip()
            threading.Thread(
                target=seguimiento_cliente.confirmar_ordenes_nuevas,
                args=(url, api_key, aplicadas), daemon=True,
            ).start()

        if creadas:
            self.ventana.tab_documentos.refrescar_todo()
            if hasattr(self.ventana, "statusBar"):
                resumen = ", ".join(
                    (o.get("matricula") or "").strip() or "(sin matrícula)" for o in creadas)
                self.ventana.statusBar().showMessage(
                    f"Nueva{'s' if len(creadas) > 1 else ''} orden{'es' if len(creadas) > 1 else ''} "
                    f"desde el móvil: {resumen}", 10000)
