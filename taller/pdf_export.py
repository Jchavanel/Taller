"""Generación de PDF para presupuestos, órdenes de trabajo, albaranes y facturas."""
from __future__ import annotations

import datetime as _dt
from pathlib import Path
from xml.sax.saxutils import escape as _xml_escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from . import domain, verifactu
from .paths import documents_dir

# Paleta tomada del modelo del taller (logo rojo, barras oscuras).
_ROJO = colors.HexColor("#ED1C24")
_OSCURO = colors.HexColor("#191B1D")
_BORDE = colors.HexColor("#C9CDD2")
_LABEL = colors.HexColor("#6A6E73")
_LABEL_BG = colors.HexColor("#F1F2F4")
_ROJO_BG = colors.HexColor("#FFF1F2")

# Compatibilidad con las funciones de ficha e historial.
_GRIS = colors.HexColor("#4a4a4a")
_GRIS_CLARO = _LABEL_BG
_LINEA = _BORDE


def _styles() -> dict:
    base = getSampleStyleSheet()
    N = base["Normal"]
    return {
        "normal": ParagraphStyle("n", parent=N, fontSize=8.5, leading=11),
        "small": ParagraphStyle("s", parent=N, fontSize=7.5, leading=9, textColor=_GRIS),
        "empresa": ParagraphStyle("e", parent=N, fontSize=10, leading=13,
                                  fontName="Helvetica-Bold"),
        "titulo": ParagraphStyle("t", parent=N, fontSize=17, leading=20,
                                 fontName="Helvetica-Bold", alignment=2),
        "num": ParagraphStyle("num", parent=N, fontSize=9, leading=12, alignment=2),
        "seccion": ParagraphStyle("sec", parent=N, fontSize=8, fontName="Helvetica-Bold",
                                  textColor=_GRIS, spaceAfter=2),
        "cell": ParagraphStyle("c", parent=N, fontSize=8, leading=10),
        "cellr": ParagraphStyle("cr", parent=N, fontSize=8, leading=10, alignment=2),
        "pie": ParagraphStyle("p", parent=N, fontSize=7.5, leading=10, textColor=_GRIS,
                              alignment=1),
        # --- estilos del formato del taller ---
        "emp_nombre": ParagraphStyle("en", parent=N, fontSize=10.5, leading=13,
                                     fontName="Helvetica-Bold", alignment=2),
        "emp_line": ParagraphStyle("el", parent=N, fontSize=7.7, leading=9.6,
                                   textColor=_LABEL, alignment=2),
        "doc_titulo": ParagraphStyle("dt", parent=N, fontSize=12.5, leading=15,
                                     fontName="Helvetica-Bold"),
        "doc_sub": ParagraphStyle("ds", parent=N, fontSize=8.5, leading=11, textColor=_LABEL),
        "doc_meta": ParagraphStyle("dm", parent=N, fontSize=9, leading=13, alignment=2),
        "bar": ParagraphStyle("bar", parent=N, fontSize=8.5, leading=11,
                              fontName="Helvetica-Bold", textColor=colors.white),
        "lbl": ParagraphStyle("lbl", parent=N, fontSize=7, leading=9,
                              fontName="Helvetica-Bold", textColor=_LABEL),
        "val": ParagraphStyle("v", parent=N, fontSize=9, leading=11),
        "th": ParagraphStyle("th", parent=N, fontSize=8, leading=10,
                             fontName="Helvetica-Bold"),
        "thr": ParagraphStyle("thr", parent=N, fontSize=8, leading=10,
                              fontName="Helvetica-Bold", alignment=2),
        "td": ParagraphStyle("td", parent=N, fontSize=8, leading=10),
        "tdr": ParagraphStyle("tdr", parent=N, fontSize=8, leading=10, alignment=2),
        "cond": ParagraphStyle("cond", parent=N, fontSize=7.3, leading=9.5, textColor=_LABEL),
        "fp": ParagraphStyle("fp", parent=N, fontSize=7.8, leading=11.5,
                             textColor=colors.white),
        "fp_row": ParagraphStyle("fpr", parent=N, fontSize=8.5, leading=11),
        "fp_iban": ParagraphStyle("fpi", parent=N, fontSize=9.5, leading=12,
                                  textColor=colors.white, alignment=1),
        "tot_l": ParagraphStyle("tl", parent=N, fontSize=8.5, leading=11, alignment=2),
        "tot_lb": ParagraphStyle("tlb", parent=N, fontSize=8.5, leading=11, alignment=2,
                                 fontName="Helvetica-Bold"),
        "firma_h": ParagraphStyle("fh", parent=N, fontSize=8, leading=10,
                                  fontName="Helvetica-Bold", alignment=1),
        "firma_f": ParagraphStyle("ff", parent=N, fontSize=7.5, leading=13, textColor=_LABEL),
    }


