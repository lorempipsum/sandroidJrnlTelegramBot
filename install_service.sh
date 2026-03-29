#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="telegram_jrnl"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
BOT_DIR="/home/ubuntu/sandroidJrnlTelegramBot"

echo "Creating ${SERVICE_FILE} ..."

sudo tee "$SERVICE_FILE" > /dev/null <<EOF
[Unit]
Description=Telegram Jrnl Bot
After=network.target

[Service]
User=ubuntu
WorkingDirectory=${BOT_DIR}
EnvironmentFile=${BOT_DIR}/.env
ExecStart=/usr/bin/python3 ${BOT_DIR}/telegram_jrnl_bot.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

echo "Reloading systemd ..."
sudo systemctl daemon-reload

echo "Enabling and starting ${SERVICE_NAME} ..."
sudo systemctl enable --now "${SERVICE_NAME}.service"

echo "Done. Tailing logs (Ctrl+C to stop):"
sudo journalctl -u "$SERVICE_NAME" -f
