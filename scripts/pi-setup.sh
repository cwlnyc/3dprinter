#!/usr/bin/env bash
# Run ON the Raspberry Pi (pi-push.sh does that for you). Installs everything
# and makes the connector start by itself whenever the Pi powers on.
# Needs 64-bit Raspberry Pi OS (Lite is fine): the image libraries only come
# ready-built for 64-bit, and building them on a Pi 3 takes hours.
set -euo pipefail
cd "$(dirname "$0")/.."
DIR=$(pwd)

if [ "$(uname -m)" != "aarch64" ]; then
  echo "This Pi is running 32-bit Raspberry Pi OS. Reflash it with the 64-bit version (Raspberry Pi Imager:"
  echo "'Raspberry Pi OS Lite (64-bit)') and run this again."
  exit 1
fi

sudo apt-get update -q
sudo apt-get install -y -q python3-venv python3-dev libglib2.0-0 curl

python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt

# The tunnel program, for Linux on ARM.
if [ ! -x "$HOME/cloudflared" ]; then
  curl -sSL -o "$HOME/cloudflared" https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64
  chmod +x "$HOME/cloudflared"
fi

# Talking to the printer over USB needs the 'dialout' group.
sudo usermod -aG dialout "$USER"

sudo tee /etc/systemd/system/hwplot.service >/dev/null <<UNIT
[Unit]
Description=Homework Plotter connector
After=network-online.target
Wants=network-online.target

[Service]
User=$USER
WorkingDirectory=$DIR
Environment=PYTHONUNBUFFERED=1
ExecStart=$DIR/.venv/bin/python -m hwplot mcp
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload
sudo systemctl enable hwplot.service
sudo systemctl restart hwplot.service  # picks up updated code on a re-run
sleep 20
echo
echo "Connector status (look for 'Connected'):"
journalctl -u hwplot.service -n 10 --no-pager | sed -E 's#/[A-Za-z0-9_-]{30,}/mcp#/<secret>/mcp#'
echo
echo "Done. It starts by itself whenever the Pi is on. Plug the printer into one of the Pi's USB ports."
