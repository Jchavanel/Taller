"""Prueba de humo sin interfaz gráfica: crea datos, calcula totales y genera un PDF."""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

tmp = Path(tempfile.mkdtemp())
os.environ["TALLER_DATA_DIR"] = str(tmp)
os.environ["TALLER_DB"] = str(tmp / "test.db")

from taller import domain  # noqa: E402
from taller.database import Database  # noqa: E402
from taller.pdf_export import (  # noqa: E402
    generar_ficha_cliente,
    generar_historial_vehiculo,
    generar_pdf,
)
from taller.repository import Repository  # noqa: E402


def test_totales_agrupa_por_iva():
    lineas = [
        domain.LineaCalc(cantidad=2, precio=100, iva_pct=21),
        domain.LineaCalc(cantidad=1, precio=50, iva_pct=10),
        domain.LineaCalc(cantidad=1, precio=100, descuento_pct=10, iva_pct=21),
    ]
    t = domain.calcular_totales(lineas)
    assert t.base == 340.0            # 200 + 50 + 90
    assert t.desglose[21.0] == (290.0, 60.9)
    assert t.desglose[10.0] == (50.0, 5.0)
    assert t.cuota_iva == 65.9
    assert t.total == 405.9


def test_redondeo_decimal():
    # 105.50 al 21 % = 22.155 -> con redondeo comercial (mitad arriba) = 22.16
    lc = [domain.LineaCalc(cantidad=1.5, precio=40, iva_pct=21),
          domain.LineaCalc(cantidad=1, precio=45.5, iva_pct=21)]
    t = domain.calcular_totales(lc)
    assert t.base == 105.5
    assert t.cuota_iva == 22.16          # antes daba 22.15 con float
    assert t.total == 127.66
    # el anticipo siempre suma el total exacto
    a, p = domain.importe_anticipo(267.51, 50)
    assert a + p == 267.51


def test_cambio_de_anio_renumera():
    db = Database()
    repo = Repository(db)
    cid = repo.save_cliente({"nombre": "Año SL"})
    pid = repo.crear_documento({"tipo": domain.PRESUPUESTO, "fecha": "2026-06-01",
                                "cliente_id": cid},
                               [{"descripcion": "x", "cantidad": 1, "precio": 10, "iva_pct": 7}])
    assert repo.get_documento(pid)["numero"].startswith("PRE-2026-")
    repo.actualizar_documento(pid, {"tipo": domain.PRESUPUESTO, "fecha": "2027-01-10",
                                    "cliente_id": cid, "estado": "abierto"},
                              [{"descripcion": "x", "cantidad": 1, "precio": 10, "iva_pct": 7}])
    assert repo.get_documento(pid)["numero"].startswith("PRE-2027-")
    assert repo.get_documento(pid)["anio"] == 2027

    # una factura NO cambia de año
    fid = repo.crear_documento({"tipo": domain.FACTURA, "fecha": "2026-06-01",
                                "cliente_id": cid},
                               [{"descripcion": "x", "cantidad": 1, "precio": 10, "iva_pct": 7}])
    repo.actualizar_documento(fid, {"tipo": domain.FACTURA, "fecha": "2027-03-01",
                                    "cliente_id": cid, "estado": "abierto"},
                              [{"descripcion": "x", "cantidad": 1, "precio": 10, "iva_pct": 7}])
    assert repo.get_documento(fid)["anio"] == 2026
    assert repo.get_documento(fid)["fecha"].startswith("2026")


def test_pdf_escapa_texto_del_usuario():
    try:
        import pymupdf
    except ImportError:
        return
    db = Database()
    repo = Repository(db)
    cid = repo.save_cliente({"nombre": 'Talleres <A&B> "Motor"'})
    vid = repo.save_vehiculo({"cliente_id": cid, "matricula": "1<2>3", "marca": "A & B"})
    did = repo.crear_documento(
        {"tipo": domain.PRESUPUESTO, "cliente_id": cid, "vehiculo_id": vid,
         "observaciones": "Revisar <EGR> & filtro"},
        [{"descripcion": "Tornillo M6 < M8 & tuerca <b>reforzada</b>", "cantidad": 1,
          "precio": 10, "iva_pct": 7}])
    pdf = generar_pdf(repo.get_documento(did), repo.get_lineas(did), repo.get_cliente(cid),
                      repo.get_vehiculo(vid), repo.get_empresa(), destino=tmp / "esc.pdf")
    texto = " ".join(pymupdf.open(str(pdf))[0].get_text().split())
    assert "Tornillo M6 < M8 & tuerca <b>reforzada</b>" in texto  # literal, no interpretado
    assert "A & B" in texto


