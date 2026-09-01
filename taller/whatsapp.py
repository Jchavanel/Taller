"""Mensaje de WhatsApp al cliente tras emitir una factura, con enlace a reseñas de Google.

No usa la API de WhatsApp Business (de pago, con alta en Meta): genera un enlace
``https://wa.me/<numero>?text=...`` que abre WhatsApp (app de escritorio o WhatsApp Web)
con el número y el mensaje ya escritos. El usuario solo pulsa «Enviar».
"""
from __future__ import annotations

import re
from urllib.parse import quote

from . import domain

PLANTILLA_DEFECTO = (
    "Hola {cliente}, gracias por confiar en {taller}. Tu factura {numero} ya está "
    "lista.\n\n"
    "Si has quedado a gusto con el servicio, nos ayudarías muchísimo dejando una reseña "
    "en Google (te lleva un minuto):\n{resenas_url}\n\n"
    "¡Gracias y hasta la próxima!"
)


def plantilla_por_defecto() -> str:
    return PLANTILLA_DEFECTO


def normalizar_telefono(telefono: str, prefijo: str = "34") -> str | None:
    """Devuelve el número en formato internacional sin '+' (p. ej. 34612345678), o None."""
    prefijo = re.sub(r"\D", "", prefijo or "") or "34"
    d = re.sub(r"\D", "", telefono or "")
    if not d:
        return None
    if d.startswith("00"):
        d = d[2:]
    if len(d) == 9:                       # número nacional -> añadir prefijo
        return prefijo + d
    if len(d) > 9:                        # ya parece llevar prefijo internacional
        return d
    return None                          # demasiado corto para ser válido


def contexto_factura(doc_row, cliente_row, empresa_row) -> dict:
    return {
        "cliente": (cliente_row["nombre"] if cliente_row else "").strip() or "cliente",
        "numero": doc_row["numero"],
        "fecha": doc_row["fecha"],
        "total": domain.formato_moneda(doc_row["total"]),
        "taller": (empresa_row["nombre"] if empresa_row else "").strip(),
        "telefono": (empresa_row["telefono"] if empresa_row else "").strip(),
        "resenas_url": (empresa_row["resenas_url"] if empresa_row else "").strip(),
    }


def aplicar_plantilla(plantilla: str, contexto: dict) -> str:
    try:
        return plantilla.format(**contexto)
    except (KeyError, IndexError, ValueError):
        return plantilla


def construir_enlace(telefono: str, texto: str, prefijo: str = "34") -> str | None:
    numero = normalizar_telefono(telefono, prefijo)
    if not numero:
        return None
    return f"https://wa.me/{numero}?text={quote(texto)}"
