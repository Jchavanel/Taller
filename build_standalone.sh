#!/usr/bin/env bash
# Genera un ejecutable independiente para Linux (no necesita Python instalado).
# EJECUTAR EN LA MÁQUINA LINUX de destino (o una con la misma distribución).
#
#   ./build_standalone.sh
#
# Resultado:  dist/taller-coches   (un único archivo ejecutable)
set -e
APP_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$APP_DIR"

PY="${PYTHON:-python3}"
"$PY" -m venv .build-venv
./.build-venv/bin/pip install --upgrade pip >/dev/null
./.build-venv/bin/pip install -r requirements.txt pyinstaller

./.build-venv/bin/pyinstaller \
    --name taller-coches \
    --onefile \
    --windowed \
    --collect-submodules taller \
    --add-data "taller/resources:taller/resources" \
    --hidden-import reportlab.graphics.barcode \
    --collect-all spylls \
    run_app.py

echo
echo "Listo:  $APP_DIR/dist/taller-coches"
echo "Cópialo donde quieras y ejecútalo con doble clic o ./taller-coches"
echo "Los datos se guardan junto al ejecutable, en ./datos/"