def test_totales_descuento_general():
    lineas = [domain.LineaCalc(cantidad=1, precio=1000, iva_pct=21)]
    t = domain.calcular_totales(lineas, descuento_general_pct=10)
    assert t.base == 900.0
    assert t.cuota_iva == 189.0
    assert t.total == 1089.0


def test_flujo_completo_y_pdf():
    db = Database()
    repo = Repository(db)
    repo.save_empresa({
        "nombre": "Taller Pruebas SL", "nif": "B00000000", "direccion": "C/ Falsa 1",
        "cp": "28001", "poblacion": "Madrid", "provincia": "Madrid",
        "telefono": "600000000", "email": "taller@ejemplo.es", "iban": "ES00 0000",
        "iva_defecto": 21.0, "logo_path": "", "pie_documento": "Gracias por su confianza",
    })
    cid = repo.save_cliente({"nombre": "Juan Pérez", "nif": "12345678Z",
                             "telefono": "611223344", "poblacion": "Getafe"})
    vid = repo.save_vehiculo({"cliente_id": cid, "matricula": "1234ABC",
                              "marca": "Seat", "modelo": "León", "kms": 90000})

    lineas = [
        {"tipo": "mano_obra", "descripcion": "Cambio de aceite y filtros",
         "cantidad": 1.5, "precio": 40, "iva_pct": 21},
        {"tipo": "material", "descripcion": "Aceite 5W30 (5L)",
         "cantidad": 1, "precio": 45.5, "iva_pct": 21},
    ]
    pre_id = repo.crear_documento(
        {"tipo": domain.PRESUPUESTO, "cliente_id": cid, "vehiculo_id": vid, "kms": 90000},
        lineas,
    )
    doc = repo.get_documento(pre_id)
    assert doc["numero"].startswith("PRE-")
    assert doc["total"] == round((60 + 45.5) * 1.21, 2)

    ot_id = repo.convertir_documento(pre_id, domain.ORDEN)
    assert repo.get_documento(ot_id)["numero"].startswith("OT-")
    assert repo.get_documento(pre_id)["estado"] == "aprobado"

    alb_id = repo.convertir_documento(ot_id, domain.ALBARAN)
    fac_id = repo.convertir_documento(alb_id, domain.FACTURA)
    fac = repo.get_documento(fac_id)
    assert fac["numero"].startswith("FAC-")

    # numeración correlativa
    fac2_id = repo.crear_documento({"tipo": domain.FACTURA, "cliente_id": cid},
                                   [{"descripcion": "Diagnóstico", "cantidad": 1,
                                     "precio": 30, "iva_pct": 21}])
    assert repo.get_documento(fac2_id)["secuencia"] == fac["secuencia"] + 1

    salida = generar_pdf(
        fac, repo.get_lineas(fac_id), repo.get_cliente(cid),
        repo.get_vehiculo(vid), repo.get_empresa(), destino=tmp / "factura.pdf",
    )
    assert salida.is_file() and salida.stat().st_size > 1000


