#!/bin/bash
set -euo pipefail
umask 022
grep -Eqi 'QEMU|Standard PC' /sys/class/dmi/id/product_name || exit 2
repo=$(cd "$(dirname "$0")/../.." && pwd)
work=/var/lib/enginex-preview/work
mkdir -p /run/enginex-preview "$work/data"
echo local-vm-only > /run/enginex-preview-vm
if [ ! -e "$work/runtime" ]; then ln -s /run/enginex-preview "$work/runtime"; fi
echo building > "$work/runtime/setup.state"
python3 - "$repo/.preview-source-sha" "$work/runtime/build.json" <<'META'
from pathlib import Path
import json,sys
Path(sys.argv[2]).write_text(json.dumps({'sourceCommit':Path(sys.argv[1]).read_text().strip()}))
META
python3 "$repo/tools/preview/server.py" --listen 0.0.0.0 --runtime "$work/runtime" --data "$work/data" --port 8765 --public-port "$(cat /etc/enginex-preview-port)" &
viewer=$!
trap 'kill -TERM "$viewer" 2>/dev/null || true' EXIT
export GOMAXPROCS=2
export ENGINEX_BUILD_TAG="desktop-preview $(head -c 8 "$repo/.preview-source-sha")"
cd "$repo"
if bash tools/preview/build.sh "$work"; then
    echo ready > "$work/runtime/setup.state"
    if ! bash tools/preview/sandbox.sh "$work" interactive; then
        echo failed > "$work/runtime/setup.state"
        echo 'Preview sandbox failed; the viewer remains available for diagnostics and shutdown.' >&2
    fi
else
    echo failed > "$work/runtime/setup.state"
    echo 'Preview build failed; the viewer remains available for diagnostics and shutdown.' >&2
fi
wait "$viewer"
