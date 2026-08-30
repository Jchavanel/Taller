# VeriFactu — alcance y plan (pendiente)

> **Estado: aplazado.** Fecha objetivo para tenerlo operativo: **julio de 2027**.
> Confirmar con el asesor fiscal: fecha límite real, modalidad y quién firma la
> declaración responsable del fabricante. Las fechas del reglamento se han retrasado
> varias veces.

## Contexto

- Base legal: Ley 11/2021 antifraude → RD 1007/2023 (Reglamento VeriFactu) →
  Orden HAC/1177/2024 (especificación técnica: formato de registro, huella, XML, eventos).
- **Canarias → VeriFactu** (los registros van a la AEAT aunque el impuesto sea IGIC).
  TicketBAI es solo País Vasco y Navarra.
- Este software es de desarrollo propio para un único taller → el taller asume la
  **declaración responsable** de cumplimiento.

## Modalidad elegida (provisional): VERI\*FACTU (envío a la AEAT)

Menos riesgo de incumplimiento que el modo local firmado. Cada registro se remite a la
AEAT por servicio web en el momento de emitir la factura.

## Requisitos

1. **Registro de facturación** por cada alta y cada anulación de factura, con campos
   normalizados (NIF emisor, serie+número, fecha, desglose por tipo, total, tipo de
   sistema, identificación del software: nombre, versión, NIF del desarrollador).
2. **Huella SHA-256 encadenada**: cada registro incluye el hash del anterior.
3. **Marca de tiempo** de cada registro.
4. **Código QR** en la factura (PDF e impresa) con enlace a la sede de la AEAT + leyenda
   "Factura verificable en la sede electrónica de la AEAT" / "VERI\*FACTU".
5. **Registro de eventos**: arranque, cierre, cambios de configuración, incidencias.
6. **Envío por servicio web** (XML/SOAP) con **certificado electrónico** del emisor;
   cola offline con reintentos si no hay conexión.

## Lo que ya está resuelto en el software

- Numeración correlativa por serie y año, sin reutilizar números.
- Facturas no borrables, solo anulables (motivo + marca ANULADO).
- Dinero con `Decimal` y redondeo fiscal; desglose por tipo impositivo.
- Esquema SQLite versionado con migraciones (`taller/database.py`).

## Plan por fases

### Fase 1 — base local (no depende de la AEAT ni del certificado)
- Tablas `registro_facturacion` y `evento` (nueva `SCHEMA_VERSION`).
- Cálculo de la huella con el algoritmo y orden de campos oficiales.
- Encadenado al guardar/anular una factura (`repository.py`).
- QR + leyendas en `pdf_export.py`.
- Registro de eventos básico enganchado a `main_window.run()` y cierre.

### Fase 2 — integración AEAT en pruebas
- Generación del XML del registro según Orden HAC/1177/2024.
- Cliente del servicio web contra el **entorno de preproducción** de la AEAT.
- Cola de envío con reintentos y estado por registro.
- Nueva dependencia para firma XML (`cryptography` + `xmlsec` o equivalente).

### Fase 3 — producción
- Carga y gestión del certificado electrónico (PIN, aviso de caducidad).
- Registro de eventos completo.
- Validación final y paso a producción.
- Documentación para la declaración responsable.

## Notas de implementación

- Mantener todo esto **desactivado por defecto** hasta Fase 3, con un ajuste en
  *Datos de mi taller* → "Facturación VeriFactu" (desactivado / preproducción / producción).
- No romper la numeración ni el flujo actual de facturas mientras se desarrolla.
- Las facturas emitidas antes de activar VeriFactu quedan como están (no se re-registran).
