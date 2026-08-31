# Taller de Coches

Aplicación de escritorio para la gestión de un taller de automoción. Funciona en local,
con base de datos en un único fichero SQLite (sin nube, sin servidor).

Permite llevar clientes, vehículos y un catálogo de artículos y servicios, y generar el
circuito completo de documentos:

**Presupuesto → Orden de trabajo → Albarán → Factura**

Cada documento se puede convertir en el siguiente con un clic (copiando cliente, vehículo
y líneas) y exportar a **PDF**.

## Pestañas

- **Documentos** — muestra por defecto solo el **trabajo en curso**: presupuestos
  pendientes de aceptar (para pasarlos a orden) y órdenes de trabajo sin terminar. En
  cuanto un presupuesto se convierte en orden, o una orden se termina/factura, desaparece
  de esta lista. El desplegable permite ver también «Todos» o un tipo concreto.
- **Calendario** — se elige un día y se ven todos los documentos de esa fecha (sobre todo
  **facturas**), con el total facturado del día. Los días con documentos aparecen
  resaltados (ámbar si hay factura, rosa si no). Doble clic para abrir.
- **Clientes**, **Vehículos**, **Artículos y servicios** — como antes.

Las facturas antiguas se consultan en el **Calendario** o en el **historial del
vehículo**, no en la pestaña Documentos.

## Formato de los documentos

Los PDF reproducen el modelo del taller: logo y datos fiscales en la cabecera, franja
roja, título con Nº / Fecha / Validez, bloques **DATOS DEL CLIENTE** (3×2) y **DATOS DEL
VEHÍCULO** (4×2), tabla **TRABAJOS, PIEZAS Y MATERIALES**, recuadro de totales a la
derecha (Base / impuesto / TOTAL / anticipo), bloque **AUTORIZACIÓN Y OBSERVACIONES**,
recuadros de firma cliente / taller y, al pie, las barras de **FORMA DE PAGO** con el
IBAN destacado en rojo.

- **Impuesto configurable**: IVA / IGIC / IPSI y tipo por defecto (en *Datos de mi taller*).
  Para Canarias viene **IGIC 7 %**.
- **Anticipo**: en presupuestos y órdenes se muestra el bloque de anticipo (50 % por
  defecto, configurable; 0 = sin bloque) con el desglose *anticipo / pendiente*.
- **Cada tipo muestra lo suyo**: «Validez … días» solo en presupuesto; firmas en
  presupuesto, orden y albarán (en albarán, «Recibí conforme»); la factura no lleva
  anticipo ni firmas.
- **Textos de condiciones** editables por tipo de documento en *Datos de mi taller*
  (botón «Restaurar textos por defecto» para volver a los de fábrica).
- Campos de la orden: **fecha de entrada** y **entrega prevista** del vehículo.

Al abrir la aplicación por primera vez con la base de datos vacía, si existe
`taller/resources/preconfig.json` se ofrecen esos datos y su logo. Se pueden cambiar en
*Datos de mi taller*.

La pestaña **Clientes** es una vista maestro-detalle: a la izquierda buscas y a la derecha
ves la **ficha completa** del cliente (datos personales, resumen de documentos y la tabla
de **todos sus vehículos**). Desde la ficha añades, editas o quitas vehículos y puedes
**imprimir la ficha en PDF**. Al dar de alta un cliente se le registran sus vehículos en
el mismo formulario; a partir del segundo coche simplemente pulsas *Añadir vehículo* otra
vez y queda asociado a su ficha.

## Configuración inicial

La configuración de un taller concreto (nombre, CIF, IBAN, IGIC…) se lee de
**`taller/resources/preconfig.json`** al primer arranque con la base de datos vacía. Ese
fichero **no se sube al repositorio** (lleva datos fiscales): parte de
`taller/resources/preconfig.example.json`, cópialo como `preconfig.json` y rellénalo, o
simplemente rellena los datos en *Archivo → Datos de mi taller* la primera vez.

## Licencia

El programa lleva un **control de licencia offline** (para su comercialización privada):

- Instalación nueva: **30 días de prueba**.
- Al caducar la prueba o la licencia → **modo consulta**: se puede ver, imprimir y
  exportar, pero no crear ni modificar. **Archivo → Licencia…** para activar una licencia.
- Se distribuye **desactivado** (`CLAVE_PUBLICA_HEX` vacía en
  [`taller/licencia.py`](taller/licencia.py)); se activa al generar el par de claves.
- Puesta en marcha y emisión de licencias: [`docs/LICENCIAS.md`](docs/LICENCIAS.md).

## Actualizaciones automáticas