_SUBTITULO = {
    domain.PRESUPUESTO: "Autorización de trabajos y condiciones de pago",
    domain.ORDEN: "Autorización de trabajos y condiciones de pago",
    domain.ALBARAN: "Entrega del vehículo y detalle de trabajos realizados",
    domain.FACTURA: "Factura de reparación",
}

_TITULO_DOC = {
    domain.PRESUPUESTO: "PRESUPUESTO / ORDEN DE REPARACIÓN",
    domain.ORDEN: "ORDEN DE REPARACIÓN",
    domain.ALBARAN: "ALBARÁN DE ENTREGA",
    domain.FACTURA: "FACTURA",
}

_TOTAL_LBL = {
    domain.PRESUPUESTO: "TOTAL PRESUPUESTO",
    domain.ORDEN: "TOTAL ORDEN",
    domain.ALBARAN: "TOTAL",
    domain.FACTURA: "TOTAL FACTURA",
}


def _fmt_num(x, dec_libres=True) -> str:
    try:
        x = float(x)
    except (TypeError, ValueError):
        return ""
    if x == int(x):
        return str(int(x))
    return f"{x:.2f}".replace(".", ",")


def _fmt_km(x) -> str:
    return f"{int(x):,}".replace(",", ".") if x not in (None, "") else ""


def _esc(texto) -> str:
    """Escapa texto del usuario para meterlo en un Paragraph de reportlab (mini-XML)."""
    return _xml_escape(str(texto if texto is not None else ""))


def _P(texto, estilo, *, multilinea: bool = False) -> Paragraph:
    """Crea un Paragraph escapando el texto (evita que <, & o etiquetas rompan el PDF)."""
    s = _esc(texto)
    if multilinea:
        s = s.replace("\n", "<br/>")
    return Paragraph(s or "&nbsp;", estilo)


def _qr_verifactu(url: str, lado_mm: float = 24):
    """Dibujo del código QR de cotejo de la AEAT."""
    from reportlab.graphics.barcode.qr import QrCodeWidget
    from reportlab.graphics.shapes import Drawing

    widget = QrCodeWidget(url, barLevel="M")
    x0, y0, x1, y1 = widget.getBounds()
    escala = (lado_mm * mm) / (x1 - x0)
    d = Drawing(lado_mm * mm, lado_mm * mm,
                transform=[escala, 0, 0, escala, -x0 * escala, -y0 * escala])
    d.add(widget)
    return d


def _bloque_verifactu(doc_row, empresa_row, ancho: float, st: dict) -> Table:
    nif = (empresa_row["verifactu_nif_productor"] or empresa_row["nif"] or "").strip().upper()
    url = verifactu.url_qr(nif, doc_row["numero"], doc_row["fecha"], doc_row["total"])
    texto = Paragraph(
        f"<b>{verifactu.LEYENDA}</b><br/>"
        "Escanea el código QR para cotejar esta factura en la Agencia Tributaria.",
        st["fp_row"])
    t = Table([[_qr_verifactu(url), texto]], colWidths=[26 * mm, ancho - 26 * mm])
    t.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.6, _BORDE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return t


def _barra(texto: str, ancho: float, st: dict) -> Table:
    t = Table([[Paragraph(texto.upper(), st["bar"])]], colWidths=[ancho])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), _OSCURO),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    return t


def _celda(label: str, valor: str, st: dict) -> Paragraph:
    valor = _esc((valor or "").strip())
    return Paragraph(
        f'<font size="7" color="#6A6E73"><b>{_esc(label.upper())}</b></font><br/>'
        f'<font size="9">{valor or "&nbsp;"}</font>',
        st["val"],
    )


def _rejilla(celdas: list, col_widths: list, row_heights: list, st: dict) -> Table:
    t = Table(celdas, colWidths=col_widths, rowHeights=row_heights)
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOX", (0, 0), (-1, -1), 0.6, _BORDE),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, _BORDE),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
    ]))
    return t


def _fecha_es(iso: str) -> str:
    try:
        d = _dt.date.fromisoformat(iso)
        return d.strftime("%d/%m/%Y")
    except ValueError:
        return iso


