#!/usr/bin/env bash
# Integra el AppImage de "Taller de Coches" en el sistema: lo deja en una ubicación
# fija, con icono y entrada en el menú de aplicaciones, como un programa más.
#
#   ./instalar_appimage.sh [ruta/al/Taller-de-Coches-x86_64.AppImage]
#
# Si no se indica ruta, busca un "Taller-de-Coches*.AppImage" en la carpeta actual,
# en ~/Descargas y en ~/Downloads.
#
# Para desinstalar:  ./instalar_appimage.sh --desinstalar
set -e

NOMBRE="Taller de Coches"
ID="taller-de-coches"
DEST_BIN="$HOME/.local/bin"
DEST_APP="$DEST_BIN/Taller-de-Coches.AppImage"
DEST_DESKTOP="$HOME/.local/share/applications/${ID}.desktop"
DEST_ICONO_DIR="$HOME/.local/share/icons/hicolor/256x256/apps"

msg()  { printf '\033[1;32m>> %s\033[0m\n' "$1"; }
warn() { printf '\033[1;33m!! %s\033[0m\n' "$1"; }

if [ "$1" = "--desinstalar" ] || [ "$1" = "-u" ]; then
    rm -f "$DEST_APP" "$DEST_DESKTOP" "$DEST_ICONO_DIR/${ID}.png"
    update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true
    msg "Desinstalado. Los datos en ~/.local/share/taller-coches/ se conservan."
    exit 0
fi

# ---------------------------------------------------------------- localizar AppImage
ORIGEN="$1"
if [ -z "$ORIGEN" ]; then
    for d in . "$HOME/Descargas" "$HOME/Downloads"; do
        cand=$(ls -1 "$d"/Taller-de-Coches*.AppImage 2>/dev/null | head -n1 || true)
        [ -n "$cand" ] && { ORIGEN="$cand"; break; }
    done
fi
[ -n "$ORIGEN" ] && [ -f "$ORIGEN" ] || {
    warn "No encuentro el AppImage. Pásalo como argumento:"
    echo "   ./instalar_appimage.sh ~/Descargas/Taller-de-Coches-x86_64.AppImage"
    exit 1
}
ORIGEN=$(readlink -f "$ORIGEN")
msg "AppImage: $ORIGEN"

# ---------------------------------------------------------------- dependencia FUSE
if ! "$ORIGEN" --appimage-version >/dev/null 2>&1; then
    if ldconfig -p 2>/dev/null | grep -q 'libfuse\.so\.2'; then :; else
        warn "Puede faltar libfuse2 (necesaria para ejecutar AppImages):"
        echo "   Debian/Ubuntu 22.04:  sudo apt install libfuse2"
        echo "   Ubuntu 24.04+:        sudo apt install libfuse2t64"
        echo "   Fedora:               sudo dnf install fuse-libs"
    fi
fi

# ---------------------------------------------------------------- copiar a sitio fijo
mkdir -p "$DEST_BIN" "$DEST_ICONO_DIR"
if [ "$ORIGEN" != "$DEST_APP" ]; then
    cp "$ORIGEN" "$DEST_APP"
fi
chmod +x "$DEST_APP"
msg "Instalado en $DEST_APP"

# ---------------------------------------------------------------- icono
TMP=$(mktemp -d)
ICON_LINE="Icon=applications-office"
(
    cd "$TMP"
    "$DEST_APP" --appimage-extract "${ID}.png" >/dev/null 2>&1 || true
    "$DEST_APP" --appimage-extract ".DirIcon"  >/dev/null 2>&1 || true
)
for cand in "$TMP/squashfs-root/${ID}.png" \
            "$TMP/squashfs-root/usr/share/icons/hicolor/256x256/apps/${ID}.png" \
            "$TMP/squashfs-root/.DirIcon"; do
    if [ -f "$cand" ]; then
        cp "$cand" "$DEST_ICONO_DIR/${ID}.png"
        ICON_LINE="Icon=${ID}"
        msg "Icono instalado"
        break
    fi
done
[ "$ICON_LINE" = "Icon=applications-office" ] && warn "No se pudo extraer el icono; se usa uno genérico."
rm -rf "$TMP"

# ---------------------------------------------------------------- entrada de menú
cat > "$DEST_DESKTOP" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=${NOMBRE}
Comment=Presupuestos, órdenes de trabajo, albaranes y facturas
Exec="${DEST_APP}" %U
${ICON_LINE}
Terminal=false
Categories=Office;Finance;
StartupWMClass=${NOMBRE}
EOF
chmod +x "$DEST_DESKTOP"
update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true
gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true

echo
msg "Listo. Busca «${NOMBRE}» en el menú de aplicaciones."
echo "   (si no aparece de inmediato, cierra y vuelve a abrir la sesión)"
echo "   • Datos:            ~/.local/share/taller-coches/"
echo "   • Actualizaciones:  Ayuda → Buscar actualizaciones…  (versión 1.11.0 o superior)"
case ":$PATH:" in
    *":$DEST_BIN:"*) echo "   • Terminal:         Taller-de-Coches.AppImage" ;;
    *) : ;;
esac