La aplicación puede actualizarse sola desde **GitHub Releases**, sin llevar nada en un
pendrive:

- Al arrancar comprueba una vez al día si hay una versión nueva. También manualmente en
  **Ayuda → Buscar actualizaciones…**.
- Si la hay, muestra las notas y, si aceptas, **descarga el paquete, comprueba su huella
  SHA-256, lo instala y reinicia** la aplicación. La base de datos (`datos/`) no se toca
  y se hace una copia de seguridad antes.
- Funciona tanto con el **AppImage** (se sustituye el propio fichero) como con la
  instalación de código (`install.sh` / `run.sh`). Una copia clonada con git avisa de que
  se actualice con `git pull`.

**Puesta en marcha (una vez):** edita la constante `REPO` en
[`taller/actualizaciones.py`](taller/actualizaciones.py) con tu `usuario/repositorio` de
GitHub (o exporta `TALLER_UPDATE_REPO`). Para publicar cada versión, ver
[`PUBLICAR.md`](PUBLICAR.md).

## Aspecto

Interfaz con **paleta cálida** (cremas y arenas con el rojo del taller como acento),
pantalla de carga al arrancar y **tema claro / oscuro / automático** (según el sistema),
en **Ver → Tema**. La elección se guarda.

## Historial del vehículo

Cada vehículo lleva un **historial de intervenciones**: cuando el cliente vuelve al taller
ves de un vistazo todo lo que se le ha hecho al coche, con fecha y kilómetros.

- El historial **incluye automáticamente** todas las **órdenes de trabajo** y **facturas**
  del vehículo (con el detalle de los trabajos de cada una).
- Puedes añadir **intervenciones manuales** (revisiones, diagnósticos, trabajos en
  garantía, cambios de neumáticos…) con su texto libre.
- Desde cualquier documento: botón **Añadir al historial** → crea la intervención ya
  rellenada con los trabajos de ese documento.
- Cada intervención puede llevar una **próxima revisión** programada (por fecha y/o por
  kilómetros); el historial la muestra destacada.
- Botón **Imprimir historial (PDF)** para entregárselo al cliente o guardarlo.

Se abre haciendo **doble clic en el vehículo**, tanto en la ficha del cliente como en la
pestaña **Vehículos** (o con el botón *Historial del vehículo* / *Ver historial*). El alta
y la edición de vehículos se hacen con los botones correspondientes; el doble clic va
directo al historial, que es lo que más se consulta. También desde el editor de un
documento → *Historial*.

---

## Requisitos

- Linux (probado en Ubuntu / Debian). También funciona en Windows y macOS.
- Python 3.10 o superior.
- Paquetes del sistema:

  ```bash
  # Debian / Ubuntu
  sudo apt update
  sudo apt install python3 python3-venv python3-pip \
      libxcb-cursor0 libxcb-xinerama0 libxkbcommon-x11-0 libegl1 libcups2
  # Fedora
  sudo dnf install python3 xcb-util-cursor libxkbcommon-x11 mesa-libEGL cups-libs
  ```

  (`libcups2` / `cups-libs` lo necesita la impresión).

  (las últimas librerías las necesita la interfaz gráfica de Qt/PySide6).

## Instalación en Linux

1. Copia la carpeta `taller-coches/` al equipo Linux (por USB, `scp`, descarga…).
2. En una terminal, dentro de esa carpeta:

   ```bash
   chmod +x install.sh run.sh uninstall.sh
   ./install.sh
   ```

El instalador:

- comprueba la versión de Python y las librerías de Qt,
- crea un entorno virtual en `.venv/` con las dependencias (PySide6 y reportlab),
- añade el lanzador **«Taller de Coches»** al menú de aplicaciones,
- crea el comando `taller-coches` en `~/.local/bin`.

Para desinstalar: `./uninstall.sh` (no borra la carpeta `datos/`).

### Sin instalar nada en el sistema

```bash
./run.sh          # crea el entorno la primera vez y arranca la app
```

### AppImage — instalación con doble clic (recomendado para el taller)

Para no tener que instalar nada en los equipos del taller, genera **una vez, en
cualquier equipo Linux**, un AppImage:

```bash
./build_appimage.sh            # produce dist/Taller-de-Coches-x86_64.AppImage
```

Después, en cada equipo del taller: **copiar ese único fichero** y **doble clic** (si el
gestor de archivos no lo permite, botón derecho → *Propiedades → Permitir ejecutar como
programa*).

**Para que aparezca en el menú de aplicaciones como un programa más** (icono + lanzador),
ejecuta una vez:

```bash
./instalar_appimage.sh ~/Descargas/Taller-de-Coches-x86_64.AppImage
```