def test_cliente_con_vehiculos_y_ficha():
    db = Database()
    repo = Repository(db)
    empresa = repo.get_empresa()
    cid = repo.guardar_cliente_con_vehiculos(
        {"nombre": "María López", "nif": "99999999R", "telefono": "600111222"},
        [
            {"matricula": "1111AAA", "marca": "Seat", "modelo": "Ibiza", "kms": 80000},
            {"matricula": "2222BBB", "marca": "Ford", "modelo": "Focus", "kms": 40000},
        ],
    )
    vehiculos = repo.list_vehiculos(cliente_id=cid)
    assert {v["matricula"] for v in vehiculos} == {"1111AAA", "2222BBB"}

    # editar: quitar el primero, añadir uno nuevo, cambiar kms del que queda
    quedan = [dict(v) for v in vehiculos if v["matricula"] == "2222BBB"]
    quedan[0]["kms"] = 45000
    quedan.append({"matricula": "3333CCC", "marca": "Kia", "modelo": "Ceed", "kms": 5000})
    borrar = [v["id"] for v in vehiculos if v["matricula"] == "1111AAA"]
    repo.guardar_cliente_con_vehiculos({"id": cid, "nombre": "María López"}, quedan, borrar)

    vehiculos2 = repo.list_vehiculos(cliente_id=cid)
    assert {v["matricula"] for v in vehiculos2} == {"2222BBB", "3333CCC"}
    assert next(v["kms"] for v in vehiculos2 if v["matricula"] == "2222BBB") == 45000

    salida = generar_ficha_cliente(repo.get_cliente(cid), vehiculos2, empresa,
                                   destino=tmp / "ficha.pdf")
    assert salida.is_file() and salida.stat().st_size > 1000


def test_formato_taller_igic_y_anticipo():
    from taller.seed import precargar_taller

    db = Database()
    repo = Repository(db)
    precargar_taller(repo)
    e = repo.get_empresa()
    assert e["nombre"] == "Taller Europa Jor S.L."
    assert e["impuesto_nombre"] == "IGIC"
    assert e["anticipo_pct"] == 50.0
    assert e["cond_presupuesto"] and "50 %" in e["cond_presupuesto"]

    cid = repo.save_cliente({"nombre": "Cliente IGIC"})
    vid = repo.save_vehiculo({"cliente_id": cid, "matricula": "0000AAA", "marca": "Opel"})
    pid = repo.crear_documento(
        {"tipo": domain.PRESUPUESTO, "cliente_id": cid, "vehiculo_id": vid,
         "validez_dias": 15, "fecha_entrada": "2026-08-28"},
        [{"descripcion": "Embrague", "cantidad": 1, "precio": 500, "iva_pct": 7}],
    )
    doc = repo.get_documento(pid)
    assert doc["validez_dias"] == 15 and doc["fecha_entrada"] == "2026-08-28"

    ant, pend = domain.importe_anticipo(doc["total"], 50)
    assert ant + pend == doc["total"]

    salida = generar_pdf(doc, repo.get_lineas(pid), repo.get_cliente(cid),
                         repo.get_vehiculo(vid), repo.get_empresa(), destino=tmp / "fmt.pdf")
    assert salida.is_file() and salida.stat().st_size > 2000
    try:
        import pymupdf
    except ImportError:
        print("  (pymupdf no instalado: se omite la comprobación del texto del PDF)")
        return
    texto = " ".join(pymupdf.open(str(salida))[0].get_text().split())
    assert "IGIC 7 %" in texto
    assert "ANTICIPO 50 %" in texto and "PENDIENTE" in texto
    assert "50 % DE ANTICIPO" in texto
    assert "IBAN ES59 0182 5046 4602 0162 1452" in texto
    assert "CLIENTE - Conforme y autorizado" in texto
    assert "FORMA DE PAGO" in texto

    # la factura no lleva anticipo ni firmas
    facid = repo.crear_documento({"tipo": domain.FACTURA, "cliente_id": cid,
                                  "vehiculo_id": vid},
                                 [{"descripcion": "x", "cantidad": 1, "precio": 10,
                                   "iva_pct": 7}])
    fac_pdf = generar_pdf(repo.get_documento(facid), repo.get_lineas(facid),
                          repo.get_cliente(cid), repo.get_vehiculo(vid),
                          repo.get_empresa(), destino=tmp / "fac.pdf")
    ftxt = " ".join(pymupdf.open(str(fac_pdf))[0].get_text().split())
    assert "ANTICIPO" not in ftxt and "Firma:" not in ftxt
    assert "TOTAL FACTURA" in ftxt
    # el IBAN solo va en el presupuesto, no en la factura
    assert "IBAN" not in ftxt and "ES59 0182" not in ftxt


