#!/usr/bin/env bash
set -euo pipefail

# Script to reload systemd daemon, enable+restart the telegram_jrnl service, and follow its journal.
# Usage: ./manage_telegram_service.sh  (or: bash manage_telegram_service.sh)

SERVICE_NAME="telegram_jrnl"

if ! command -v systemctl >/dev/null 2>&1; then
  echo "Error: systemctl not found. This script must be run on a systemd Linux host." >&2
  exit 1
fi

# Use sudo for commands if not running as root
SUDO=""
if [[ $EUID -ne 0 ]]; then
  SUDO="sudo"
fi

echo "Reloading systemd daemon..."
$SUDO systemctl daemon-reload

echo "Enabling ${SERVICE_NAME}..."
$SUDO systemctl enable --now "${SERVICE_NAME}.service"

echo "Restarting ${SERVICE_NAME} to apply latest .env and unit changes..."
$SUDO systemctl restart "${SERVICE_NAME}.service"

echo "Tailing journal for ${SERVICE_NAME} (press Ctrl+C to exit)..."
exec $SUDO journalctl -u "${SERVICE_NAME}" -f
