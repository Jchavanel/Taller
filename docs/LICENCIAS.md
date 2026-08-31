# Sistema de licencias

Licencia **offline firmada** (Ed25519). El desarrollador firma cada licencia con su clave
privada; la aplicación la verifica con la clave pública incrustada. Sin servidor.

## Cómo funciona para el usuario final

- **Instalación nueva sin licencia**: funciona **30 días** completos (periodo de prueba).
- Cuando caduca la prueba o la licencia, el programa pasa a **modo consulta**: se puede
  abrir, ver, imprimir y exportar todo lo que ya hay, pero **no crear ni modificar**
  documentos, clientes, vehículos ni artículos. Una banda amarilla lo indica.
- **Archivo → Licencia…**: muestra el estado, permite pegar una licencia nueva y copiar la
  **huella de este equipo**.
- Aviso automático cuando faltan ≤ 15 días para caducar.
- La licencia se guarda en la base de datos y también en `datos/licencia.txt` (sobrevive a
  restaurar una copia de seguridad).
- Protección básica contra atrasar el reloj del sistema.

## Puesta en marcha (una sola vez)

1. Genera el par de claves **en tu equipo de desarrollo**:

   ```bash
   python scripts/generar_par_claves.py
   ```

   - Guarda la clave privada en `~/.taller-licencias/privada.pem`. **Haz copia de
     seguridad**: si la pierdes, no podrás emitir ni renovar licencias y habría que
     publicar una versión nueva con otra clave.
   - Imprime la clave pública en hex.

2. Pega la clave pública en [`taller/licencia.py`](../taller/licencia.py):

   ```python
   CLAVE_PUBLICA_HEX = "…los 64 caracteres hex…"
   ```

3. Publica una versión nueva (tag `vX.Y.Z`). A partir de ahí el control de licencia está
   activo. **Mientras `CLAVE_PUBLICA_HEX` esté vacía, todo funciona sin restricciones.**

## Emitir una licencia para un cliente

**Siempre átala al equipo del cliente.** Una licencia sin atar funciona en cualquier
ordenador con el programa hasta que caduca: si se filtra o el cliente la comparte, se
puede usar duplicada (el sistema es offline, no hay revocación).

1. El cliente te pasa la **huella de su equipo**: *Archivo → Licencia → botón «Copiar»*.
   Es un código como `a1b2c3d4e5f6a7b8c9d0`.
2. Emites la licencia con esa huella:

   ```bash
   python scripts/generar_licencia.py --cliente "Taller X, S.L." --nif B12345678 \
       --meses 12 --maquina a1b2c3d4e5f6a7b8c9d0
   ```

   - Varios equipos: repite `--maquina` por cada uno.
   - Hasta una fecha concreta en vez de meses: `--expira 2027-07-31`.

Si ejecutas el script **sin `--maquina`**, avisa y pide confirmación (escribe `SI`). Para
emitir a propósito una licencia sin atar (por ejemplo la tuya de propietario), añade
`--sin-maquina`.

La salida es **una sola línea**. Envíasela al cliente por correo. Él la pega en
**Archivo → Licencia → Activar licencia**.

Recomendación: licencias de cliente a **12 meses** y **atadas al equipo**. Así una copia
filtrada no sirve en otro ordenador y, en cualquier caso, caduca en un año.

## Renovar (tras el pago)

Emites otra licencia con la nueva fecha y se la envías. El cliente la pega encima de la
anterior. No hace falta desinstalar nada.

## Limitación

La aplicación es Python y se distribuye con su código fuente (o `.pyc` en el AppImage,
igual de legible). Este sistema **disuade la copia y ordena los cobros**, pero alguien con
conocimientos y acceso al código puede quitar la comprobación. Para endurecerlo habría que
compilar el binario con **Nuitka** o **Cython** (tarea aparte).