def test_aplicar_impuesto_a_articulos():
    from taller.seed import cargar_articulos_ejemplo

    db = Database()
    repo = Repository(db)
    base = {"nombre": "T", "nif": "", "direccion": "", "cp": "", "poblacion": "",
            "provincia": "", "telefono": "", "email": "", "iban": "", "logo_path": "",
            "pie_documento": ""}
    # simula el caso del usuario: artículos cargados con IVA 21 antiguo
    repo.save_empresa({**base, "impuesto_nombre": "IVA", "iva_defecto": 21.0})
    cargar_articulos_ejemplo(repo)
    arts = repo.list_articulos(solo_activos=False)
    assert arts and all(a["iva_pct"] == 21.0 for a in arts)

    repo.save_empresa({**base, "impuesto_nombre": "IGIC", "iva_defecto": 7.0})
    assert repo.contar_articulos_con_iva_distinto(7.0) == len(arts)
    cambiados = repo.aplicar_impuesto_a_articulos(7.0)
    assert cambiados == len(arts)
    assert all(a["iva_pct"] == 7.0 for a in repo.list_articulos(solo_activos=False))
    assert repo.contar_articulos_con_iva_distinto(7.0) == 0
    # ejecutar de nuevo no cambia nada
    assert repo.aplicar_impuesto_a_articulos(7.0) == 0


def test_correo_plantillas_y_mensaje():
    from taller import email_envio as mail

    # ofuscación reversible
    assert mail.desofuscar(mail.ofuscar("secreta123")) == "secreta123"
    assert mail.ofuscar("") == ""
    assert not mail.ofuscar("x").startswith("b64:b64:")  # no doble prefijo
    assert mail.ofuscar(mail.ofuscar("x")) == mail.ofuscar("x")

    db = Database()
    repo = Repository(db)
    repo.save_empresa({
        "nombre": "Taller X", "telefono": "600", "nif": "", "direccion": "", "cp": "",
        "poblacion": "", "provincia": "", "email": "", "iban": "", "iva_defecto": 7.0,
        "logo_path": "", "pie_documento": "",
        "smtp_host": "smtp.example.com", "smtp_port": 587, "smtp_seguridad": "starttls",
        "smtp_usuario": "taller@example.com", "smtp_password": mail.ofuscar("pw"),
        "smtp_remitente": "taller@example.com",
        "email_asunto": "{tipo} {numero}", "email_cuerpo": "Hola {cliente}, adjunto {numero}.",
    })
    cfg = mail.ConfigCorreo.desde_empresa(repo.get_empresa())
    assert cfg.configurado
    assert cfg.password == "pw"

    cid = repo.save_cliente({"nombre": "Ana", "email": "ana@correo.es"})
    vid = repo.save_vehiculo({"cliente_id": cid, "matricula": "1234ABC"})
    did = repo.crear_documento(
        {"tipo": domain.PRESUPUESTO, "cliente_id": cid, "vehiculo_id": vid},
        [{"descripcion": "x", "cantidad": 1, "precio": 100, "iva_pct": 7}])
    doc = repo.get_documento(did)
    ctx = mail.contexto_documento(doc, repo.get_cliente(cid), repo.get_vehiculo(vid),
                                  repo.get_empresa())
    asunto = mail.aplicar_plantilla(cfg.asunto, ctx)
    cuerpo = mail.aplicar_plantilla(cfg.cuerpo, ctx)
    assert asunto == f"Presupuesto {doc['numero']}"
    assert "Hola Ana" in cuerpo and doc["numero"] in cuerpo

    pdf = generar_pdf(doc, repo.get_lineas(did), repo.get_cliente(cid),
                      repo.get_vehiculo(vid), repo.get_empresa(), destino=tmp / "corr.pdf")
    msg = mail.construir_mensaje(cfg, ["ana@correo.es"], asunto, cuerpo, [pdf])
    assert msg["To"] == "ana@correo.es"
    assert msg["Subject"] == asunto
    adjuntos = [p for p in msg.iter_attachments()]
    assert len(adjuntos) == 1
    assert adjuntos[0].get_filename() == "corr.pdf"
    assert adjuntos[0].get_content_type() == "application/pdf"

    # plantilla con marcador inexistente -> se deja tal cual, sin reventar
    assert mail.aplicar_plantilla("hola {desconocido}", ctx) == "hola {desconocido}"


