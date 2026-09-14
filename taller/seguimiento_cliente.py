"""Sincroniza el estado de las órdenes de trabajo con el portal de seguimiento del
cliente (app web instalable con notificaciones push).

Totalmente opcional: si no está activado en Ajustes → Datos de mi taller, o si falla
la conexión (sin internet en el taller, portal caído...), no se envía nada y la
aplicación sigue funcionando con normalidad. Nunca lanza una excepción hacia quien
llama ni bloquea la interfaz (el envío se hace en un hilo aparte).
"""
from __future__ import annotations

import json
import logging
import secrets
import threading
import urllib.error
import urllib.request

from . import domain

logger = logging.getLogger(__name__)

# Estados de una orden que el cliente ve como "vehículo listo para recoger": al
# entrar en uno de ellos se dispara la notificación push (no solo la actualización
# silenciosa de estado).
ESTADOS_LISTO = ("finalizado",)

# Traducción del estado interno de la orden al estado que ve el cliente en el portal.
ESTADO_CLIENTE = {
    "abierto": "recibido",
    "aprobado": "recibido",
    "en curso": "en_reparacion",
    "finalizado": "listo",
    "facturado": "entregado",
    "cobrado": "entregado",
    "rechazado": "cancelado",
    "anulado": "cancelado",
}

# Traducción inversa: el mecánico solo mueve la orden entre estos tres estados desde
# el panel del móvil (entregar/facturar/anular son pasos de facturación y se quedan
# en el programa de escritorio).
ESTADO_INTERNO_DESDE_CLIENTE = {
    "recibido": "aprobado",
    "en_reparacion": "en curso",
    "listo": "finalizado",
}


def generar_token() -> str:
    """Identificador público del vehículo/orden en el portal (va en la URL, sin login)."""
    return secrets.token_urlsafe(16)


def configurado(empresa_row) -> bool:
    return bool(
        empresa_row["seguimiento_activo"]
        and (empresa_row["seguimiento_url"] or "").strip()
        and (empresa_row["seguimiento_api_key"] or "").strip()
    )


def sincronizar(repo, documento_id: int, *, notificar: bool = False,
                estado_override: str | None = None) -> None:
    """Envía el estado actual de una orden al portal de seguimiento, en segundo plano.

    ``notificar=True`` además pide al portal que avise por notificación push al
    cliente (se usa cuando la orden acaba de pasar a un estado de ``ESTADOS_LISTO``).
    ``estado_override`` fuerza el estado que ve el cliente en vez de traducir el
    estado interno de la orden (se usa al borrar una orden: en ese instante el
    documento todavía existe para poder leer matrícula/cliente, pero el estado que
    debe ver el cliente es "cancelado", no el que tuviera la orden).
    """
    empresa = repo.get_empresa()
    if not configurado(empresa):
        return
    doc = repo.get_documento(documento_id)
    if doc is None or doc["tipo"] != domain.ORDEN or not doc["seguimiento_token"]:
        return
    vehiculo = repo.get_vehiculo(doc["vehiculo_id"]) if doc["vehiculo_id"] else None
    cliente = repo.get_cliente(doc["cliente_id"]) if doc["cliente_id"] else None
    payload = {
        "token": doc["seguimiento_token"],
        "matricula": (vehiculo["matricula"] if vehiculo else "") or "",
        "marca": (vehiculo["marca"] if vehiculo else "") or "",
        "modelo": (vehiculo["modelo"] if vehiculo else "") or "",
        "cliente_nombre": (cliente["nombre"] if cliente else "") or "",
        "estado": estado_override or ESTADO_CLIENTE.get(doc["estado"], "en_reparacion"),
        "entrega_prevista": doc["entrega_prevista"] or None,
        "taller_nombre": (empresa["nombre"] or "").strip(),
        "notificar": bool(notificar),
    }
    url = empresa["seguimiento_url"].strip().rstrip("/") + "/api/sync"
    api_key = empresa["seguimiento_api_key"].strip()
    threading.Thread(target=_enviar, args=(url, api_key, payload), daemon=True).start()


def _enviar(url: str, api_key: str, payload: dict) -> None:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": "application/json", "x-api-key": api_key},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        logger.warning("No se pudo sincronizar el seguimiento del cliente: %s", e)


# ------------------------------------------------------------- cambios remotos
# El mecánico también puede cambiar el estado de un vehículo, o dar de alta una orden
# nueva, desde el panel del móvil (el panel usa su propia contraseña, no toca los
# ajustes del taller). La app de escritorio pregunta periódicamente si hay algo
# pendiente y lo aplica en local; ver ui/seguimiento_poller.py.

def _consultar(url: str, api_key: str, ruta: str, campo: str) -> list[dict]:
    """Llamada de red pura (sin tocar la base de datos): pensada para ejecutarse en
    un hilo aparte. Devuelve ``[]`` si falla, nunca lanza."""
    req = urllib.request.Request(
        url.rstrip("/") + ruta, headers={"x-api-key": api_key})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return list(data.get(campo) or [])
    except (urllib.error.URLError, OSError, TimeoutError, ValueError) as e:
        logger.warning("No se pudo consultar %s: %s", ruta, e)
        return []


def _confirmar(url: str, api_key: str, ruta: str, ids: list) -> None:
    """Mejor esfuerzo: si falla, se reintenta solo (se volverán a recibir y aplicar
    en la siguiente consulta, sin efecto negativo)."""
    if not ids:
        return
    body = json.dumps({"ids": ids}).encode("utf-8")
    req = urllib.request.Request(
        url.rstrip("/") + ruta, data=body, method="POST",
        headers={"Content-Type": "application/json", "x-api-key": api_key},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        logger.warning("No se pudo confirmar %s: %s", ruta, e)


def consultar_cambios(url: str, api_key: str) -> list[dict]:
    """Cambios de estado pendientes hechos desde el panel del móvil."""
    return _consultar(url, api_key, "/api/cambios", "cambios")


def confirmar_cambios(url: str, api_key: str, ids: list) -> None:
    return _confirmar(url, api_key, "/api/cambios/confirmar", ids)


def consultar_ordenes_nuevas(url: str, api_key: str) -> list[dict]:
    """Altas rápidas de orden de trabajo pendientes, hechas desde el panel del móvil
    (matrícula, cliente, qué le pasa — sin líneas ni precios)."""
    return _consultar(url, api_key, "/api/ordenes-nuevas", "ordenes")


def confirmar_ordenes_nuevas(url: str, api_key: str, ids: list) -> None:
    return _confirmar(url, api_key, "/api/ordenes-nuevas/confirmar", ids)
