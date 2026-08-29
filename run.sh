#!/usr/bin/env bash
# Arranca Taller de Coches usando el entorno virtual local.
set -e
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
    echo "Primer arranque: creando entorno virtual e instalando dependencias…"
    python3 -m venv .venv
    ./.venv/bin/pip install --upgrade pip >/dev/null
    ./.venv/bin/pip install -r requirements.txt
fi

exec ./.venv/bin/python -m taller "$@"
