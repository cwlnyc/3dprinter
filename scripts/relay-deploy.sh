#!/usr/bin/env bash
# Put the connector's permanent front door online at <name>.pages.dev, using
# your own Cloudflare account. Run it once, on the Mac, from the 3dprinter folder:
#
#   ./scripts/relay-deploy.sh
#
# It needs Node (for npx wrangler) and asks you to log in to Cloudflare in the
# browser if you aren't already. Running it again is safe: it reuses what exists.
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT=$(pwd)
CONFIG="$ROOT/workspace/connector.json"

# Make the connector's secret (and the site's name) if this is the first time.
python3 -c "import sys; sys.path.insert(0, '.'); from hwplot.connector import secret; secret('workspace')"
SECRET=$(python3 -c "import json; print(json.load(open('$CONFIG'))['secret'])")
NAME=$(python3 -c "import json; print(json.load(open('$CONFIG'))['relay_project'])")
WR="npx --yes wrangler@4"

cd "$ROOT/relay"
$WR whoami >/dev/null 2>&1 || $WR login

# A small key-value store for "where the Mac is right now".
KV_ID=$($WR kv namespace list | python3 -c "
import json, sys
for ns in json.load(sys.stdin):
    if ns['title'] == '$NAME':
        print(ns['id'])")
if [ -z "$KV_ID" ]; then
  $WR kv namespace create "$NAME" >/dev/null
  KV_ID=$($WR kv namespace list | python3 -c "
import json, sys
print(next(ns['id'] for ns in json.load(sys.stdin) if ns['title'] == '$NAME'))")
fi

cat > wrangler.toml <<TOML
name = "$NAME"
pages_build_output_dir = "public"
compatibility_date = "2025-06-01"

[[kv_namespaces]]
binding = "HWPLOT"
id = "$KV_ID"
TOML

# Pages serves <name>.pages.dev only from the production branch: create the
# project with one and always deploy to it.
$WR pages project create "$NAME" --production-branch main >/dev/null 2>&1 || true
printf '%s' "$SECRET" | $WR pages secret put HWPLOT_SECRET --project-name "$NAME" >/dev/null
$WR pages deploy --project-name "$NAME" --branch main

URL="https://$NAME.pages.dev"
python3 - "$CONFIG" "$URL" <<'PY'
import json, sys
path, url = sys.argv[1], sys.argv[2]
data = json.load(open(path)); data["relay"] = url
json.dump(data, open(path, "w"), indent=2)
PY
echo
echo "Front door is up at $URL."
echo "Now start the connector:  python3 -m hwplot mcp"