Deja el AppImage en `~/.local/bin/`, extrae el icono y crea la entrada de menú «Taller de
Coches». Para quitarlo: `./instalar_appimage.sh --desinstalar` (no borra los datos).

Los datos se guardan en `~/.local/share/taller-coches/`.

> En Ubuntu 24.04+ puede pedir `sudo apt install libfuse2t64` la primera vez
> (`libfuse2` en 22.04).

### Ejecutable independiente (carpeta)

```bash
./build_standalone.sh          # produce dist/taller-coches
```

Un ejecutable único (necesita las mismas librerías del sistema que el AppImage no
requiere). Los datos se guardan en `datos/` junto al ejecutable.

### Arranque

- Menú de aplicaciones → **Taller de Coches**, o
- Terminal → `taller-coches`, o
- sin instalar nada en el sistema: `./run.sh` (crea el entorno la primera vez).

## Uso en Windows / macOS (o manual en Linux)

```bash
python -m venv .venv
# Linux/macOS:
source .venv/bin/activate
# Windows:  .venv\Scripts\activate

pip install -r requirements.txt
python -m taller
```

---

## Primeros pasos

1. **Archivo → Datos de mi taller**: nombre, NIF/CIF, dirección, IBAN, logo y pie de
   página que aparecerán en los documentos.
2. **Archivo → Cargar artículos y servicios de ejemplo** (opcional): añade un catálogo
   típico de taller (horas de mano de obra, cambio de aceite, frenos, aceites, etc.)
   que luego puedes editar. Los artículos nuevos toman el **impuesto por defecto** de
   *Datos de mi taller* (IGIC 7% en Canarias). Para cambiar el de los artículos que ya
   tienes: pestaña **Artículos y servicios → «Aplicar [impuesto] a todos»**, o al
   cambiar el impuesto en *Datos de mi taller* la aplicación te ofrece hacerlo.
3. Pestaña **Clientes** → *Nuevo cliente*. En la misma ficha, con **Añadir vehículo**,
   le registras uno o varios coches sin salir del formulario.
4. Pestaña **Documentos** → *Nuevo presupuesto*. Añade líneas desde el catálogo
   («Añadir artículo») o escríbelas a mano («Añadir línea libre»). Los totales y el
   desglose de IVA se calculan solos.
6. Con el documento seleccionado:
   - **Imprimir…**: abre una **vista previa** desde la que se elige impresora, se ajusta
     el zoom/páginas y se imprime directamente (o «Imprimir a PDF»).
   - **Guardar PDF**: guarda el PDF en `datos/documentos/` y lo abre.
   - **Convertir…**: presupuesto → orden de trabajo → albarán → factura.

   También desde el editor de un documento: **Guardar e imprimir…**. La ficha del
   cliente y el historial del vehículo tienen su propio botón **Imprimir…**.

## Envío por correo electrónico

**Archivo → Configurar correo electrónico**: servidor SMTP, usuario, contraseña y las
plantillas de asunto y cuerpo (con marcadores `{numero}`, `{cliente}`, `{matricula}`,
`{total}`…). Botón **Probar conexión** para comprobar que funciona.

- Ajustes automáticos para **Gmail, Outlook/Office 365, Yahoo, iCloud, Zoho, IONOS y OVH**.
- **Otro (configuración manual)**: escribe a mano servidor, puerto y tipo de cifrado de
  cualquier proveedor.
- **Guardar proveedor…**: guarda esos datos con un nombre para reutilizarlos; aparecen en
  la lista marcados como «(guardado)» y se pueden eliminar. Se guardan en
  `datos/proveedores_correo.json`.

> Con **Gmail** y **Outlook** hay que usar una **contraseña de aplicación** (no la de la
> cuenta) y tener activada la verificación en dos pasos. La contraseña se guarda en el
> **llavero del sistema** (`keyring`) si está disponible; si no, ofuscada en la base de
> datos local.

Luego, con un documento seleccionado: **Enviar por correo…** genera el PDF, lo adjunta y
abre una ventana con el destinatario (rellenado con el email del cliente), asunto y
mensaje, todo editable antes de enviar.

## Numeración

Cada tipo de documento lleva su propia serie anual correlativa:

| Documento         | Formato          |
|-------------------|------------------|
| Presupuesto       | `PRE-2026-0001`  |
| Orden de trabajo  | `OT-2026-0001`   |
| Albarán           | `ALB-2026-0001`  |
| Factura           | `FAC-2026-0001`  |

El número se asigna al guardar y no se reutiliza.