def test_documentos_en_curso_y_calendario():
    db = Database()
    repo = Repository(db)
    cid = repo.save_cliente({"nombre": "Curso SL"})
    vid = repo.save_vehiculo({"cliente_id": cid, "matricula": "5555EEE"})
    lin = [{"descripcion": "x", "cantidad": 1, "precio": 100, "iva_pct": 7}]

    p1 = repo.crear_documento({"tipo": domain.PRESUPUESTO, "cliente_id": cid,
                               "vehiculo_id": vid, "fecha": "2026-05-10"}, lin)
    p2 = repo.crear_documento({"tipo": domain.PRESUPUESTO, "cliente_id": cid,
                               "vehiculo_id": vid, "fecha": "2026-05-10"}, lin)
    # p2 -> orden -> albarán -> factura  (deja de estar "en curso")
    o2 = repo.convertir_documento(p2, domain.ORDEN)
    a2 = repo.convertir_documento(o2, domain.ALBARAN)
    f2 = repo.convertir_documento(a2, domain.FACTURA)

    en_curso = repo.list_documentos(en_curso=True)
    nums = {d["numero"] for d in en_curso}
    # p1 (presupuesto abierto) sí; p2 (aprobado) no; o2 (finalizado) no; a2/f2 no
    assert repo.get_documento(p1)["numero"] in nums
    assert repo.get_documento(p2)["numero"] not in nums
    assert repo.get_documento(o2)["numero"] not in nums
    assert all(d["tipo"] in ("presupuesto", "orden") for d in en_curso)

    # una orden nueva sin terminar SÍ aparece
    o3 = repo.crear_documento({"tipo": domain.ORDEN, "cliente_id": cid,
                               "vehiculo_id": vid}, lin)
    assert repo.get_documento(o3)["numero"] in {d["numero"] for d in
                                               repo.list_documentos(en_curso=True)}

    # calendario: los convertidos toman la fecha de hoy, no la del original
    deldia = repo.documentos_de_fecha("2026-05-10")
    assert len(deldia) == 2  # p1 y p2
    marcas = repo.fechas_con_documentos(2026, 5)
    assert "2026-05-10" in marcas and marcas["2026-05-10"]["n"] == 2
    # la factura f2 está en la fecha de hoy
    import datetime
    hoy = datetime.date.today().isoformat()
    hoy_docs = {d["numero"] for d in repo.documentos_de_fecha(hoy)}
    assert repo.get_documento(f2)["numero"] in hoy_docs


def test_borrado_seguro_y_anulacion():
    db = Database()
    repo = Repository(db)
    cid = repo.save_cliente({"nombre": "Seguro SL"})
    vid = repo.save_vehiculo({"cliente_id": cid, "matricula": "9999XXX"})
    lin = [{"descripcion": "x", "cantidad": 1, "precio": 100, "iva_pct": 7}]

    # borrar un presupuesto YA convertido no debe fallar (referencia origen_id)
    pid = repo.crear_documento({"tipo": domain.PRESUPUESTO, "cliente_id": cid,
                                "vehiculo_id": vid}, lin)
    oid = repo.convertir_documento(pid, domain.ORDEN)
    repo.delete_documento(pid)  # antes lanzaba IntegrityError
    assert repo.get_documento(pid) is None
    assert repo.get_documento(oid) is not None
    assert repo.get_documento(oid)["origen_id"] is None  # se limpió la referencia

    # una factura NO se borra
    fid = repo.crear_documento({"tipo": domain.FACTURA, "cliente_id": cid,
                                "vehiculo_id": vid}, lin)
    numero_fac = repo.get_documento(fid)["numero"]
    try:
        repo.delete_documento(fid)
        raise AssertionError("debería haber impedido borrar la factura")
    except ValueError:
        pass
    assert repo.get_documento(fid) is not None

    # anular conserva el documento y su número
    repo.anular_documento(fid, "error en importe")
    anulada = repo.get_documento(fid)
    assert anulada["estado"] == "anulado"
    assert anulada["numero"] == numero_fac
    assert "ANULADO" in anulada["observaciones"] and "error en importe" in anulada["observaciones"]
    assert repo.documento_bloqueado(anulada) is True

    # el número de la siguiente factura NO reutiliza el de la anulada
    fid2 = repo.crear_documento({"tipo": domain.FACTURA, "cliente_id": cid}, lin)
    assert repo.get_documento(fid2)["secuencia"] == anulada["secuencia"] + 1

    # el PDF de una factura anulada se genera y lleva la marca
    pdf = generar_pdf(anulada, repo.get_lineas(fid), repo.get_cliente(cid),
                      repo.get_vehiculo(vid), repo.get_empresa(), destino=tmp / "anul.pdf")
    assert pdf.is_file() and pdf.stat().st_size > 2000


