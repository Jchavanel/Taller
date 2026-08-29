#!/usr/bin/env bash
# Genera un AppImage: UN SOLO FICHERO que se ejecuta con doble clic en cualquier
# Linux, sin instalar Python ni nada.
#
#   EJECUTAR UNA VEZ EN UN EQUIPO LINUX (no en Windows):
#       ./build_appimage.sh
#
#   Resultado:  dist/Taller-de-Coches-x86_64.AppImage
#
# Luego, en el taller: copiar ese fichero, botón derecho → «Permitir ejecutar
# como programa» (o el gestor de archivos ya lo hace) → doble clic.
set -e
APP_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$APP_DIR"
PY="${PYTHON:-python3}"
ARCH="$(uname -m)"
OUT="dist/Taller-de-Coches-${ARCH}.AppImage"

command -v "$PY" >/dev/null || { echo "Falta python3"; exit 1; }

echo ">> Entorno de compilación…"
"$PY" -m venv .build-venv
./.build-venv/bin/pip install --upgrade pip >/dev/null
./.build-venv/bin/pip install -r requirements.txt pyinstaller

echo ">> Empaquetando con PyInstaller…"
rm -rf build dist/taller-coches AppDir
./.build-venv/bin/pyinstaller \
    --name taller-coches --onedir --windowed --noconfirm \
    --collect-submodules taller \
    --add-data "taller/resources:taller/resources" \
    --hidden-import reportlab.graphics.barcode \
    run_app.py

echo ">> Montando AppDir…"
mkdir -p AppDir/usr/bin AppDir/usr/share/icons/hicolor/256x256/apps
cp -r dist/taller-coches/* AppDir/usr/bin/
cp taller/resources/icono.png AppDir/taller-de-coches.png
cp taller/resources/icono.png AppDir/usr/share/icons/hicolor/256x256/apps/taller-de-coches.png

cat > AppDir/taller-de-coches.desktop <<'EOF'
[Desktop Entry]
Type=Application
Name=Taller de Coches
Comment=Presupuestos, órdenes de trabajo, albaranes y facturas
Exec=taller-coches
Icon=taller-de-coches
Terminal=false
Categories=Office;Finance;
EOF

cat > AppDir/AppRun <<'EOF'
#!/bin/bash
HERE="$(dirname "$(readlink -f "${0}")")"
exec "${HERE}/usr/bin/taller-coches" "$@"
EOF
chmod +x AppDir/AppRun

echo ">> appimagetool…"
TOOL="./appimagetool-${ARCH}.AppImage"
if [ ! -x "$TOOL" ]; then
    URL="https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-${ARCH}.AppImage"
    echo "   descargando $URL"
    curl -L -o "$TOOL" "$URL" || wget -O "$TOOL" "$URL"
    chmod +x "$TOOL"
fi

mkdir -p dist
ARCH="$ARCH" "$TOOL" --no-appstream AppDir "$OUT" \
    || ARCH="$ARCH" "$TOOL" --no-appstream --appimage-extract-and-run AppDir "$OUT"

rm -rf AppDir build .build-venv
echo
echo "Listo:  $OUT"
echo "Cópialo al taller y ábrelo con doble clic. Los datos se guardan en"
echo "  ~/.local/share/taller-coches/"