def _dir_bloque(nombre, nif, direccion, cp, poblacion, provincia, tel="", email="", st=None):
    partes = []
    if nombre:
        partes.append(f"<b>{_esc(nombre)}</b>")
    if nif:
        partes.append(f"NIF/CIF: {_esc(nif)}")
    if direccion:
        partes.append(_esc(direccion))
    linea_pob = " ".join(x for x in [cp or "", poblacion or ""] if x).strip()
    if provincia:
        linea_pob = f"{linea_pob} ({provincia})" if linea_pob else f"({provincia})"
    if linea_pob:
        partes.append(_esc(linea_pob))
    if tel:
        partes.append(f"Tel.: {_esc(tel)}")
    if email:
        partes.append(_esc(email))
    return Paragraph("<br/>".join(partes) or "-", st["cell"])


def generar_pdf(doc_row, lineas_rows, cliente_row, vehiculo_row, empresa_row,
                destino: Path | str | None = None) -> Path:
    """Crea el PDF del documento con el formato del taller y devuelve la ruta."""
    st = _styles()
    tipo = doc_row["tipo"]
    numero = doc_row["numero"]
    ancho = 182 * mm  # A4 (210) menos 14 mm de margen a cada lado
    gap = 4
    imp_nombre = (empresa_row["impuesto_nombre"] or "IVA") if empresa_row else "IVA"
    anticipo_pct = float(empresa_row["anticipo_pct"] or 0) if empresa_row else 0.0
    con_anticipo = anticipo_pct > 0 and tipo in (domain.PRESUPUESTO, domain.ORDEN)

    if destino is None:
        destino = documents_dir() / f"{numero}.pdf"
    destino = Path(destino)

    pdf = SimpleDocTemplate(
        str(destino), pagesize=A4,
        leftMargin=14 * mm, rightMargin=14 * mm, topMargin=12 * mm, bottomMargin=14 * mm,
        title=f"{domain.TIPO_NOMBRE[tipo]} {numero}",
    )
    elems: list = []

    # ---- cabecera: logo | datos de empresa (derecha) ----------------
    logo = empresa_row["logo_path"] if empresa_row else ""
    if not (logo and Path(logo).is_file()):
        alt = Path(__file__).resolve().parent / "resources" / "logo.png"
        logo = str(alt) if alt.is_file() else ""
    logo_cell: object = ""
    if logo:
        try:
            # lazy=0 fuerza a leer la imagen ahora: si falla, se captura aquí y el
            # PDF se genera igualmente sin logo (no revienta durante build()).
            logo_cell = Image(logo, width=60 * mm, height=15 * mm, kind="proportional",
                              hAlign="LEFT", lazy=0)
        except Exception:  # noqa: BLE001 - un logo ilegible no debe impedir el PDF
            logo_cell = ""

    emp_lineas = [_P(empresa_row["nombre"], st["emp_nombre"])]
    for txt in [
        f"CIF: {empresa_row['nif']}" if empresa_row["nif"] else "",
        empresa_row["direccion"],
        " ".join(x for x in [empresa_row["cp"], empresa_row["poblacion"]] if x)
        + (f" - {empresa_row['provincia']}" if empresa_row["provincia"] else ""),
        f"TFN: {empresa_row['telefono']}" if empresa_row["telefono"] else "",
        empresa_row["email"],
    ]:
        if txt and txt.strip():
            emp_lineas.append(_P(txt.strip(), st["emp_line"]))

    cab = Table([[logo_cell, emp_lineas]], colWidths=[95 * mm, 87 * mm])
    cab.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    elems.append(cab)
    elems.append(Spacer(1, 4))
    elems.append(Table([[""]], colWidths=[ancho], rowHeights=[2],
                       style=[("BACKGROUND", (0, 0), (-1, -1), _ROJO)]))
    elems.append(Spacer(1, 5))

    # ---- franja de título + número --------------------------------
    meta = [f"<b>Nº:</b> {numero}",
            f"<b>Fecha:</b> {_fecha_es(doc_row['fecha'])}"]
    if tipo == domain.PRESUPUESTO:
        vd = doc_row["validez_dias"]
        meta.append(f"<b>Validez:</b> {vd} días" if vd else "<b>Validez:</b> _____ días")
    elif tipo == domain.FACTURA and doc_row["forma_pago"]:
        meta.append(f"<b>Pago:</b> {doc_row['forma_pago']}")
    franja = Table([[[Paragraph(_TITULO_DOC[tipo], st["doc_titulo"]),
                      Paragraph(_SUBTITULO[tipo], st["doc_sub"])],
                     [Paragraph(m, st["doc_meta"]) for m in meta]]],
                   colWidths=[120 * mm, 62 * mm])
    franja.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOX", (0, 0), (-1, -1), 0.6, _BORDE),
        ("LINEBEFORE", (1, 0), (1, 0), 0.6, _BORDE),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 9), ("RIGHTPADDING", (0, 0), (-1, -1), 9),
    ]))
    elems.append(franja)
    elems.append(Spacer(1, gap))

    # ---- datos del cliente ---------------------------------------
    c = cliente_row
    elems.append(_barra("Datos del cliente", ancho, st))
    dir_cli = c["direccion"] if c else ""
    loc_cli = " ".join(x for x in [(c["cp"] if c else ""), (c["poblacion"] if c else "")] if x)
    if c and c["provincia"]:
        loc_cli = f"{loc_cli} ({c['provincia']})" if loc_cli else c["provincia"]
    elems.append(_rejilla(
        [[_celda("Nombre / Razón social", c["nombre"] if c else "", st),
          _celda("NIF / CIF", c["nif"] if c else "", st),
          _celda("Teléfono", c["telefono"] if c else "", st)],
         [_celda("Dirección", dir_cli, st),
          _celda("Email", c["email"] if c else "", st),
          _celda("Localidad / C.P.", loc_cli, st)]],
        [78 * mm, 48 * mm, 56 * mm], [11 * mm, 11 * mm], st,
    ))
    elems.append(Spacer(1, gap))

    # ---- datos del vehículo ------------------------------------
    v = vehiculo_row
    elems.append(_barra("Datos del vehículo", ancho, st))
    km = doc_row["kms"] if doc_row["kms"] is not None else (v["kms"] if v else None)
    elems.append(_rejilla(
        [[_celda("Marca", v["marca"] if v else "", st),
          _celda("Modelo / Versión", v["modelo"] if v else "", st),
          _celda("Matrícula", v["matricula"] if v else "", st),
          _celda("Kilómetros", _fmt_km(km), st)],
         [_celda("VIN / Bastidor", v["bastidor"] if v else "", st),
          _celda("Fecha de entrada", _fecha_es(doc_row["fecha_entrada"])
                 if doc_row["fecha_entrada"] else "", st),
          _celda("Entrega prevista", _fecha_es(doc_row["entrega_prevista"])
                 if doc_row["entrega_prevista"] else "", st),
          _celda("Combustible / Nivel", v["combustible"] if v else "", st)]],
        [45.5 * mm, 45.5 * mm, 45.5 * mm, 45.5 * mm], [9.5 * mm, 9.5 * mm], st,
    ))
    elems.append(Spacer(1, gap))

    # ---- líneas ----------------------------------------------
    elems.append(_barra("Trabajos, piezas y materiales", ancho, st))
    data = [[Paragraph("Cant.", st["thr"]), Paragraph("Concepto / descripción", st["th"]),
             Paragraph("P. unitario", st["thr"]), Paragraph("Dto.", st["thr"]),
             Paragraph("Importe", st["thr"])]]
    calc: list[domain.LineaCalc] = []
    for ln in lineas_rows:
        lc = domain.LineaCalc(cantidad=ln["cantidad"], precio=ln["precio"],
                              descuento_pct=ln["descuento_pct"], iva_pct=ln["iva_pct"])
        calc.append(lc)
        data.append([
            Paragraph(_fmt_num(ln["cantidad"]), st["tdr"]),
            _P(ln["descripcion"], st["td"]),
            Paragraph(domain.formato_moneda(ln["precio"]), st["tdr"]),
            Paragraph(f"{_fmt_num(ln['descuento_pct'])} %" if ln["descuento_pct"] else "",
                      st["tdr"]),
            Paragraph(domain.formato_moneda(lc.base), st["tdr"]),
        ])
    for _ in range(max(0, 4 - len(lineas_rows))):
        data.append(["", "", "", "", ""])

    lt = Table(data, colWidths=[16 * mm, 94 * mm, 26 * mm, 18 * mm, 28 * mm], repeatRows=1)
    lt.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, _OSCURO),
        ("BOX", (0, 0), (-1, -1), 0.6, _BORDE),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, _BORDE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#FAFAFB")]),
    ]))
    elems.append(lt)
    elems.append(Spacer(1, gap))

    # ---- totales (bloque a la derecha, como en el modelo) ----------
    totales = domain.calcular_totales(calc, doc_row["descuento_pct"] or 0)
    tot_rows = []
    est = [
        ("BOX", (0, 0), (-1, -1), 0.6, _BORDE),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, _BORDE),
        ("BACKGROUND", (0, 0), (-1, -1), _LABEL_BG),
        ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 4.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 4.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 9), ("RIGHTPADDING", (0, 0), (-1, -1), 9),
    ]
    if doc_row["descuento_pct"]:
        tot_rows.append([Paragraph("Descuento general", st["tot_l"]),
                         Paragraph(f"{_fmt_num(doc_row['descuento_pct'])} %", st["tot_l"])])
    tot_rows.append([Paragraph("Base imponible", st["tot_l"]),
                     Paragraph(domain.formato_moneda(totales.base), st["tot_l"])])
    for rate, (_b, cuota_r) in totales.desglose.items():
        tot_rows.append([Paragraph(f"{imp_nombre} {rate:g} %", st["tot_l"]),
                         Paragraph(domain.formato_moneda(cuota_r), st["tot_l"])])
    ft = len(tot_rows)
    tot_rows.append([Paragraph(_TOTAL_LBL[tipo], st["tot_lb"]),
                     Paragraph(domain.formato_moneda(totales.total), st["tot_lb"])])
    est += [("LINEABOVE", (0, ft), (-1, ft), 0.8, _OSCURO),
            ("BACKGROUND", (0, ft), (-1, ft), colors.white)]
    if con_anticipo:
        ant, pend = domain.importe_anticipo(totales.total, anticipo_pct)
        fa = len(tot_rows)
        tot_rows.append([
            Paragraph(f"<font color='#ED1C24'><b>ANTICIPO {anticipo_pct:g} %</b></font>"
                      f" <font color='#191B1D'>/ PENDIENTE</font>", st["tot_l"]),
            Paragraph(f"<font color='#ED1C24'><b>{domain.formato_moneda(ant)}</b></font>"
                      f" / {domain.formato_moneda(pend)}", st["tot_l"]),
        ])
        est.append(("BACKGROUND", (0, fa), (-1, fa), _ROJO_BG))
    tot_box = Table(tot_rows, colWidths=[48 * mm, 34 * mm])
    tot_box.setStyle(TableStyle(est))
    envoltura = Table([["", tot_box]], colWidths=[ancho - 82 * mm, 82 * mm])
    envoltura.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0),
                                   ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                                   ("TOPPADDING", (0, 0), (-1, -1), 0),
                                   ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    elems.append(envoltura)
    elems.append(Spacer(1, gap))

    # ---- autorización / observaciones -----------------------------
    cond_map = {
        domain.PRESUPUESTO: empresa_row["cond_presupuesto"],
        domain.ORDEN: empresa_row["cond_orden"],
        domain.ALBARAN: empresa_row["cond_albaran"],
        domain.FACTURA: empresa_row["cond_factura"],
    }
    cond_txt = (cond_map.get(tipo) or "").strip()
    titulo_cond = ("AUTORIZACIÓN Y OBSERVACIONES"
                   if tipo in (domain.PRESUPUESTO, domain.ORDEN) else "OBSERVACIONES")
    elems.append(_barra(titulo_cond, ancho, st))
    cont = []
    if cond_txt:
        cont.append(_P(cond_txt, st["cond"], multilinea=True))
        cont.append(Spacer(1, 4))
    obs = (doc_row["observaciones"] or "").strip()
    cont.append(Paragraph(
        f"<b>Observaciones:</b> {_esc(obs).replace(chr(10), '<br/>')}" if obs
        else "<b>Observaciones:</b> " + "_" * 78, st["cond"]))
    caja = Table([[cont]], colWidths=[ancho])
    caja.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.6, _BORDE),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    elems.append(caja)

    # ---- firmas -------------------------------------------------
    if tipo != domain.FACTURA:
        elems.append(Spacer(1, gap))
        izq = ("CLIENTE - Recibí conforme" if tipo == domain.ALBARAN
               else "CLIENTE - Conforme y autorizado")

        def _fc(titulo):
            return [Paragraph(titulo, st["firma_h"]), Spacer(1, 12),
                    Paragraph("Firma:", st["firma_f"]),
                    Paragraph("Nombre: __________________________", st["firma_f"]),
                    Paragraph("DNI/NIF: _________________________", st["firma_f"])]

        firmas = Table([[_fc(izq), _fc("TALLER - Firma / sello")]],
                       colWidths=[91 * mm, 91 * mm])
        firmas.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.6, _BORDE),
            ("LINEBEFORE", (1, 0), (1, 0), 0.6, _BORDE),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ]))
        elems.append(firmas)

    # ---- forma de pago (barras a lo ancho, al pie) ----------------
    elems.append(Spacer(1, gap))
    elems.append(_barra("Forma de pago", ancho, st))
    if tipo in (domain.PRESUPUESTO, domain.ORDEN):
        izq_txt = (f"{anticipo_pct:g} % DE ANTICIPO" if con_anticipo
                   else "TRANSFERENCIA BANCARIA")
        der_txt = f"Transferencia bancaria  ·  Concepto: {numero} + matrícula"
    elif tipo == domain.FACTURA:
        izq_txt = "PAGO"
        der_txt = doc_row["forma_pago"] or "Al contado a la recepción de la factura."
    else:  # albarán
        izq_txt = "DOCUMENTO SIN VALOR FISCAL"
        der_txt = "La factura se emitirá por separado."
    fp1 = Table([[Paragraph(f"<b>{_esc(izq_txt)}</b>", st["fp_row"]),
                  _P(der_txt, st["fp_row"])]],
                colWidths=[62 * mm, ancho - 62 * mm])
    fp1.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.6, _BORDE),
        ("LINEBEFORE", (1, 0), (1, 0), 0.6, _BORDE),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 9), ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    elems.append(fp1)
    # El IBAN solo aparece en el presupuesto (para que el cliente lo acepte e ingrese
    # el anticipo). En orden, albarán y factura no se muestra.
    if empresa_row["iban"] and tipo == domain.PRESUPUESTO:
        fp2 = Table([[Paragraph(f"<b>Titular:</b> {_esc(empresa_row['nombre'])}", st["fp_row"]),
                      Paragraph(f"<b>IBAN {_esc(empresa_row['iban'])}</b>", st["fp_iban"])]],
                    colWidths=[78 * mm, ancho - 78 * mm])
        fp2.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, 0), _LABEL_BG),
            ("BACKGROUND", (1, 0), (1, 0), _ROJO),
            ("BOX", (0, 0), (-1, -1), 0.6, _BORDE),
            ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 9), ("RIGHTPADDING", (0, 0), (-1, -1), 9),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        elems.append(fp2)

    # ---- QR VeriFactu (solo facturas, si está activado) --
    if tipo == domain.FACTURA and empresa_row is not None and verifactu.activo(empresa_row):
        elems.append(Spacer(1, gap))
        try:
            elems.append(_bloque_verifactu(doc_row, empresa_row, ancho, st))
        except Exception:  # noqa: BLE001 - un fallo del QR no debe impedir la factura
            elems.append(Paragraph(f"<b>{verifactu.LEYENDA}</b>", st["fp_row"]))

    # ---- pie de página -----------------------------------
    pie_txt = (empresa_row["pie_documento"] or "").strip() if empresa_row else ""
    if not pie_txt and empresa_row:
        partes = [empresa_row["nombre"]]
        if empresa_row["nif"]:
            partes.append(f"CIF {empresa_row['nif']}")
        d2 = empresa_row["direccion"]
        loc = " ".join(y for y in [empresa_row["cp"], empresa_row["poblacion"]] if y)
        if d2 or loc:
            partes.append(" - ".join(x for x in [d2, loc] if x))
        if empresa_row["telefono"]:
            partes.append(empresa_row["telefono"])
        pie_txt = "  ·  ".join(p for p in partes if p)

    anulado = doc_row["estado"] == "anulado"

    def _pie(canvas, _doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(_LABEL)
        if pie_txt:
            canvas.drawCentredString(A4[0] / 2, 9 * mm, pie_txt[:200])
        canvas.drawRightString(A4[0] - 14 * mm, 9 * mm, f"Página {_doc.page}")
        canvas.setStrokeColor(_BORDE)
        canvas.setLineWidth(0.5)
        canvas.line(14 * mm, 12 * mm, A4[0] - 14 * mm, 12 * mm)
        canvas.restoreState()
        if anulado:
            canvas.saveState()
            canvas.translate(A4[0] / 2, A4[1] / 2)
            canvas.rotate(38)
            canvas.setFont("Helvetica-Bold", 90)
            canvas.setFillColor(colors.Color(0.90, 0.14, 0.10, alpha=0.22))
            canvas.drawCentredString(0, -20, "ANULADO")
            canvas.restoreState()

    pdf.build(elems, onFirstPage=_pie, onLaterPages=_pie)
    return destino


def _num(x: float) -> str:
    if x == int(x):
        return str(int(x))
    return f"{x:.2f}".replace(".", ",")


def generar_ficha_cliente(cliente_row, vehiculos_rows, empresa_row,
                          destino: Path | str | None = None) -> Path:
    """Genera un PDF de una sola página con los datos del cliente y todos sus vehículos."""
    st = _styles()
    nombre_fich = (cliente_row["nombre"] or f"cliente-{cliente_row['id']}").strip()
    nombre_fich = "".join(c if c.isalnum() or c in " -_" else "_" for c in nombre_fich)

    if destino is None:
        destino = documents_dir() / f"Ficha - {nombre_fich}.pdf"
    destino = Path(destino)

    pdf = SimpleDocTemplate(
        str(destino), pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm, topMargin=15 * mm, bottomMargin=18 * mm,
        title=f"Ficha de cliente - {cliente_row['nombre']}",
    )
    elems: list = []

    logo = empresa_row["logo_path"] if empresa_row else ""
    cab_izq: list = []
    if logo and Path(logo).is_file():
        try:
            cab_izq.append(Image(logo, width=45 * mm, height=20 * mm, kind="proportional"))
        except Exception:  # noqa: BLE001
            pass
    cab_izq.append(_dir_bloque(
        empresa_row["nombre"], empresa_row["nif"], empresa_row["direccion"],
        empresa_row["cp"], empresa_row["poblacion"], empresa_row["provincia"],
        empresa_row["telefono"], empresa_row["email"], st,
    ))
    cab = Table([[cab_izq, Paragraph("FICHA DE CLIENTE", st["titulo"])]],
                colWidths=[100 * mm, 74 * mm])
    cab.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    elems.append(cab)
    elems.append(Spacer(1, 12))

    pob = " ".join(x for x in [cliente_row["cp"] or "", cliente_row["poblacion"] or ""] if x)
    if cliente_row["provincia"]:
        pob = f"{pob} ({cliente_row['provincia']})" if pob else f"({cliente_row['provincia']})"
    datos = [
        ["Nombre / Razón social", cliente_row["nombre"] or "-"],
        ["NIF / CIF", cliente_row["nif"] or "-"],
        ["Dirección", cliente_row["direccion"] or "-"],
        ["Población", pob or "-"],
        ["Teléfono", cliente_row["telefono"] or "-"],
        ["Email", cliente_row["email"] or "-"],
    ]
    if cliente_row["notas"]:
        datos.append(["Notas", cliente_row["notas"]])
    t_datos = Table([[Paragraph(k, st["cell"]), _P(v, st["cell"], multilinea=True)]
                     for k, v in datos],
                    colWidths=[42 * mm, 132 * mm])
    t_datos.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, _LINEA),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, _LINEA),
        ("BACKGROUND", (0, 0), (0, -1), _GRIS_CLARO),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    elems.append(t_datos)
    elems.append(Spacer(1, 14))

    elems.append(Paragraph(f"VEHÍCULOS ({len(vehiculos_rows)})", st["seccion"]))
    elems.append(Spacer(1, 4))
    if vehiculos_rows:
        cabecera = ["Matrícula", "Marca", "Modelo", "Bastidor", "Año", "Combust.", "Kms"]
        data = [cabecera]
        for v in vehiculos_rows:
            data.append([
                _P(v["matricula"], st["cell"]),
                _P(v["marca"], st["cell"]),
                _P(v["modelo"], st["cell"]),
                _P(v["bastidor"], st["cell"]),
                Paragraph(str(v["anio"] or ""), st["cell"]),
                _P(v["combustible"], st["cell"]),
                Paragraph(f"{v['kms']:,}".replace(",", ".") if v["kms"] else "", st["cellr"]),
            ])
        t_veh = Table(data, colWidths=[22 * mm, 24 * mm, 30 * mm, 44 * mm, 12 * mm,
                                       20 * mm, 22 * mm], repeatRows=1)
        t_veh.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), _GRIS),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 8),
            ("LINEBELOW", (0, 0), (-1, -1), 0.25, _LINEA),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f6f6f6")]),
        ]))
        elems.append(t_veh)
    else:
        elems.append(Paragraph("Sin vehículos registrados.", st["small"]))

    elems.append(Spacer(1, 16))
    elems.append(Paragraph(
        f"Ficha generada el {_dt.date.today().strftime('%d/%m/%Y')}", st["small"]
    ))

    pdf.build(elems)
    return destino


