#!/usr/bin/env bash
# Empaqueta el código en dist/taller-coches-<version>.tar.gz para distribuirlo / actualizar.
# Funciona en Git Bash (Windows), Linux y en GitHub Actions.
set -e
cd "$(dirname "$0")"

VERSION=$(grep -E '^__version__' taller/__init__.py | sed 's/.*"\(.*\)".*/\1/')
PREFIJO="taller-coches-${VERSION}"
OUT="dist/${PREFIJO}.tar.gz"
mkdir -p dist

if git rev-parse --git-dir >/dev/null 2>&1; then
    # Repositorio git: archivo limpio y reproducible con prefijo normalizado.
    git archive --format=tar.gz --prefix="${PREFIJO}/" -o "$OUT" HEAD
else
    # Sin git: empaqueta la carpeta actual excluyendo lo que no debe viajar.
    TMP=$(mktemp -d)
    mkdir "$TMP/$PREFIJO"
    tar --exclude='./.venv' --exclude='./.build-venv' --exclude='./venv' \
        --exclude='./datos' --exclude='./dist' --exclude='./build' \
        --exclude='./AppDir' --exclude='./.git' --exclude='./appimagetool-*' \
        --exclude='*/__pycache__' --exclude='*.pyc' --exclude='*.spec' \
        --exclude='./taller/resources/preconfig.json' \
        -cf - . | tar -C "$TMP/$PREFIJO" -xf -
    tar -C "$TMP" -czf "$OUT" "$PREFIJO"
    rm -rf "$TMP"
fi

echo "Creado: $OUT"
du -h "$OUT"
