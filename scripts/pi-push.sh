#!/usr/bin/env bash
# Run on the Mac, from the 3dprinter folder:  ./scripts/pi-push.sh <pi-user>@<pi-name>.local
# Copies this project to the Pi, including workspace/ (your handwriting, printer
# settings and the connector's secret), then runs the Pi's setup.
# Run it again whenever you've changed things on the Mac (relearned handwriting,
# recalibrated, pulled an update); it only copies what changed.
set -euo pipefail
cd "$(dirname "$0")/.."
TARGET=${1:?usage: ./scripts/pi-push.sh user@hostname.local   (e.g. pi@hwplot.local)}

# Stop the Mac's connector first if it's running: two connectors would fight
# over who the front door points at.
# Photos sent to the Pi from chat, and its own output, stay put.
rsync -az --delete --exclude .venv --exclude __pycache__ --exclude .pytest_cache --exclude relay/.wrangler \
  --exclude workspace/photos --exclude workspace/out \
  ./ "$TARGET:3dprinter/"
ssh -t "$TARGET" 'bash 3dprinter/scripts/pi-setup.sh'
