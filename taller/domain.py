"""Lógica de negocio: tipos de documento, cálculo de totales y numeración."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

_CENT = Decimal("0.01")
_CIEN = Decimal(100)

# Tipos de documento y su orden en el flujo de trabajo del taller.
PRESUPUESTO = "presupuesto"
ORDEN = "orden"
ALBARAN = "albaran"
FACTURA = "factura"

TIPOS = [PRESUPUESTO, ORDEN, ALBARAN, FACTURA]

TIPO_NOMBRE = {
    PRESUPUESTO: "Presupuesto",
    ORDEN: "Orden de trabajo",
    ALBARAN: "Albarán",
    FACTURA: "Factura",
}

TIPO_PREFIJO = {
    PRESUPUESTO: "PRE",
    ORDEN: "OT",
    ALBARAN: "ALB",
    FACTURA: "FAC",
}

# Conversiones permitidas: de qué tipo se puede pasar a qué tipo(s).
CONVERSIONES = {
    PRESUPUESTO: [ORDEN, ALBARAN, FACTURA],
    ORDEN: [ALBARAN, FACTURA],
    ALBARAN: [FACTURA],
    FACTURA: [],
}

ESTADOS = ["abierto", "aprobado", "rechazado", "en curso", "finalizado",
           "facturado", "cobrado", "anulado"]

# Un presupuesto deja de estar "en curso" cuando se aprueba (pasa a orden), se
# rechaza o avanza en el flujo. Una orden, cuando se termina o se factura.
CERRADO_PRESUPUESTO = ("aprobado", "rechazado", "finalizado", "facturado",
                       "cobrado", "anulado")
CERRADO_ORDEN = ("finalizado", "facturado", "cobrado", "anulado")

LINEA_MATERIAL = "material"
LINEA_MANO_OBRA = "mano_obra"

# Tipos de intervención del historial del vehículo.
INTERVENCION_TIPOS = {
    "mantenimiento": "Mantenimiento",
    "reparacion": "Reparación",
    "revision": "Revisión / diagnóstico",
    "itv": "ITV / pre-ITV",
    "neumaticos": "Neumáticos",
    "garantia": "Garantía",
    "otro": "Otro",
}

# Al pasar un documento al historial, tipo de intervención sugerido según el documento.
TIPO_DOC_A_INTERVENCION = {
    ORDEN: "reparacion",
    ALBARAN: "reparacion",
    FACTURA: "reparacion",
    PRESUPUESTO: "revision",
}

TIPO_LINEA_NOMBRE = {
    LINEA_MATERIAL: "Material",
    LINEA_MANO_OBRA: "Mano de obra",
}


def _dec(x) -> Decimal:
    """Convierte a Decimal de forma segura (pasando por str para no arrastrar el ruido del float)."""
    if isinstance(x, Decimal):
        return x
    try:
        return Decimal(str(x if x is not None else 0))
    except (InvalidOperation, ValueError):
        return Decimal(0)


def _q2(x: Decimal) -> Decimal:
    """Cuantiza a 2 decimales con redondeo comercial (mitad hacia arriba)."""
    return x.quantize(_CENT, rounding=ROUND_HALF_UP)


def _r2(x) -> float:
    """Redondeo a 2 decimales (céntimos). Devuelve float para almacenar/formatear."""
    return float(_q2(_dec(x)))


@dataclass
class LineaCalc:
    descripcion: str = ""
    cantidad: float = 1.0
    precio: float = 0.0
    descuento_pct: float = 0.0
    iva_pct: float = 21.0
    tipo: str = LINEA_MATERIAL
    codigo: str = ""

    def base_dec(self) -> Decimal:
        bruto = _dec(self.cantidad) * _dec(self.precio)
        return _q2(bruto * (Decimal(1) - _dec(self.descuento_pct) / _CIEN))

    @property
    def base(self) -> float:
        return float(self.base_dec())


@dataclass
class TotalesDoc:
    base: float = 0.0
    cuota_iva: float = 0.0
    total: float = 0.0
    # desglose por tipo de IVA: {iva_pct: (base, cuota)}
    desglose: dict = field(default_factory=dict)


def calcular_totales(lineas: list[LineaCalc], descuento_general_pct: float = 0.0) -> TotalesDoc:
    """Calcula base, IVA y total agrupando por tipo impositivo.

    El descuento general se aplica proporcionalmente a la base de cada línea
    antes de calcular la cuota de IVA correspondiente.
    """
    factor = Decimal(1) - _dec(descuento_general_pct) / _CIEN
    grupos: dict[float, Decimal] = {}
    for ln in lineas:
        # base de línea redondeada, luego se aplica el descuento general y se re-redondea
        b = _q2(ln.base_dec() * factor)
        rate = round(float(ln.iva_pct), 2)
        grupos[rate] = grupos.get(rate, Decimal(0)) + b

    total_base = Decimal(0)
    total_cuota = Decimal(0)
    desglose = {}
    for iva_pct, base in sorted(grupos.items()):
        cuota = _q2(base * _dec(iva_pct) / _CIEN)
        desglose[iva_pct] = (float(base), float(cuota))
        total_base += base
        total_cuota += cuota

    return TotalesDoc(
        base=float(total_base),
        cuota_iva=float(total_cuota),
        total=float(total_base + total_cuota),
        desglose=desglose,
    )


def formatear_numero(tipo: str, anio: int, secuencia: int) -> str:
    return f"{TIPO_PREFIJO[tipo]}-{anio}-{secuencia:04d}"


def condiciones_por_defecto(anticipo_pct: float = 50.0) -> dict:
    """Textos de condiciones iniciales para cada tipo de documento."""
    a = f"{anticipo_pct:g}"
    return {
        PRESUPUESTO: (
            "El cliente declara haber recibido y aceptado el presente presupuesto y "
            "autoriza la realización de los trabajos descritos. "
            f"El inicio de la reparación queda condicionado al abono del anticipo del {a} %. "
            "Cualquier trabajo, avería o material adicional no contemplado deberá ser "
            "comunicado y autorizado previamente por el cliente. El importe restante se "
            "abonará a la finalización de los trabajos, salvo pacto distinto indicado por "
            "escrito. El presupuesto no incluye trabajos ni piezas no detallados."
        ),
        ORDEN: (
            "El cliente autoriza la realización de los trabajos descritos en esta orden de "
            "reparación y declara haber sido informado de su alcance y coste estimado. "
            "Cualquier trabajo, avería o material adicional no contemplado deberá ser "
            "comunicado y autorizado previamente. El vehículo permanecerá en el taller "
            "hasta el abono total de la reparación."
        ),
        ALBARAN: (
            "El cliente recibe el vehículo y declara su conformidad con los trabajos "
            "realizados y el material entregado que se detallan en el presente documento. "
            "Documento sin valor fiscal; la factura se emitirá por separado."
        ),
        FACTURA: (
            "Factura emitida conforme a la normativa vigente. Salvo indicación en "
            "contrario, el pago se realizará al contado a la recepción de la factura. "
            "Los trabajos realizados tienen la garantía legal aplicable."
        ),
    }


def importe_anticipo(total: float, anticipo_pct: float) -> tuple[float, float]:
    """Devuelve (importe del anticipo, importe pendiente)."""
    ant = _r2(_dec(total) * _dec(anticipo_pct) / _CIEN)
    return ant, _r2(_dec(total) - _dec(ant))


def con_impuesto(base: float, impuesto_pct: float) -> float:
    """Precio con el impuesto incluido, redondeado a céntimos."""
    return _r2(_dec(base) * (Decimal(1) + _dec(impuesto_pct) / _CIEN))


def formato_moneda(x: float) -> str:
    """Formato español: 1.234,56 €"""
    s = f"{x:,.2f}"
    s = s.replace(",", "_").replace(".", ",").replace("_", ".")
    return f"{s} €"
