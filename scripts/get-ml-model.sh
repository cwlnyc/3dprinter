#!/usr/bin/env bash
# Download the trained handwriting model's weights (15 MB) into models/graves/,
# from a pinned commit of X-rayLaser/pytorch-handwriting-synthesis-toolkit
# (MIT licence), and refuse them unless they match the expected checksums.
# Only these two files are fetched; none of that project's code is run.
set -euo pipefail
cd "$(dirname "$0")/.."
COMMIT=899e9432dfe0998ba2ef31582d11c2d5f24a5185
BASE="https://raw.githubusercontent.com/X-rayLaser/pytorch-handwriting-synthesis-toolkit/$COMMIT/checkpoints/Epoch_56"
DEST=models/graves
mkdir -p "$DEST"
curl -fsSL "$BASE/model.pt" -o "$DEST/model.pt"
curl -fsSL "$BASE/meta.json" -o "$DEST/meta.json"
curl -fsSL "https://raw.githubusercontent.com/X-rayLaser/pytorch-handwriting-synthesis-toolkit/$COMMIT/LICENSE" -o "$DEST/LICENSE"
cat > "$DEST/SHA256SUMS" <<SUMS
e5eddd9f771ef1f0414909e61f173e88f293a35cb4c99cf359ac296552349e43  $DEST/model.pt
00c383051895af5a091743652597dc4a9c456c70d07ec7ca51a96fcad6e6f70c  $DEST/meta.json
SUMS
if command -v sha256sum >/dev/null; then sha256sum -c "$DEST/SHA256SUMS"; else shasum -a 256 -c "$DEST/SHA256SUMS"; fi
echo "Model ready in $DEST"