def test_copias_de_seguridad():
    # DB aislada para este test (restaurar necesita cerrar todas las conexiones)
    sub = Path(tempfile.mkdtemp())
    os.environ["TALLER_DATA_DIR"] = str(sub)
    os.environ["TALLER_DB"] = str(sub / "test.db")
    try:
        from taller import backup

        db = Database()
        Repository(db).save_cliente({"nombre": "Con copia"})
        c1 = backup.hacer_copia(db, forzar=True)
        assert c1 and c1.is_file() and c1.stat().st_size > 0
        assert backup.hacer_copia(db, forzar=False) is None  # ya hay copia de hoy
        c2 = backup.hacer_copia(db, forzar=True)
        assert c2 and c2 != c1
        assert len(backup.listar_copias()) >= 2

        # --- copia en carpeta externa (USB) ---
        repo = Repository(db)
        externa = Path(tempfile.mkdtemp())
        backup.set_carpeta_externa(repo, externa)
        assert backup.carpeta_externa(repo) == externa
        c3 = backup.hacer_copia(db, forzar=True)
        ok, msg = backup.replicar_externa(c3, repo)
        assert ok, msg
        assert (externa / "taller-copias" / c3.name).is_file()

        # carpeta externa no disponible -> no rompe, avisa
        backup.set_carpeta_externa(repo, externa / "no-existe-pendrive")
        ok2, msg2 = backup.replicar_externa(c3, repo)
        assert not ok2 and "disponible" in msg2
        backup.set_carpeta_externa(repo, None)

        # exportar copia puntual a una ruta cualquiera
        suelto = Path(tempfile.mkdtemp()) / "copia-manual.db"
        p = backup.exportar_copia(suelto, db)
        assert p.is_file() and p.stat().st_size > 0

        Repository(db).save_cliente({"nombre": "Añadido después"})
        n_antes = Repository(db).estadisticas()["clientes"]
        backup.restaurar(c1, db)  # cierra db
        db2 = Database()
        assert Repository(db2).estadisticas()["clientes"] == n_antes - 1
        db2.close()
    finally:
        os.environ["TALLER_DATA_DIR"] = str(tmp)
        os.environ["TALLER_DB"] = str(tmp / "test.db")


def test_historial_vehiculo():
    db = Database()
    repo = Repository(db)
    cid = repo.save_cliente({"nombre": "Historial SL"})
    vid = repo.save_vehiculo({"cliente_id": cid, "matricula": "7777ZZZ",
                              "marca": "VW", "modelo": "Golf", "kms": 120000})

    # Orden de trabajo -> aparece en el historial automáticamente
    ot = repo.crear_documento(
        {"tipo": domain.ORDEN, "cliente_id": cid, "vehiculo_id": vid, "kms": 120000},
        [{"descripcion": "Cambio de embrague", "cantidad": 1, "precio": 600, "iva_pct": 21}],
    )
    hist = repo.historial_vehiculo(vid)
    assert len(hist) == 1
    assert hist[0]["origen"] == "documento"
    assert "Cambio de embrague" in hist[0]["detalle"]

    # Intervención manual con próxima revisión
    iid = repo.save_intervencion({
        "vehiculo_id": vid, "fecha": "2026-01-15", "kms": 118000, "tipo": "mantenimiento",
        "titulo": "Revisión de 118.000 km", "detalle": "Aceite, filtros, frenos revisados",
        "prox_fecha": "2027-01-15", "prox_kms": 133000,
    })
    hist = repo.historial_vehiculo(vid)
    assert len(hist) == 2
    assert hist[0]["fecha"] >= hist[1]["fecha"]  # orden descendente

    prox = repo.proxima_revision(vid)
    assert prox["prox_kms"] == 133000

    # Prefill desde documento
    datos = repo.intervencion_desde_documento(ot)
    assert datos["vehiculo_id"] == vid
    assert "Cambio de embrague" in datos["detalle"]
    repo.save_intervencion(datos)
    hist = repo.historial_vehiculo(vid)
    # la OT ya está representada por su intervención vinculada -> no se duplica
    assert sum(1 for e in hist if e["origen"] == "documento" and e["id"] == ot) == 0

    repo.delete_intervencion(iid)
    # queda solo la intervención derivada de la OT (la OT sigue sin duplicarse)
    hist = repo.historial_vehiculo(vid)
    assert len(hist) == 1 and hist[0]["origen"] == "intervencion"

    salida = generar_historial_vehiculo(
        repo.get_vehiculo(vid), repo.get_cliente(cid),
        repo.historial_vehiculo(vid), repo.get_empresa(), destino=tmp / "historial.pdf",
    )
    assert salida.is_file() and salida.stat().st_size > 1000


