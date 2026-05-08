#!/bin/bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${VENV_DIR:-$APP_DIR/.venv}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
SERVICE_NAME="${SERVICE_NAME:-saas-mortgage}"
SERVICE_TEMPLATE="${SERVICE_TEMPLATE:-$APP_DIR/deploy/saas-mortgage.service}"

echo "Deploying from: $APP_DIR"
cd "$APP_DIR"

if [ ! -d "$VENV_DIR" ]; then
  echo "Creating virtual environment at $VENV_DIR"
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"

echo "Installing Python dependencies"
pip install -r requirements.txt

if [ -d "$APP_DIR/migrations" ]; then
  echo "Applying database migrations"
  export FLASK_APP="app:create_app"
  flask db upgrade
fi

if [ -f "$SERVICE_TEMPLATE" ]; then
  echo "Installing systemd service: $SERVICE_NAME"
  sudo cp "$SERVICE_TEMPLATE" "/etc/systemd/system/${SERVICE_NAME}.service"
fi

echo "Reloading and restarting systemd service"
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
sudo systemctl restart "$SERVICE_NAME"
sudo systemctl --no-pager --lines=20 status "$SERVICE_NAME"

