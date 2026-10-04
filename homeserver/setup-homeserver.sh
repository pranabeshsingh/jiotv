#!/usr/bin/env bash
set -euo pipefail

# This script sets up the JioTV residential proxy service on homeserver.
# It runs as a systemd user service and ensures lingering is enabled so it survives reboots.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "==> Creating bin and systemd user directories..."
mkdir -p "$HOME/bin" "$HOME/.config/systemd/user"

echo "==> Installing proxy script..."
cp "$SCRIPT_DIR/jio_proxy.py" "$HOME/bin/jio_proxy.py"
chmod +x "$HOME/bin/jio_proxy.py"

echo "==> Installing systemd service..."
cp "$SCRIPT_DIR/jiotv-proxy.service" "$HOME/.config/systemd/user/jiotv-proxy.service"

echo "==> Enabling user linger (service runs even when logged out)..."
loginctl enable-linger "$USER" || true

echo "==> Reloading and enabling service..."
systemctl --user daemon-reload
systemctl --user enable --now jiotv-proxy.service

echo "==> Proxy service status:"
systemctl --user status jiotv-proxy.service --no-pager