def test_actualizaciones_comparar_versiones():
    from taller import actualizaciones as a
    assert a._version_tupla("v1.11.0") == (1, 11, 0)
    assert a._version_tupla("1.9.10") < a._version_tupla("1.10.0")
    assert a.hay_version_nueva("1.11.1", actual="1.11.0")
    assert a.hay_version_nueva("1.11.0", actual="1.10.9")
    assert not a.hay_version_nueva("1.11.0", actual="1.11.0")
    assert not a.hay_version_nueva("1.10.0", actual="1.11.0")
    assert a.modo_instalacion() in ("appimage", "congelado", "git", "fuente")


def test_generar_manifiesto_latest_json():
    import json

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import generar_latest_json as g

    paquete = tmp / "taller-coches-9.9.9.tar.gz"
    paquete.write_bytes(b"contenido de prueba")
    salida = tmp / "latest.json"
    rc = g.main([
        "--version", "9.9.9", "--repo", "usuario/taller-coches",
        "--fuente", str(paquete), "--notas", "Notas de prueba",
        "--salida", str(salida),
    ])
    assert rc == 0
    m = json.loads(salida.read_text(encoding="utf-8"))
    assert m["version"] == "9.9.9"
    assert m["fuente"]["url"].endswith("v9.9.9/taller-coches-9.9.9.tar.gz")
    assert len(m["fuente"]["sha256"]) == 64
    assert g.sha256(paquete) == m["fuente"]["sha256"]


def test_numeracion_inicial_correlativa():
    db = Database()
    repo = Repository(db)
    cid = repo.save_cliente({"nombre": "Migración SL"})
    linea = [{"descripcion": "x", "cantidad": 1, "precio": 10, "iva_pct": 7}]

    # el taller ya emitió 560 facturas fuera del programa este año
    repo.set_numeracion_inicial(domain.FACTURA, 2026, 561)
    assert repo.proximo_numero(domain.FACTURA, 2026) == 561

    f1 = repo.crear_documento({"tipo": domain.FACTURA, "fecha": "2026-06-01",
                               "cliente_id": cid}, linea)
    assert repo.get_documento(f1)["numero"] == "FAC-2026-0561"

    f2 = repo.crear_documento({"tipo": domain.FACTURA, "fecha": "2026-06-02",
                               "cliente_id": cid}, linea)
    assert repo.get_documento(f2)["numero"] == "FAC-2026-0562"    # sigue correlativo

    # no se puede fijar por debajo de lo ya emitido
    try:
        repo.set_numeracion_inicial(domain.FACTURA, 2026, 100)
        assert False, "debería rechazar un número inferior al emitido"
    except ValueError:
        pass

    # se puede saltar hacia arriba (emitió más en papel) y sigue desde ahí
    repo.set_numeracion_inicial(domain.FACTURA, 2026, 600)
    f3 = repo.crear_documento({"tipo": domain.FACTURA, "fecha": "2026-06-03",
                               "cliente_id": cid}, linea)
    assert repo.get_documento(f3)["numero"] == "FAC-2026-0600"

    # otros tipos no se ven afectados por el ajuste de facturas
    esperado = repo.proximo_numero(domain.PRESUPUESTO, 2026)
    assert esperado < 500
    p1 = repo.crear_documento({"tipo": domain.PRESUPUESTO, "fecha": "2026-06-01",
                               "cliente_id": cid}, linea)
    assert repo.get_documento(p1)["numero"] == f"PRE-2026-{esperado:04d}"


