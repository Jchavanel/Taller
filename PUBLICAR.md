# Publicar una versión nueva

La aplicación instalada en el taller se actualiza sola desde **GitHub Releases**. Para
sacar una versión nueva:

## 1. Preparar el repositorio (solo la primera vez)

1. Crea un repositorio **público** en GitHub, p. ej. `TU_USUARIO/taller-coches`.
2. Edita la constante `REPO` en [`taller/actualizaciones.py`](taller/actualizaciones.py):

   ```python
   REPO = os.environ.get("TALLER_UPDATE_REPO", "TU_USUARIO/taller-coches")
   ```

3. Sube el código:

   ```bash
   git init
   git add .
   git commit -m "Versión inicial"
   git branch -M main
   git remote add origin https://github.com/TU_USUARIO/taller-coches.git
   git push -u origin main
   ```

`taller/resources/preconfig.json` (datos fiscales del taller) está en `.gitignore` y **no
se sube**. Guárdalo aparte; el PC del taller ya lo tiene aplicado en su base de datos.

## 2. Cada versión nueva

1. Cambia el número de versión en **dos sitios** (deben coincidir):
   - `taller/__init__.py` → `__version__`
   - `pyproject.toml` → `version`
2. Comprueba que las pruebas pasan:

   ```bash
   python tests/test_smoke.py
   ```

3. Haz commit y crea una **etiqueta** `vX.Y.Z` cuyo mensaje son las notas que verá el
   taller:

   ```bash
   git add -A
   git commit -m "vX.Y.Z: descripción breve"
   git tag -a vX.Y.Z -m "Novedades de esta versión:
   - ...
   - ..."
   git push && git push origin vX.Y.Z
   ```

4. Al recibir la etiqueta, GitHub Actions
   ([`.github/workflows/release.yml`](.github/workflows/release.yml)):
   - comprueba que `vX.Y.Z` coincide con `taller.__version__`,
   - construye el **AppImage** y el **paquete de código**,
   - genera `latest.json` con las huellas SHA-256,
   - publica la **release** con esos tres ficheros adjuntos.

5. En cuestión de minutos, cada taller verá el aviso de actualización al abrir la
   aplicación (o en *Ayuda → Buscar actualizaciones…*).

## Publicar el manifiesto a mano (sin GitHub Actions)

```bash
bash make_dist.sh
bash build_appimage.sh                     # en un equipo Linux
python scripts/generar_latest_json.py \
    --version X.Y.Z --repo TU_USUARIO/taller-coches \
    --appimage dist/Taller-de-Coches-x86_64.AppImage \
    --fuente   dist/taller-coches-X.Y.Z.tar.gz \
    --notas    "Novedades..." \
    --salida   dist/latest.json
```

Luego crea la release `vX.Y.Z` en GitHub y sube esos tres ficheros
(`Taller-de-Coches-x86_64.AppImage`, `taller-coches-X.Y.Z.tar.gz`, `latest.json`).

## Cómo lo comprueba la aplicación

- Descarga `https://github.com/TU_USUARIO/taller-coches/releases/latest/download/latest.json`
  (URL fija que siempre apunta a la última release).
- Compara `version` con la instalada; si es mayor, ofrece actualizar.
- Descarga el paquete que corresponda (`appimage` o `fuente`), verifica el `sha256` y lo
  aplica. Antes hace copia de seguridad de la base de datos.

Para probar sin publicar nada: `TALLER_UPDATE_URL=file:///ruta/latest.json`.
