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


def url_seguimiento(empresa_row, token: str) -> str:
    """URL que se le entrega al cliente para ver el estado de su vehículo. Cadena
    vacía si el portal no está configurado."""
    base = (empresa_row["seguimiento_url"] or "").strip().rstrip("/")
    return f"{base}/s/{token}" if base and token else ""


def configurado(empresa_row) -> bool:
    return bool(
        empresa_row["seguimiento_activo"]
        and (empresa_row["seguimiento_url"] or "").strip()
        and (empresa_row["seguimiento_api_key"] or "").strip()
    )


def sincronizar(repo, documento_id: int, *, notificar: bool = False) -> None:
    """Envía el estado actual de una orden al portal de seguimiento, en segundo plano.

    ``notificar=True`` además pide al portal que avise por notificación push al
    cliente (se usa cuando la orden acaba de pasar a un estado de ``ESTADOS_LISTO``).
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
        "estado": ESTADO_CLIENTE.get(doc["estado"], "en_reparacion"),
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
# El mecánico también puede cambiar el estado de un vehículo desde el panel del móvil
# (portal → Ajustes del taller no hace falta tocarlos: el panel usa su propia
# contraseña). La app de escritorio pregunta periódicamente si hay cambios pendientes
# y los aplica a la orden de trabajo local; ver ui/seguimiento_poller.py.

def consultar_cambios(url: str, api_key: str) -> list[dict]:
    """Cambios pendientes hechos desde el panel del móvil. Llamada de red pura (sin
    tocar la base de datos): pensada para ejecutarse en un hilo aparte. Devuelve
    ``[]`` si falla, nunca lanza."""
    req = urllib.request.Request(
        url.rstrip("/") + "/api/cambios", headers={"x-api-key": api_key})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return list(data.get("cambios") or [])
    except (urllib.error.URLError, OSError, TimeoutError, ValueError) as e:
        logger.warning("No se pudieron consultar los cambios del panel del taller: %s", e)
        return []


def confirmar_cambios(url: str, api_key: str, ids: list) -> None:
    """Avisa al portal de que estos cambios ya se han aplicado en local, para que no
    se vuelvan a entregar. Mejor esfuerzo: si falla, se reintenta solo (se volverán a
    recibir y aplicar en la siguiente consulta, sin efecto negativo)."""
    if not ids:
        return
    body = json.dumps({"ids": ids}).encode("utf-8")
    req = urllib.request.Request(
        url.rstrip("/") + "/api/cambios/confirmar", data=body, method="POST",
        headers={"Content-Type": "application/json", "x-api-key": api_key},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        logger.warning("No se pudo confirmar la aplicación de cambios: %s", e)
