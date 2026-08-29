#!/usr/bin/env bash
# Desinstala "Taller de Coches" (deja intacta la carpeta datos/).
set -e
APP_DIR="$(cd "$(dirname "$0")" && pwd)"

rm -f "$HOME/.local/bin/taller-coches"
rm -f "$HOME/.local/share/applications/taller-coches.desktop"
update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true
rm -rf "$APP_DIR/.venv"

echo "Desinstalado."
echo "Tus datos siguen en:  $APP_DIR/datos/   (bórralos a mano si ya no los necesitas)"
