"""Datos iniciales: configuración del taller (opcional) y catálogo de artículos ejemplo.

Los datos concretos de un taller NO están en el código: se leen de
``taller/resources/preconfig.json`` si existe. Bórralo o edítalo para otro taller.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from . import domain
from .paths import data_dir
from .repository import Repository

_RECURSOS = Path(__file__).resolve().parent / "resources"
_PRECONFIG = _RECURSOS / "preconfig.json"

_CAMPOS_EMPRESA = ("nombre", "nif", "direccion", "cp", "poblacion", "provincia",
                   "telefono", "email", "iban", "iva_defecto", "impuesto_nombre",
                   "anticipo_pct", "pie_documento")


def hay_preconfiguracion() -> bool:
    return _PRECONFIG.is_file()


def _cargar_preconfig() -> dict:
    try:
        return json.loads(_PRECONFIG.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def instalar_logo(nombre: str = "logo.png") -> str:
    """Copia el logo indicado (en recursos) a la carpeta de datos y devuelve su ruta."""
    origen = _RECURSOS / nombre
    if not origen.is_file():
        return ""
    destino = data_dir() / origen.name
    try:
        if not destino.is_file():
            shutil.copyfile(origen, destino)
    except OSError:
        return str(origen)
    return str(destino)


def precargar_taller(repo: Repository) -> bool:
    """Aplica la configuración inicial (preconfig.json) y los textos de condiciones.

    Devuelve True si había una preconfiguración con datos de empresa.
    """
    pre = _cargar_preconfig()
    empresa = pre.get("empresa", {}) if isinstance(pre, dict) else {}

    datos = {c: empresa[c] for c in _CAMPOS_EMPRESA if c in empresa}
    anticipo = float(datos.get("anticipo_pct", 50.0) or 50.0)
    if pre.get("logo"):
        datos["logo_path"] = instalar_logo(str(pre["logo"]))

    conds = domain.condiciones_por_defecto(anticipo)
    datos["cond_presupuesto"] = conds[domain.PRESUPUESTO]
    datos["cond_orden"] = conds[domain.ORDEN]
    datos["cond_albaran"] = conds[domain.ALBARAN]
    datos["cond_factura"] = conds[domain.FACTURA]

    repo.save_empresa(datos)
    return bool(empresa.get("nombre"))

ARTICULOS_EJEMPLO = [
    ("MO-01", "Hora de mano de obra - Mecánica", "mano_obra", 45.0),
    ("MO-02", "Hora de mano de obra - Electricidad", "mano_obra", 50.0),
    ("MO-03", "Hora de mano de obra - Chapa y pintura", "mano_obra", 48.0),
    ("MO-04", "Diagnosis electrónica", "mano_obra", 40.0),
    ("SRV-01", "Cambio de aceite y filtro", "mano_obra", 35.0),
    ("SRV-02", "Sustitución de filtro de aire", "mano_obra", 12.0),
    ("SRV-03", "Sustitución de filtro de habitáculo", "mano_obra", 15.0),
    ("SRV-04", "Cambio de pastillas de freno (eje)", "mano_obra", 40.0),
    ("SRV-05", "Cambio de discos y pastillas (eje)", "mano_obra", 60.0),
    ("SRV-06", "Sustitución de kit de distribución", "mano_obra", 220.0),
    ("SRV-07", "Cambio de neumático (por unidad)", "mano_obra", 12.0),
    ("SRV-08", "Equilibrado de rueda", "mano_obra", 8.0),
    ("SRV-09", "Alineación de dirección", "mano_obra", 40.0),
    ("SRV-10", "Carga de aire acondicionado", "mano_obra", 55.0),
    ("SRV-11", "Pre-ITV / revisión pre-inspección", "mano_obra", 30.0),
    ("MAT-01", "Aceite motor 5W30 (litro)", "material", 9.5),
    ("MAT-02", "Aceite motor 5W40 (litro)", "material", 9.0),
    ("MAT-03", "Líquido de frenos DOT4 (litro)", "material", 8.0),
    ("MAT-04", "Anticongelante / refrigerante (litro)", "material", 6.5),
    ("MAT-05", "Limpiaparabrisas (juego)", "material", 18.0),
    ("MAT-06", "Batería 12V 60Ah", "material", 85.0),
    ("MAT-07", "Bombilla H7", "material", 6.0),
    ("MAT-08", "Consumibles y material de taller", "material", 5.0),
]


def cargar_articulos_ejemplo(repo: Repository) -> int:
    """Inserta los artículos de ejemplo que aún no existan (por código). Devuelve cuántos añadió."""
    existentes = {a["codigo"] for a in repo.list_articulos(solo_activos=False) if a["codigo"]}
    iva = repo.iva_defecto()
    añadidos = 0
    for codigo, descripcion, tipo, precio in ARTICULOS_EJEMPLO:
        if codigo in existentes:
            continue
        repo.save_articulo({
            "codigo": codigo, "descripcion": descripcion, "tipo": tipo,
            "precio": precio, "iva_pct": iva, "activo": 1,
        })
        añadidos += 1
    return añadidos
