"""Acceso a datos: CRUD de clientes, vehículos, artículos y documentos."""
from __future__ import annotations

import datetime as _dt
import sqlite3

from .database import Database
from . import domain


def _now() -> str:
    return _dt.datetime.now().isoformat(timespec="seconds")


def _fmt_cant(x: float) -> str:
    try:
        x = float(x)
    except (TypeError, ValueError):
        return "0"
    return str(int(x)) if x == int(x) else f"{x:.2f}".replace(".", ",")


def _today() -> str:
    return _dt.date.today().isoformat()


class Repository:
    def __init__(self, db: Database) -> None:
        self.db = db

    # ---------------------------------------------------------- ajustes (meta)
    def get_ajuste(self, clave: str, defecto: str = "") -> str:
        row = self.db.query_one("SELECT valor FROM meta WHERE clave = ?", (clave,))
        return row["valor"] if row else defecto

    def set_ajuste(self, clave: str, valor: str) -> None:
        self.db.execute(
            "INSERT INTO meta (clave, valor) VALUES (?, ?) "
            "ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor",
            (clave, str(valor)),
        )
        self.db.commit()

    # ------------------------------------------------------------------ empresa
    def get_empresa(self) -> sqlite3.Row:
        return self.db.query_one("SELECT * FROM empresa WHERE id = 1")

    def save_empresa(self, data: dict) -> None:
        campos = [
            "nombre", "nif", "direccion", "cp", "poblacion", "provincia",
            "telefono", "email", "iban", "iva_defecto", "logo_path", "pie_documento",
            "impuesto_nombre", "anticipo_pct",
            "cond_presupuesto", "cond_orden", "cond_albaran", "cond_factura",
            "smtp_host", "smtp_port", "smtp_seguridad", "smtp_usuario", "smtp_password",
            "smtp_remitente", "email_asunto", "email_cuerpo",
            "resenas_url", "whatsapp_plantilla", "whatsapp_tras_factura", "whatsapp_prefijo",
            "email_gestoria", "whatsapp_plantilla_doc",
        ]
        actual = self.get_empresa()
        sets = ", ".join(f"{c} = :{c}" for c in campos)
        params = {c: data[c] if c in data else actual[c] for c in campos}
        self.db.execute(f"UPDATE empresa SET {sets} WHERE id = 1", params)  # noqa: S608
        self.db.commit()

    def iva_defecto(self) -> float:
        row = self.db.query_one("SELECT iva_defecto FROM empresa WHERE id = 1")
        return float(row["iva_defecto"]) if row else 21.0

    # ----------------------------------------------------------------- clientes
    def list_clientes(self, filtro: str = "") -> list[sqlite3.Row]:
        if filtro:
            like = f"%{filtro}%"
            return self.db.query(
                "SELECT * FROM cliente WHERE nombre LIKE ? OR nif LIKE ? OR telefono LIKE ? "
                "ORDER BY nombre",
                (like, like, like),
            )
        return self.db.query("SELECT * FROM cliente ORDER BY nombre")

    def get_cliente(self, cliente_id: int) -> sqlite3.Row:
        return self.db.query_one("SELECT * FROM cliente WHERE id = ?", (cliente_id,))

    def save_cliente(self, data: dict) -> int:
        campos = ["nombre", "nif", "direccion", "cp", "poblacion", "provincia",
                  "telefono", "email", "notas"]
        if data.get("id"):
            sets = ", ".join(f"{c} = :{c}" for c in campos)
            params = {c: data.get(c, "") for c in campos}
            params["id"] = data["id"]
            self.db.execute(f"UPDATE cliente SET {sets} WHERE id = :id", params)  # noqa: S608
            self.db.commit()
            return int(data["id"])
        params = {c: data.get(c, "") for c in campos}
        params["creado"] = _now()
        cur = self.db.execute(
            "INSERT INTO cliente (nombre, nif, direccion, cp, poblacion, provincia, "
            "telefono, email, notas, creado) VALUES (:nombre, :nif, :direccion, :cp, "
            ":poblacion, :provincia, :telefono, :email, :notas, :creado)",
            params,
        )
        self.db.commit()
        return int(cur.lastrowid)

    def delete_cliente(self, cliente_id: int) -> None:
        self.db.execute("DELETE FROM cliente WHERE id = ?", (cliente_id,))
        self.db.commit()

    def cliente_tiene_documentos(self, cliente_id: int) -> bool:
        row = self.db.query_one(
            "SELECT COUNT(*) AS n FROM documento WHERE cliente_id = ?", (cliente_id,)
        )
        return row["n"] > 0

    def contar_documentos_cliente(self, cliente_id: int) -> dict:
        filas = self.db.query(
            "SELECT tipo, COUNT(*) AS n, COALESCE(SUM(total), 0) AS suma "
            "FROM documento WHERE cliente_id = ? GROUP BY tipo",
            (cliente_id,),
        )
        return {f["tipo"]: {"n": f["n"], "suma": f["suma"]} for f in filas}

    def guardar_cliente_con_vehiculos(self, data: dict, vehiculos: list[dict],
                                      eliminar_ids: list[int] | None = None) -> int:
        """Guarda el cliente y sincroniza sus vehículos en una sola operación.

        `vehiculos`: lista de dicts; los que traen 'id' se actualizan, el resto se crean.
        `eliminar_ids`: ids de vehículos a borrar (se ignora el que esté en uso).
        """
        cliente_id = self.save_cliente(data)
        for vid in (eliminar_ids or []):
            if not self.vehiculo_tiene_documentos(vid):
                self.db.execute("DELETE FROM vehiculo WHERE id = ?", (vid,))
        for v in vehiculos:
            v = {**v, "cliente_id": cliente_id}
            self.save_vehiculo(v)
        self.db.commit()
        return cliente_id

    # ---------------------------------------------------------------- vehículos
    def list_vehiculos(self, cliente_id: int | None = None, filtro: str = "") -> list[sqlite3.Row]:
        sql = (
            "SELECT v.*, c.nombre AS cliente_nombre FROM vehiculo v "
            "JOIN cliente c ON c.id = v.cliente_id"
        )
        cond = []
        params: list = []
        if cliente_id:
            cond.append("v.cliente_id = ?")
            params.append(cliente_id)
        if filtro:
            like = f"%{filtro}%"
            cond.append("(v.matricula LIKE ? OR v.marca LIKE ? OR v.modelo LIKE ? "
                        "OR v.bastidor LIKE ? OR c.nombre LIKE ?)")
            params += [like, like, like, like, like]
        if cond:
            sql += " WHERE " + " AND ".join(cond)
        sql += " ORDER BY v.matricula"
        return self.db.query(sql, tuple(params))

    def get_vehiculo(self, vehiculo_id: int) -> sqlite3.Row:
        return self.db.query_one(
            "SELECT v.*, c.nombre AS cliente_nombre FROM vehiculo v "
            "JOIN cliente c ON c.id = v.cliente_id WHERE v.id = ?",
            (vehiculo_id,),
        )

    def save_vehiculo(self, data: dict) -> int:
        campos = ["cliente_id", "matricula", "marca", "modelo", "bastidor",
                  "anio", "color", "combustible", "kms", "notas"]
        params = {c: data.get(c) for c in campos}
        for c in ("matricula", "marca", "modelo", "bastidor", "color", "combustible", "notas"):
            params[c] = params.get(c) or ""
        if data.get("id"):
            sets = ", ".join(f"{c} = :{c}" for c in campos)
            params["id"] = data["id"]
            self.db.execute(f"UPDATE vehiculo SET {sets} WHERE id = :id", params)  # noqa: S608
            self.db.commit()
            return int(data["id"])
        cur = self.db.execute(
            "INSERT INTO vehiculo (cliente_id, matricula, marca, modelo, bastidor, anio, "
            "color, combustible, kms, notas) VALUES (:cliente_id, :matricula, :marca, "
            ":modelo, :bastidor, :anio, :color, :combustible, :kms, :notas)",
            params,
        )
        self.db.commit()
        return int(cur.lastrowid)

    def delete_vehiculo(self, vehiculo_id: int) -> None:
        self.db.execute("DELETE FROM vehiculo WHERE id = ?", (vehiculo_id,))
        self.db.commit()

    def vehiculo_tiene_documentos(self, vehiculo_id: int) -> bool:
        row = self.db.query_one(
            "SELECT COUNT(*) AS n FROM documento WHERE vehiculo_id = ?", (vehiculo_id,)
        )
        return row["n"] > 0

    # ---------------------------------------------- historial / intervenciones
    def list_intervenciones(self, vehiculo_id: int) -> list[sqlite3.Row]:
        return self.db.query(
            "SELECT i.*, d.numero AS documento_numero, d.tipo AS documento_tipo "
            "FROM intervencion i LEFT JOIN documento d ON d.id = i.documento_id "
            "WHERE i.vehiculo_id = ? ORDER BY i.fecha DESC, i.id DESC",
            (vehiculo_id,),
        )

    def get_intervencion(self, intervencion_id: int) -> sqlite3.Row:
        return self.db.query_one(
            "SELECT * FROM intervencion WHERE id = ?", (intervencion_id,)
        )

    def save_intervencion(self, data: dict) -> int:
        campos = ["vehiculo_id", "fecha", "kms", "tipo", "titulo", "detalle",
                  "documento_id", "prox_fecha", "prox_kms"]
        params = {c: data.get(c) for c in campos}
        params["fecha"] = params.get("fecha") or _today()
        for c in ("tipo", "titulo", "detalle"):
            params[c] = params.get(c) or ""
        if data.get("id"):
            sets = ", ".join(f"{c} = :{c}" for c in campos)
            params["id"] = data["id"]
            self.db.execute(f"UPDATE intervencion SET {sets} WHERE id = :id", params)  # noqa: S608
            self.db.commit()
            return int(data["id"])
        params["creado"] = _now()
        cur = self.db.execute(
            "INSERT INTO intervencion (vehiculo_id, fecha, kms, tipo, titulo, detalle, "
            "documento_id, prox_fecha, prox_kms, creado) VALUES (:vehiculo_id, :fecha, :kms, "
            ":tipo, :titulo, :detalle, :documento_id, :prox_fecha, :prox_kms, :creado)",
            params,
        )
        self.db.commit()
        return int(cur.lastrowid)

    def delete_intervencion(self, intervencion_id: int) -> None:
        self.db.execute("DELETE FROM intervencion WHERE id = ?", (intervencion_id,))
        self.db.commit()

    def intervencion_desde_documento(self, documento_id: int) -> dict:
        """Prepara (sin guardar) los datos de una intervención a partir de un documento."""
        doc = self.get_documento(documento_id)
        lineas = self.get_lineas(documento_id)
        detalle = "\n".join(
            f"· {ln['descripcion']}" + (f" (x{_fmt_cant(ln['cantidad'])})"
                                        if ln["cantidad"] not in (1, 1.0) else "")
            for ln in lineas if ln["descripcion"]
        )
        return {
            "vehiculo_id": doc["vehiculo_id"],
            "fecha": doc["fecha"],
            "kms": doc["kms"],
            "tipo": domain.TIPO_DOC_A_INTERVENCION.get(doc["tipo"], "reparacion"),
            "titulo": f"{domain.TIPO_NOMBRE[doc['tipo']]} {doc['numero']}",
            "detalle": detalle,
            "documento_id": documento_id,
        }

    def historial_vehiculo(self, vehiculo_id: int) -> list[dict]:
        """Línea de tiempo unificada: intervenciones manuales + órdenes y facturas.

        Cada evento es un dict con claves comunes: origen, id, fecha, kms, tipo,
        titulo, detalle, documento_id, documento_numero, total.
        """
        eventos: list[dict] = []
        docs_en_intervencion = set()

        for iv in self.list_intervenciones(vehiculo_id):
            if iv["documento_id"]:
                docs_en_intervencion.add(iv["documento_id"])
            eventos.append({
                "origen": "intervencion",
                "id": iv["id"],
                "fecha": iv["fecha"],
                "kms": iv["kms"],
                "tipo": iv["tipo"],
                "tipo_nombre": domain.INTERVENCION_TIPOS.get(iv["tipo"], iv["tipo"]),
                "titulo": iv["titulo"] or domain.INTERVENCION_TIPOS.get(iv["tipo"], ""),
                "detalle": iv["detalle"],
                "documento_id": iv["documento_id"],
                "documento_numero": iv["documento_numero"],
                "prox_fecha": iv["prox_fecha"],
                "prox_kms": iv["prox_kms"],
                "total": None,
            })

        docs = self.db.query(
            "SELECT * FROM documento WHERE vehiculo_id = ? AND tipo IN ('orden', 'factura') "
            "ORDER BY fecha DESC, id DESC",
            (vehiculo_id,),
        )
        for d in docs:
            if d["id"] in docs_en_intervencion:
                continue  # ya representado por una intervención vinculada
            lineas = self.get_lineas(d["id"])
            detalle = "\n".join(
                f"· {ln['descripcion']}" + (f" (x{_fmt_cant(ln['cantidad'])})"
                                            if ln["cantidad"] not in (1, 1.0) else "")
                for ln in lineas if ln["descripcion"]
            )
            eventos.append({
                "origen": "documento",
                "id": d["id"],
                "fecha": d["fecha"],
                "kms": d["kms"],
                "tipo": d["tipo"],
                "tipo_nombre": domain.TIPO_NOMBRE[d["tipo"]],
                "titulo": f"{domain.TIPO_NOMBRE[d['tipo']]} {d['numero']}",
                "detalle": detalle,
                "documento_id": d["id"],
                "documento_numero": d["numero"],
                "prox_fecha": None,
                "prox_kms": None,
                "total": d["total"],
            })

        eventos.sort(key=lambda e: (e["fecha"], e["id"]), reverse=True)
        return eventos

    def documentos_de_vehiculo(self, vehiculo_id: int) -> list[sqlite3.Row]:
        return self.db.query(
            "SELECT id, tipo, numero, fecha, total FROM documento WHERE vehiculo_id = ? "
            "ORDER BY fecha DESC, id DESC",
            (vehiculo_id,),
        )

    def proxima_revision(self, vehiculo_id: int) -> dict | None:
        """Devuelve la próxima revisión pendiente más cercana (fecha o kms), si la hay."""
        row = self.db.query_one(
            "SELECT fecha, kms, prox_fecha, prox_kms FROM intervencion "
            "WHERE vehiculo_id = ? AND (prox_fecha IS NOT NULL OR prox_kms IS NOT NULL) "
            "ORDER BY fecha DESC, id DESC LIMIT 1",
            (vehiculo_id,),
        )
        if row is None:
            return None
        return {"prox_fecha": row["prox_fecha"], "prox_kms": row["prox_kms"]}

    # ---------------------------------------------------------------- artículos
    def list_articulos(self, filtro: str = "", solo_activos: bool = True) -> list[sqlite3.Row]:
        sql = "SELECT * FROM articulo"
        cond = []
        params: list = []
        if solo_activos:
            cond.append("activo = 1")
        if filtro:
            like = f"%{filtro}%"
            cond.append("(codigo LIKE ? OR descripcion LIKE ?)")
            params += [like, like]
        if cond:
            sql += " WHERE " + " AND ".join(cond)
        sql += " ORDER BY descripcion"
        return self.db.query(sql, tuple(params))

    def get_articulo(self, articulo_id: int) -> sqlite3.Row:
        return self.db.query_one("SELECT * FROM articulo WHERE id = ?", (articulo_id,))

    def save_articulo(self, data: dict) -> int:
        campos = ["codigo", "descripcion", "tipo", "precio", "iva_pct", "activo",
                  "canon_reciclaje", "canon_descripcion"]
        actual = self.get_articulo(data["id"]) if data.get("id") else None
        params = {c: (data[c] if c in data else (actual[c] if actual else None))
                  for c in campos}
        params["codigo"] = params.get("codigo") or ""
        params["canon_descripcion"] = params.get("canon_descripcion") or ""
        params["canon_reciclaje"] = float(params.get("canon_reciclaje") or 0)
        params["activo"] = 1 if data.get("activo", 1) else 0
        if data.get("id"):
            sets = ", ".join(f"{c} = :{c}" for c in campos)
            params["id"] = data["id"]
            self.db.execute(f"UPDATE articulo SET {sets} WHERE id = :id", params)  # noqa: S608
            self.db.commit()
            return int(data["id"])
        cols = ", ".join(campos)
        marc = ", ".join(f":{c}" for c in campos)
        cur = self.db.execute(
            f"INSERT INTO articulo ({cols}) VALUES ({marc})", params)  # noqa: S608
        self.db.commit()
        return int(cur.lastrowid)

    def delete_articulo(self, articulo_id: int) -> None:
        self.db.execute("DELETE FROM articulo WHERE id = ?", (articulo_id,))
        self.db.commit()

    def contar_articulos_con_iva_distinto(self, iva_pct: float) -> int:
        row = self.db.query_one(
            "SELECT COUNT(*) AS n FROM articulo WHERE ROUND(iva_pct, 2) <> ROUND(?, 2)",
            (iva_pct,),
        )
        return int(row["n"])

    def aplicar_impuesto_a_articulos(self, nuevo_iva: float) -> int:
        """Pone el mismo tipo impositivo a todos los artículos. Devuelve cuántos cambiaron."""
        cur = self.db.execute(
            "UPDATE articulo SET iva_pct = ? WHERE ROUND(iva_pct, 2) <> ROUND(?, 2)",
            (nuevo_iva, nuevo_iva),
        )
        self.db.commit()
        return cur.rowcount

    # --------------------------------------------------------------- documentos
    _SELECT_DOC = (
        "SELECT d.*, c.nombre AS cliente_nombre, v.matricula AS matricula, "
        "v.marca AS marca, v.modelo AS modelo "
        "FROM documento d LEFT JOIN cliente c ON c.id = d.cliente_id "
        "LEFT JOIN vehiculo v ON v.id = d.vehiculo_id"
    )

    def list_documentos(self, tipo: str | None = None, filtro: str = "",
                        limite: int | None = 500, en_curso: bool = False
                        ) -> list[sqlite3.Row]:
        sql = self._SELECT_DOC
        cond = []
        params: list = []
        if en_curso:
            cp = ",".join("?" * len(domain.CERRADO_PRESUPUESTO))
            co = ",".join("?" * len(domain.CERRADO_ORDEN))
            cond.append(f"((d.tipo = 'presupuesto' AND d.estado NOT IN ({cp})) OR "
                        f"(d.tipo = 'orden' AND d.estado NOT IN ({co})))")
            params += [*domain.CERRADO_PRESUPUESTO, *domain.CERRADO_ORDEN]
        elif tipo:
            cond.append("d.tipo = ?")
            params.append(tipo)
        if filtro:
            like = f"%{filtro}%"
            cond.append("(d.numero LIKE ? OR c.nombre LIKE ? OR v.matricula LIKE ? "
                        "OR v.marca LIKE ?)")
            params += [like, like, like, like]
        if cond:
            sql += " WHERE " + " AND ".join(cond)
        sql += " ORDER BY d.creado DESC, d.id DESC"
        if limite:
            sql += f" LIMIT {int(limite)}"
        return self.db.query(sql, tuple(params))

    def documentos_de_fecha(self, fecha_iso: str) -> list[sqlite3.Row]:
        return self.db.query(
            self._SELECT_DOC + " WHERE d.fecha = ? ORDER BY d.tipo, d.secuencia",
            (fecha_iso,),
        )

    def facturas_de_fecha(self, fecha_iso: str) -> list[sqlite3.Row]:
        """Solo facturas emitidas ese día, ordenadas por número."""
        return self.db.query(
            self._SELECT_DOC + " WHERE d.tipo = 'factura' AND d.fecha = ? "
            "ORDER BY d.secuencia",
            (fecha_iso,),
        )

    def fechas_con_documentos(self, anio: int, mes: int) -> dict:
        """{fecha_iso: {'n': nº docs, 'facturas': nº facturas}} para un mes."""
        prefijo = f"{anio:04d}-{mes:02d}-%"
        filas = self.db.query(
            "SELECT fecha, COUNT(*) AS n, "
            "SUM(CASE WHEN tipo = 'factura' THEN 1 ELSE 0 END) AS facturas "
            "FROM documento WHERE fecha LIKE ? GROUP BY fecha",
            (prefijo,),
        )
        return {f["fecha"]: {"n": f["n"], "facturas": f["facturas"]} for f in filas}

    def get_documento(self, documento_id: int) -> sqlite3.Row:
        return self.db.query_one(
            "SELECT d.*, c.nombre AS cliente_nombre, v.matricula AS matricula "
            "FROM documento d LEFT JOIN cliente c ON c.id = d.cliente_id "
            "LEFT JOIN vehiculo v ON v.id = d.vehiculo_id WHERE d.id = ?",
            (documento_id,),
        )

    def get_lineas(self, documento_id: int) -> list[sqlite3.Row]:
        return self.db.query(
            "SELECT * FROM linea WHERE documento_id = ? ORDER BY orden, id",
            (documento_id,),
        )

    def _siguiente_secuencia(self, tipo: str, anio: int) -> int:
        row = self.db.query_one(
            "SELECT COALESCE(MAX(secuencia), 0) AS m FROM documento WHERE tipo = ? AND anio = ?",
            (tipo, anio),
        )
        base = int(row["m"]) + 1
        forzado = self.db.query_one(
            "SELECT siguiente FROM numeracion WHERE tipo = ? AND anio = ?", (tipo, anio))
        if forzado and int(forzado["siguiente"]) > base:
            return int(forzado["siguiente"])
        return base

    # ------------------------------------------------------------- numeración
    def ultimo_numero(self, tipo: str, anio: int) -> int:
        """Mayor número ya emitido de ese tipo y año (0 si no hay ninguno)."""
        row = self.db.query_one(
            "SELECT COALESCE(MAX(secuencia), 0) AS m FROM documento WHERE tipo = ? AND anio = ?",
            (tipo, anio),
        )
        return int(row["m"])

    def proximo_numero(self, tipo: str, anio: int) -> int:
        """Número que se asignará al siguiente documento de ese tipo y año."""
        return self._siguiente_secuencia(tipo, anio)

    def get_numeracion_inicial(self, tipo: str, anio: int) -> int | None:
        row = self.db.query_one(
            "SELECT siguiente FROM numeracion WHERE tipo = ? AND anio = ?", (tipo, anio))
        return int(row["siguiente"]) if row else None

    def set_numeracion_inicial(self, tipo: str, anio: int, siguiente: int | None) -> None:
        """Fija el próximo número de ese tipo/año como un mínimo.

        No permite bajar por debajo de un documento ya emitido. ``None`` borra el ajuste.
        """
        if siguiente is None:
            self.db.execute("DELETE FROM numeracion WHERE tipo = ? AND anio = ?", (tipo, anio))
            self.db.commit()
            return
        siguiente = int(siguiente)
        maximo = self.ultimo_numero(tipo, anio)
        if siguiente <= maximo:
            raise ValueError(
                f"Ya hay un documento con el número {maximo}; el siguiente debe ser "
                f"mayor que {maximo}.")
        self.db.execute(
            "INSERT INTO numeracion (tipo, anio, siguiente) VALUES (?, ?, ?) "
            "ON CONFLICT(tipo, anio) DO UPDATE SET siguiente = excluded.siguiente",
            (tipo, anio, siguiente),
        )
        self.db.commit()

    def crear_documento(self, cabecera: dict, lineas: list[dict]) -> int:
        """Crea un documento nuevo asignando número correlativo. Devuelve el id."""
        fecha = cabecera.get("fecha") or _today()
        anio = int(fecha[:4])
        tipo = cabecera["tipo"]
        estado = cabecera.get("estado") or "abierto"
        if tipo == domain.FACTURA:
            estado = domain.normalizar_estado_factura(estado)
        totales = self._totales_desde_dicts(lineas, cabecera.get("descuento_pct", 0.0))

        # Reintenta si otra instancia ha cogido el mismo número entre el cálculo y el insert.
        secuencia = self._siguiente_secuencia(tipo, anio)
        for intento in range(20):
            numero = domain.formatear_numero(tipo, anio, secuencia)
            try:
                cur = self.db.execute(
                    "INSERT INTO documento (tipo, numero, anio, secuencia, fecha, cliente_id, "
                    "vehiculo_id, kms, estado, descuento_pct, observaciones, forma_pago, "
                    "origen_id, fecha_entrada, entrega_prevista, validez_dias, "
                    "base, cuota_iva, total, creado) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        tipo, numero, anio, secuencia, fecha,
                        cabecera.get("cliente_id"), cabecera.get("vehiculo_id"),
                        cabecera.get("kms"), estado,
                        cabecera.get("descuento_pct", 0.0),
                        cabecera.get("observaciones", ""),
                        cabecera.get("forma_pago", ""), cabecera.get("origen_id"),
                        cabecera.get("fecha_entrada"), cabecera.get("entrega_prevista"),
                        cabecera.get("validez_dias"),
                        totales.base, totales.cuota_iva, totales.total, _now(),
                    ),
                )
                break
            except sqlite3.IntegrityError as e:
                # solo reintentamos si el choque es por el número (UNIQUE); otro
                # fallo de integridad debe propagarse tal cual
                if intento == 19 or "UNIQUE" not in str(e).upper():
                    raise
                secuencia += 1
        doc_id = int(cur.lastrowid)
        self._reemplazar_lineas(doc_id, lineas)
        self.db.commit()
        self._sync_kms_vehiculo(cabecera.get("vehiculo_id"), cabecera.get("kms"))
        return doc_id

    def _sync_kms_vehiculo(self, vehiculo_id, kms) -> None:
        """Sube los km del documento a la ficha del vehículo si son mayores."""
        if not vehiculo_id or not kms:
            return
        v = self.get_vehiculo(vehiculo_id)
        if v is None:
            return
        if int(kms) > int(v["kms"] or 0):
            self.db.execute("UPDATE vehiculo SET kms = ? WHERE id = ?",
                            (int(kms), vehiculo_id))
            self.db.commit()

    def actualizar_documento(self, documento_id: int, cabecera: dict, lineas: list[dict]) -> None:
        totales = self._totales_desde_dicts(lineas, cabecera.get("descuento_pct", 0.0))
        actual = self.get_documento(documento_id)
        fecha = cabecera.get("fecha") or _today()
        nuevo_anio = int(str(fecha)[:4])
        estado = cabecera.get("estado") or "abierto"
        if (actual and actual["tipo"] == domain.FACTURA) or cabecera.get("tipo") == domain.FACTURA:
            estado = domain.normalizar_estado_factura(estado)

        # Si cambia el año, el número deja de ser correlativo: renumerar.
        # Las facturas no cambian de año/número (usa una rectificativa).
        if actual and nuevo_anio != actual["anio"] and actual["tipo"] != domain.FACTURA:
            sec = self._siguiente_secuencia(actual["tipo"], nuevo_anio)
            self.db.execute(
                "UPDATE documento SET anio = ?, secuencia = ?, numero = ? WHERE id = ?",
                (nuevo_anio, sec,
                 domain.formatear_numero(actual["tipo"], nuevo_anio, sec), documento_id),
            )
        elif actual and nuevo_anio != actual["anio"] and actual["tipo"] == domain.FACTURA:
            fecha = actual["fecha"]  # no se permite cambiar el año de una factura

        self.db.execute(
            "UPDATE documento SET fecha = ?, cliente_id = ?, vehiculo_id = ?, kms = ?, "
            "estado = ?, descuento_pct = ?, observaciones = ?, forma_pago = ?, "
            "fecha_entrada = ?, entrega_prevista = ?, validez_dias = ?, "
            "base = ?, cuota_iva = ?, total = ? WHERE id = ?",
            (
                fecha,
                cabecera.get("cliente_id"), cabecera.get("vehiculo_id"),
                cabecera.get("kms"), estado,
                cabecera.get("descuento_pct", 0.0), cabecera.get("observaciones", ""),
                cabecera.get("forma_pago", ""),
                cabecera.get("fecha_entrada"), cabecera.get("entrega_prevista"),
                cabecera.get("validez_dias"),
                totales.base, totales.cuota_iva, totales.total, documento_id,
            ),
        )
        self._reemplazar_lineas(documento_id, lineas)
        self.db.commit()
        self._sync_kms_vehiculo(cabecera.get("vehiculo_id"), cabecera.get("kms"))

    def _reemplazar_lineas(self, documento_id: int, lineas: list[dict]) -> None:
        self.db.execute("DELETE FROM linea WHERE documento_id = ?", (documento_id,))
        for i, ln in enumerate(lineas):
            self.db.execute(
                "INSERT INTO linea (documento_id, orden, tipo, codigo, descripcion, "
                "cantidad, precio, descuento_pct, iva_pct, es_canon) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    documento_id, i, ln.get("tipo", domain.LINEA_MATERIAL),
                    ln.get("codigo", ""), ln.get("descripcion", ""),
                    float(ln.get("cantidad", 0) or 0), float(ln.get("precio", 0) or 0),
                    float(ln.get("descuento_pct", 0) or 0), float(ln.get("iva_pct", 21) or 0),
                    1 if ln.get("es_canon") else 0,
                ),
            )

    @staticmethod
    def _totales_desde_dicts(lineas: list[dict], descuento_pct: float) -> domain.TotalesDoc:
        calc = [
            domain.LineaCalc(
                cantidad=float(ln.get("cantidad", 0) or 0),
                precio=float(ln.get("precio", 0) or 0),
                descuento_pct=float(ln.get("descuento_pct", 0) or 0),
                iva_pct=float(ln.get("iva_pct", 21) or 0),
            )
            for ln in lineas
        ]
        return domain.calcular_totales(calc, float(descuento_pct or 0))

    def delete_documento(self, documento_id: int) -> None:
        """Borra un documento. Las facturas NO se borran (usa anular_documento)."""
        doc = self.get_documento(documento_id)
        if doc is None:
            return
        if doc["tipo"] == domain.FACTURA:
            raise ValueError(
                "Una factura no se puede eliminar. Anúlala en su lugar: se conserva "
                "el número y queda registrada como anulada.")
        # quita las referencias de otros documentos a este (evita fallo de clave foránea)
        self.db.execute(
            "UPDATE documento SET origen_id = NULL WHERE origen_id = ?", (documento_id,)
        )
        self.db.execute(
            "UPDATE intervencion SET documento_id = NULL WHERE documento_id = ?",
            (documento_id,),
        )
        self.db.execute("DELETE FROM documento WHERE id = ?", (documento_id,))
        self.db.commit()

    def anular_documento(self, documento_id: int, motivo: str = "") -> None:
        """Marca un documento como anulado (se conserva íntegro y con su número)."""
        doc = self.get_documento(documento_id)
        if doc is None:
            return
        obs = (doc["observaciones"] or "").strip()
        sello = _dt.date.today().strftime("%d/%m/%Y")
        nota = f"[ANULADO {sello}]" + (f" {motivo}" if motivo else "")
        obs = f"{nota}\n{obs}".strip() if obs else nota
        self.db.execute(
            "UPDATE documento SET estado = 'anulado', observaciones = ? WHERE id = ?",
            (obs, documento_id),
        )
        self.db.commit()

    def documento_bloqueado(self, doc_row) -> bool:
        """True si el documento no debe editarse (factura anulada o cobrada)."""
        return (doc_row["tipo"] == domain.FACTURA
                and doc_row["estado"] in ("anulado", "cobrado"))

    def convertir_documento(self, documento_id: int, nuevo_tipo: str) -> int:
        """Genera un documento nuevo del tipo indicado copiando cabecera y líneas."""
        doc = self.get_documento(documento_id)
        if doc is None:
            raise ValueError("El documento no existe")
        if nuevo_tipo not in domain.CONVERSIONES.get(doc["tipo"], []):
            raise ValueError(
                f"No se puede convertir {domain.TIPO_NOMBRE[doc['tipo']]} "
                f"en {domain.TIPO_NOMBRE[nuevo_tipo]}"
            )
        lineas = [
            {
                "tipo": ln["tipo"], "codigo": ln["codigo"], "descripcion": ln["descripcion"],
                "cantidad": ln["cantidad"], "precio": ln["precio"],
                "descuento_pct": ln["descuento_pct"], "iva_pct": ln["iva_pct"],
                "es_canon": ln["es_canon"] if "es_canon" in ln.keys() else 0,
            }
            for ln in self.get_lineas(documento_id)
        ]
        cabecera = {
            "tipo": nuevo_tipo,
            "fecha": _today(),
            "cliente_id": doc["cliente_id"],
            "vehiculo_id": doc["vehiculo_id"],
            "kms": doc["kms"],
            "estado": "abierto",
            "descuento_pct": doc["descuento_pct"],
            "observaciones": doc["observaciones"],
            "forma_pago": doc["forma_pago"],
            "fecha_entrada": doc["fecha_entrada"],
            "entrega_prevista": doc["entrega_prevista"],
            "validez_dias": doc["validez_dias"] if nuevo_tipo == domain.PRESUPUESTO else None,
            "origen_id": documento_id,
        }
        nuevo_id = self.crear_documento(cabecera, lineas)
        # Marca el documento de origen como avanzado en el flujo.
        nuevo_estado = {
            domain.ORDEN: "aprobado",
            domain.ALBARAN: "finalizado",
            domain.FACTURA: "facturado",
        }.get(nuevo_tipo)
        if nuevo_estado:
            self.db.execute(
                "UPDATE documento SET estado = ? WHERE id = ?", (nuevo_estado, documento_id)
            )
            self.db.commit()
        return nuevo_id

    # ------------------------------------------------------- facturas de anticipo
    def _lineas_calc(self, documento_id: int) -> list[domain.LineaCalc]:
        return [
            domain.LineaCalc(cantidad=l["cantidad"], precio=l["precio"],
                             descuento_pct=l["descuento_pct"], iva_pct=l["iva_pct"])
            for l in self.get_lineas(documento_id)
        ]

    def crear_factura_anticipo(self, presupuesto_id: int, pct: float) -> int:
        """Emite una factura por el anticipo (pct % del presupuesto) con su impuesto."""
        pre = self.get_documento(presupuesto_id)
        if not pre or pre["tipo"] != domain.PRESUPUESTO:
            raise ValueError("Solo se puede facturar el anticipo de un presupuesto.")
        if not (0 < pct < 100):
            raise ValueError("El porcentaje del anticipo debe estar entre 1 y 99.")
        if self.db.query_one(
                "SELECT id FROM documento WHERE origen_id = ? AND factura_tipo = 'anticipo'",
                (presupuesto_id,)):
            raise ValueError("Este presupuesto ya tiene una factura de anticipo.")

        reparto = domain.desglose_anticipo(
            self._lineas_calc(presupuesto_id), pre["descuento_pct"], pct)
        if not reparto or sum(reparto.values()) <= 0:
            raise ValueError("El presupuesto no tiene importes que facturar.")

        un_solo = len(reparto) == 1
        lineas = []
        for rate, base in sorted(reparto.items()):
            desc = f"Anticipo {pct:g}% s/ presupuesto {pre['numero']}"
            if not un_solo:
                desc += f" (base al {rate:g}%)"
            lineas.append({"tipo": domain.LINEA_MATERIAL, "descripcion": desc,
                           "cantidad": 1, "precio": base, "descuento_pct": 0,
                           "iva_pct": rate})

        fid = self.crear_documento({
            "tipo": domain.FACTURA, "fecha": _today(),
            "cliente_id": pre["cliente_id"], "vehiculo_id": pre["vehiculo_id"],
            "kms": pre["kms"], "estado": "facturado", "descuento_pct": 0,
            "observaciones": (
                f"Factura de anticipo del {pct:g}% correspondiente al presupuesto "
                f"{pre['numero']}. El importe se regularizará en la factura final."),
            "forma_pago": pre["forma_pago"], "origen_id": presupuesto_id,
        }, lineas)
        self.db.execute(
            "UPDATE documento SET factura_tipo = 'anticipo', anticipo_pct = ? WHERE id = ?",
            (float(pct), fid))
        self.db.execute(
            "UPDATE documento SET estado = 'aprobado' WHERE id = ? "
            "AND estado NOT IN ('facturado','cobrado','anulado')", (presupuesto_id,))
        self.db.commit()
        return fid

    def crear_factura_final(self, anticipo_factura_id: int) -> int:
        """Emite la factura final: todo el trabajo del presupuesto menos el anticipo ya
        facturado."""
        ant = self.get_documento(anticipo_factura_id)
        if not ant or ant["factura_tipo"] != "anticipo":
            raise ValueError("Selecciona una factura de anticipo.")
        if self.db.query_one(
                "SELECT id FROM documento WHERE origen_id = ? AND factura_tipo = 'final'",
                (anticipo_factura_id,)):
            raise ValueError("Esta factura de anticipo ya tiene su factura final.")
        pre = self.get_documento(ant["origen_id"]) if ant["origen_id"] else None
        if not pre:
            raise ValueError("No se encuentra el presupuesto de origen del anticipo.")

        desc_gen = pre["descuento_pct"]
        lineas = [
            {"tipo": l["tipo"], "codigo": l["codigo"], "descripcion": l["descripcion"],
             "cantidad": l["cantidad"], "precio": l["precio"],
             "descuento_pct": l["descuento_pct"], "iva_pct": l["iva_pct"],
             "es_canon": l["es_canon"] if "es_canon" in l.keys() else 0}
            for l in self.get_lineas(pre["id"])
        ]
        for l in self.get_lineas(anticipo_factura_id):
            lineas.append({
                "tipo": domain.LINEA_MATERIAL,
                "descripcion": f"A deducir: anticipo ya facturado ({ant['numero']})",
                "cantidad": 1,
                "precio": domain.precio_deduccion_anticipo(l["precio"], desc_gen),
                "descuento_pct": 0, "iva_pct": l["iva_pct"],
            })

        fid = self.crear_documento({
            "tipo": domain.FACTURA, "fecha": _today(),
            "cliente_id": pre["cliente_id"], "vehiculo_id": pre["vehiculo_id"],
            "kms": pre["kms"], "estado": "facturado", "descuento_pct": desc_gen,
            "observaciones": (
                f"Factura final del presupuesto {pre['numero']}. Incluye la deducción "
                f"del anticipo facturado en {ant['numero']}."),
            "forma_pago": pre["forma_pago"], "origen_id": anticipo_factura_id,
        }, lineas)
        self.db.execute("UPDATE documento SET factura_tipo = 'final' WHERE id = ?", (fid,))
        self.db.execute("UPDATE documento SET estado = 'facturado' WHERE id = ?", (pre["id"],))
        self.db.commit()
        return fid

    # ------------------------------------------------------------------- varios
    def estadisticas(self) -> dict:
        def n(sql: str, p: tuple = ()) -> int:
            return int(self.db.query_one(sql, p)["n"])

        return {
            "clientes": n("SELECT COUNT(*) AS n FROM cliente"),
            "vehiculos": n("SELECT COUNT(*) AS n FROM vehiculo"),
            "articulos": n("SELECT COUNT(*) AS n FROM articulo"),
            "presupuestos": n("SELECT COUNT(*) AS n FROM documento WHERE tipo = 'presupuesto'"),
            "facturas": n("SELECT COUNT(*) AS n FROM documento WHERE tipo = 'factura'"),
        }
