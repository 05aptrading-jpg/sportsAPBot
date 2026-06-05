#!/bin/bash
# MLB Bot — Setup para Hostinger VPS
# Ejecutar como root: bash setup.sh

set -e

echo "=== MLB Bot Setup para Hostinger ==="

# 1. Actualizar sistema
apt update && apt upgrade -y

# 2. Instalar Python, pip, git
apt install -y python3 python3-pip python3-venv git

# 3. Crear usuario del bot
if ! id -u mlbbot &>/dev/null; then
    useradd -m -s /bin/bash mlbbot
    echo "Usuario mlbbot creado"
fi

# 4. Clonar repo
su - mlbbot -c "
    cd ~
    if [ -d ApuestasMLB ]; then
        cd ApuestasMLB && git pull
    else
        git clone https://github.com/05aptrading-jpg/ApuestasMLB.git
        cd ApuestasMLB
    fi

    # 5. Crear virtualenv
    python3 -m venv venv
    source venv/bin/activate

    # 6. Instalar dependencias
    pip install --upgrade pip
    pip install -r requirements.txt
    pip install -r futbol_bot/requirements.txt
"

# 7. Copiar service file
cp /home/mlbbot/ApuestasMLB/hostinger/bot.service /etc/systemd/system/bot.service

# 8. Copiar env file
if [ ! -f /home/mlbbot/ApuestasMLB/.env ]; then
    cp /home/mlbbot/ApuestasMLB/hostinger/env.example /home/mlbbot/ApuestasMLB/.env
    echo "编辑 /home/mlbbot/ApuestasMLB/.env con tus tokens"
fi

# 9. Activar servicio
systemctl daemon-reload
systemctl enable bot.service

echo ""
echo "=== Setup completado ==="
echo "1. Edita: nano /home/mlbbot/ApuestasMLB/.env"
echo "2. Inicia: systemctl start bot.service"
echo "3. Logs:   journalctl -u bot.service -f"