def generar_historial_vehiculo(vehiculo_row, cliente_row, eventos, empresa_row,
                               destino: Path | str | None = None) -> Path:
    """Genera el PDF con el historial de intervenciones y trabajos de un vehículo."""
    st = _styles()
    matricula = (vehiculo_row["matricula"] or f"vehiculo-{vehiculo_row['id']}").strip()
    slug = "".join(c if c.isalnum() or c in " -_" else "_" for c in matricula)

    if destino is None:
        destino = documents_dir() / f"Historial - {slug}.pdf"
    destino = Path(destino)

    pdf = SimpleDocTemplate(
        str(destino), pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm, topMargin=15 * mm, bottomMargin=18 * mm,
        title=f"Historial del vehículo {matricula}",
    )
    elems: list = []

    cab_izq = _dir_bloque(
        empresa_row["nombre"], empresa_row["nif"], empresa_row["direccion"],
        empresa_row["cp"], empresa_row["poblacion"], empresa_row["provincia"],
        empresa_row["telefono"], empresa_row["email"], st,
    )
    cab = Table([[cab_izq, Paragraph("HISTORIAL DEL VEHÍCULO", st["titulo"])]],
                colWidths=[100 * mm, 74 * mm])
    cab.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    elems.append(cab)
    elems.append(Spacer(1, 10))

    desc = " ".join(x for x in [vehiculo_row["marca"], vehiculo_row["modelo"]] if x)
    info = [
        f"<b>Matrícula:</b> {_esc(vehiculo_row['matricula'] or '-')}",
        f"<b>Vehículo:</b> {_esc(desc or '-')}",
        f"<b>Bastidor:</b> {_esc(vehiculo_row['bastidor'] or '-')}",
        f"<b>Cliente:</b> {_esc(cliente_row['nombre'] if cliente_row else '-')}",
    ]
    if vehiculo_row["combustible"]:
        info.append(f"<b>Combustible:</b> {_esc(vehiculo_row['combustible'])}")
    if vehiculo_row["anio"]:
        info.append(f"<b>Año:</b> {vehiculo_row['anio']}")
    caja = Table([[Paragraph("&nbsp;&nbsp;·&nbsp;&nbsp;".join(info), st["cell"])]],
                 colWidths=[174 * mm])
    caja.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, _LINEA),
        ("BACKGROUND", (0, 0), (-1, -1), _GRIS_CLARO),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    elems.append(caja)
    elems.append(Spacer(1, 12))

    if not eventos:
        elems.append(Paragraph("Este vehículo no tiene intervenciones registradas.", st["cell"]))
        pdf.build(elems)
        return destino

    data = [["Fecha", "Kms", "Tipo", "Intervención"]]
    for ev in eventos:
        fecha = _fecha_es(ev["fecha"])
        km = f"{ev['kms']:,}".replace(",", ".") if ev["kms"] else "-"
        detalle = _esc(ev["titulo"])
        if ev["detalle"]:
            detalle += "<br/>" + _esc(ev["detalle"]).replace("\n", "<br/>")
        if ev.get("total") is not None:
            detalle += f"<br/><font color='#666'>Total: {domain.formato_moneda(ev['total'])}</font>"
        prox = []
        if ev.get("prox_fecha"):
            prox.append(f"fecha {_fecha_es(ev['prox_fecha'])}")
        if ev.get("prox_kms"):
            prox.append(f"{ev['prox_kms']:,}".replace(",", ".") + " km")
        if prox:
            detalle += f"<br/><font color='#a05a00'>Próxima revisión: {' o '.join(prox)}</font>"
        data.append([
            Paragraph(fecha, st["cell"]),
            Paragraph(km, st["cellr"]),
            Paragraph(ev["tipo_nombre"], st["cell"]),
            Paragraph(detalle, st["cell"]),
        ])

    tabla = Table(data, colWidths=[20 * mm, 18 * mm, 30 * mm, 106 * mm], repeatRows=1)
    tabla.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), _GRIS),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, _LINEA),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f6f6f6")]),
    ]))
    elems.append(tabla)
    elems.append(Spacer(1, 12))
    elems.append(Paragraph(
        f"{len(eventos)} intervenciones · historial generado el "
        f"{_dt.date.today().strftime('%d/%m/%Y')}", st["small"]
    ))

    pdf.build(elems)
    return destino
