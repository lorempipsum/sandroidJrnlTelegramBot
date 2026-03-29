#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="telegram_jrnl"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
RUN_AS_USER="${SUDO_USER:-$USER}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BOT_DIR="${BOT_DIR:-$SCRIPT_DIR}"

if [[ ! -f "${BOT_DIR}/telegram_jrnl_bot.py" ]]; then
	echo "Error: ${BOT_DIR}/telegram_jrnl_bot.py not found"
	echo "Set BOT_DIR explicitly, e.g.: BOT_DIR=/path/to/sandroidJrnlTelegramBot ./install_service.sh"
	exit 1
fi

if [[ ! -f "${BOT_DIR}/.env" ]]; then
	echo "Error: ${BOT_DIR}/.env not found"
	echo "Create it first (or point BOT_DIR to the correct directory)."
	exit 1
fi

echo "Creating ${SERVICE_FILE} ..."
echo "Service will run as user: ${RUN_AS_USER}"
echo "Working directory: ${BOT_DIR}"

read -r -p "Proceed with service install/start? [y/N]: " CONFIRM
if [[ "${CONFIRM}" != "y" ]]; then
	echo "Aborted: no changes were made."
	exit 0
fi

sudo tee "$SERVICE_FILE" > /dev/null <<EOF
[Unit]
Description=Telegram Jrnl Bot
After=network.target

[Service]
User=${RUN_AS_USER}
WorkingDirectory=${BOT_DIR}
EnvironmentFile=${BOT_DIR}/.env
ExecStart=/usr/bin/python3 ${BOT_DIR}/telegram_jrnl_bot.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

echo "Reloading systemd ..."
sudo systemctl daemon-reload

echo "Enabling ${SERVICE_NAME} ..."
sudo systemctl enable --now "${SERVICE_NAME}.service"

echo "Restarting ${SERVICE_NAME} to apply latest .env and unit changes ..."
sudo systemctl restart "${SERVICE_NAME}.service"

echo "Done. Tailing logs (Ctrl+C to stop):"
sudo journalctl -u "$SERVICE_NAME" -f
