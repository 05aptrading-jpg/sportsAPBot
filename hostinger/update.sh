#!/bin/bash
# MLB Bot — Actualizar en Hostinger
# Ejecutar: bash update.sh

set -e

cd /home/mlbbot/ApuestasMLB

echo "=== Actualizando MLB Bot ==="

# 1. Pull latest code
git pull origin main

# 2. Actualizar dependencias si cambió requirements
source venv/bin/activate
pip install -r requirements.txt -q
pip install -r futbol_bot/requirements.txt -q

# 3. Reiniciar servicio
sudo systemctl restart bot.service

echo "=== Bot actualizado y reiniciado ==="
echo "Logs: journalctl -u bot.service -f"