**Continuar una numeración existente**: si el taller ya venía emitiendo documentos con
otro sistema (por ejemplo, 560 facturas este año), en **Archivo → Numeración de
documentos…** se indica desde qué número sigue cada serie (p. ej. factura 561). El
programa continúa correlativo a partir de ahí; si más adelante se emite un número mayor,
sigue desde ese último. No permite poner un número igual o inferior a uno ya emitido.

## Dónde se guardan los datos

Todo se guarda en la carpeta **`datos/` dentro de la propia carpeta del programa**:

```
taller-coches/
  datos/
    taller.db              ← base de datos
    logo.png
    registro.log           ← registro de errores
    documentos/            ← PDF generados (presupuestos, facturas, fichas, historiales)
    copias/                ← copias de seguridad automáticas
```

- **Archivo → Abrir carpeta de datos…** abre `datos/`.
- Si el programa está en una ruta sin permiso de escritura, usa como alternativa la
  carpeta de datos del usuario del sistema (`%APPDATA%\taller-coches` / `~/.local/share`).
- Al actualizar desde una versión anterior, los datos que estuvieran en la carpeta del
  sistema se **copian automáticamente** a `datos/` al arrancar (se conserva el original).

Al generar un PDF, la aplicación intenta abrirlo con el lector predeterminado. Si el
equipo no tiene ningún lector de PDF asociado (o la asociación está rota), abre la
carpeta que contiene el documento y muestra su ruta, en lugar de dar un error de
Windows.

### Copia de seguridad

La aplicación hace una **copia automática al arrancar** (una al día), en
`datos/copias/taller-AAAA-MM-DD-HHMMSS.db`, y conserva las últimas 20. Además:

- **Archivo → Copia de seguridad ahora**: fuerza una copia inmediata.
- **Archivo → Restaurar copia de seguridad**: sustituye la base de datos por una copia
  anterior (antes guarda el estado actual). La aplicación se cierra; vuelve a abrirla.

Para llevártelo a otro equipo o a la nube, copia la carpeta `datos/` entera.

Se puede forzar otra ubicación con variables de entorno:

```bash
TALLER_DATA_DIR=/media/usb/taller-datos   taller-coches   # carpeta completa
TALLER_DB=/media/usb/taller.db            taller-coches   # solo el fichero de BD
```

---

## Facturas

- Las facturas **no se pueden eliminar** (se perdería su número). Se **anulan**:
  *Documentos → Más → Anular…*. La factura anulada se conserva íntegra, mantiene su
  número, se registra el motivo y el PDF sale con la marca **ANULADO**.
- Una factura **anulada o cobrada** se abre en **solo lectura**. Para corregirla se emite
  una factura rectificativa.
- Los números de factura **nunca se reutilizan**.

## Nota fiscal

Esta versión emite facturas en PDF con numeración correlativa y desglose de impuesto,
pensada para uso interno del taller. **No** implementa todavía **VeriFactu** (huella
encadenada, QR y remisión a la AEAT).

- Canarias entra por **VeriFactu**, no por TicketBAI (que es solo País Vasco / Navarra).
- Fecha objetivo para tener el módulo listo: **julio de 2027** (confírmala con el asesor;
  las fechas del reglamento se han ido retrasando).
- El alcance y el plan por fases están en [`docs/VERIFACTU.md`](docs/VERIFACTU.md).

## Estructura del proyecto

```
taller/
  database.py        Esquema y conexión SQLite
  domain.py          Tipos de documento, cálculo de totales, numeración
  repository.py      Acceso a datos (CRUD y conversión de documentos)
  pdf_export.py      Generación de PDF (reportlab)
  seed.py            Catálogo de artículos de ejemplo
  paths.py           Rutas de datos (XDG)
  actualizaciones.py Comprobación e instalación de actualizaciones (GitHub Releases)
  licencia.py        Control de licencia offline (firma Ed25519)
  ui/
    main_window.py   Ventana principal y menús
    actualizador.py  Diálogos y descarga en segundo plano de actualizaciones
    licencia_dialog.py  Diálogo Archivo → Licencia
    tabs.py          Pestañas de documentos, clientes, vehículos y artículos
    dialogs.py       Altas/edición de cliente, vehículo, artículo, taller e intervención
    documento_editor.py  Editor de documento con líneas y totales en vivo
    historial.py     Historial de intervenciones y trabajos por vehículo
tests/
  test_smoke.py      Pruebas sin interfaz (lógica + generación de PDF)
```

## Pruebas

```bash
python tests/test_smoke.py
```

Comprueban cálculos de impuesto, numeración, el flujo presupuesto→factura, la ficha de
cliente, el historial y la generación de los PDF. La comprobación del *texto* dentro del
PDF necesita `pymupdf` (opcional: `pip install pymupdf`); si no está, esa parte se omite.
