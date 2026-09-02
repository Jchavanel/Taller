#!/usr/bin/env bash
# Instala "Taller de Coches" para el usuario actual en Linux.
#  - Crea un entorno virtual con las dependencias (PySide6, reportlab).
#  - Añade el comando `taller-coches` y un lanzador en el menú de aplicaciones.
# No necesita permisos de root.
set -e

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
BIN_DIR="$HOME/.local/bin"
DESKTOP_DIR="$HOME/.local/share/applications"
PY="${PYTHON:-python3}"

msg()  { printf '\033[1;32m>> %s\033[0m\n' "$1"; }
warn() { printf '\033[1;33m!! %s\033[0m\n' "$1"; }

# ---------------------------------------------------------------- Python 3
if ! command -v "$PY" >/dev/null; then
    warn "No se encuentra python3."
    echo "   Debian/Ubuntu: sudo apt install python3 python3-venv"
    echo "   Fedora:        sudo dnf install python3"
    echo "   Arch:          sudo pacman -S python"
    exit 1
fi

PYVER=$("$PY" -c 'import sys;print("%d.%d"%sys.version_info[:2])')
msg "Python detectado: $PYVER"
"$PY" -c 'import sys;sys.exit(0 if sys.version_info[:2]>=(3,10) else 1)' || {
    warn "Se necesita Python 3.10 o superior (tienes $PYVER)."; exit 1;
}

# El módulo venv puede faltar en Debian/Ubuntu.
if ! "$PY" -c 'import venv' 2>/dev/null; then
    warn "Falta el módulo venv. Instálalo con:  sudo apt install python3-venv"
    exit 1
fi

# ---------------------------------------------------------------- entorno virtual
msg "Creando entorno virtual en .venv/ …"
"$PY" -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install --upgrade pip >/dev/null
msg "Instalando dependencias (puede tardar un par de minutos)…"
"$APP_DIR/.venv/bin/pip" install PySide6 reportlab cryptography spylls
# keyring es opcional (guarda la contraseña del correo en el llavero del sistema)
"$APP_DIR/.venv/bin/pip" install keyring 2>/dev/null || \
    warn "keyring no se pudo instalar; la contraseña del correo se guardará ofuscada."

# ---------------------------------------------------------------- comprobación Qt
msg "Comprobando que la interfaz gráfica arranca…"
if ! QT_QPA_PLATFORM=offscreen "$APP_DIR/.venv/bin/python" -c 'from PySide6.QtWidgets import QApplication; QApplication([])' 2>/tmp/taller_qt_err; then
    warn "PySide6 no ha podido inicializarse. Suele faltar alguna librería del sistema:"
    echo "   Debian/Ubuntu: sudo apt install libxcb-cursor0 libxcb-xinerama0 libxkbcommon-x11-0 libegl1 libcups2"
    echo "   Fedora:        sudo dnf install xcb-util-cursor libxkbcommon-x11 mesa-libEGL cups-libs"
    echo "   Detalle del error en /tmp/taller_qt_err"
    warn "Continúo con la instalación; corrige eso y vuelve a lanzar la app."
fi

# ---------------------------------------------------------------- lanzador de terminal
msg "Creando el comando 'taller-coches' en $BIN_DIR …"
mkdir -p "$BIN_DIR"
cat > "$BIN_DIR/taller-coches" <<EOF
#!/usr/bin/env bash
exec "$APP_DIR/.venv/bin/python" -m taller "\$@"
EOF
chmod +x "$BIN_DIR/taller-coches"

# ---------------------------------------------------------------- lanzador de menú
msg "Creando la entrada en el menú de aplicaciones…"
mkdir -p "$DESKTOP_DIR"
cat > "$DESKTOP_DIR/taller-coches.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Taller de Coches
Comment=Presupuestos, órdenes de trabajo, albaranes y facturas
Exec=$APP_DIR/.venv/bin/python -m taller
Path=$APP_DIR
Icon=$APP_DIR/taller/resources/icono.png
Terminal=false
Categories=Office;Finance;
StartupWMClass=Taller de Coches
EOF
update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true

echo
msg "Instalación completada."
echo "   • Menú de aplicaciones → «Taller de Coches»"
echo "   • Terminal → taller-coches"
case ":$PATH:" in
    *":$BIN_DIR:"*) ;;
    *) warn "Añade ~/.local/bin al PATH:  echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.bashrc" ;;
esac
echo
echo "   Los datos se guardan en:  $APP_DIR/datos/"
