#!/bin/bash
# MLB Bot — Iniciar manualmente en Hostinger
# Ejecutar: bash start.sh

cd /home/mlbbot/ApuestasMLB
source venv/bin/activate

echo "=== Iniciando MLB Bot ==="
echo "Puerto: ${PORT:-8000}"
echo "Logs: Ctrl+C para salir"

python -m uvicorn railway_app.main:app --host 0.0.0.0 --port ${PORT:-8000}