def _firmar_licencia(priv, **campos):
    import base64 as _b64
    import json as _json
    d = {"cliente": "Cli", "nif": "", "emitida": "2026-01-01",
         "expira": "2099-01-01", "maquinas": None, "plan": "completo", "notas": ""}
    d.update(campos)
    payload = _json.dumps(d, sort_keys=True, separators=(",", ":")).encode()
    firma = priv.sign(payload)
    b = lambda x: _b64.urlsafe_b64encode(x).rstrip(b"=").decode()
    return b(payload) + "." + b(firma)


def test_licencia_firma_estados_y_prueba():
    import datetime as _dt

    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from taller import licencia

    priv = Ed25519PrivateKey.generate()
    pub_hex = priv.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()

    orig = licencia.CLAVE_PUBLICA_HEX
    licencia.CLAVE_PUBLICA_HEX = pub_hex
    try:
        db = Database()
        repo = Repository(db)

        def limpiar():
            for k in ("licencia_token", "prueba_inicio", "licencia_fecha_max"):
                db.execute("DELETE FROM meta WHERE clave = ?", (k,))
            db.commit()
            (licencia._ruta_fichero()).unlink(missing_ok=True)

        # licencia válida
        limpiar()
        tok = _firmar_licencia(priv, cliente="Taller Uno",
                               expira=(_dt.date.today() + _dt.timedelta(days=200)).isoformat())
        lic = licencia.guardar_token(repo, tok)
        assert lic.cliente == "Taller Uno"
        e = licencia.evaluar(repo)
        assert e.codigo == "activa" and e.puede_operar

        # a punto de caducar
        limpiar()
        db.execute("INSERT INTO meta VALUES ('licencia_token', ?)",
                   (_firmar_licencia(priv, expira=(_dt.date.today() + _dt.timedelta(days=5)).isoformat()),))
        db.commit()
        assert licencia.evaluar(repo).codigo == "por_caducar"

        # caducada -> bloqueo
        limpiar()
        db.execute("INSERT INTO meta VALUES ('licencia_token', ?)",
                   (_firmar_licencia(priv, expira="2020-01-01"),))
        db.commit()
        e = licencia.evaluar(repo)
        assert e.codigo == "caducada" and not e.puede_operar

        # firma manipulada -> inválida
        limpiar()
        malo = _firmar_licencia(priv)[:-4] + "AAAA"
        db.execute("INSERT INTO meta VALUES ('licencia_token', ?)", (malo,))
        db.commit()
        assert not licencia.evaluar(repo).puede_operar

        # atada a otra máquina
        limpiar()
        db.execute("INSERT INTO meta VALUES ('licencia_token', ?)",
                   (_firmar_licencia(priv, maquinas=["equipo-inexistente"]),))
        db.commit()
        assert licencia.evaluar(repo).codigo == "otra_maquina"

        # prueba: nueva instalación
        limpiar()
        assert licencia.evaluar(repo).codigo == "prueba"
        # prueba agotada
        db.execute("UPDATE meta SET valor = ? WHERE clave = 'prueba_inicio'",
                   ((_dt.date.today() - _dt.timedelta(days=40)).isoformat(),))
        db.execute("DELETE FROM meta WHERE clave = 'licencia_fecha_max'")
        db.commit()
        e = licencia.evaluar(repo)
        assert e.codigo == "prueba_fin" and not e.puede_operar

        limpiar()
    finally:
        licencia.CLAVE_PUBLICA_HEX = orig


def test_licencia_desactivada_sin_clave():
    from taller import licencia
    orig = licencia.CLAVE_PUBLICA_HEX
    licencia.CLAVE_PUBLICA_HEX = ""      # sin clave -> control de licencia inactivo
    try:
        e = licencia.evaluar(Repository(Database()))
        assert e.codigo == "desactivada" and e.puede_operar
        assert licencia.puede_operar() is True
    finally:
        licencia.CLAVE_PUBLICA_HEX = orig


if __name__ == "__main__":
    for nombre, fn in list(globals().items()):
        if nombre.startswith("test_") and callable(fn):
            fn()
            print(f"OK  {nombre}")
    print("\nTodas las pruebas pasaron.")
