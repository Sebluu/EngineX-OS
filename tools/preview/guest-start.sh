#!/bin/bash
set -euo pipefail
grep -Eqi 'QEMU|Standard PC' /sys/class/dmi/id/product_name || exit 2
repo=$(cd "$(dirname "$0")/../.." && pwd)
work=/var/lib/enginex-preview/work
mkdir -p /run/enginex-preview
echo local-vm-only > /run/enginex-preview-vm
if [ ! -e "$work/runtime" ]; then ln -s /run/enginex-preview "$work/runtime"; fi
export GOMAXPROCS=2
export ENGINEX_BUILD_TAG="desktop-preview $(head -c 8 "$repo/.preview-source-sha")"
cd "$repo"
bash tools/preview/build.sh "$work"
python3 tools/preview/server.py --listen 0.0.0.0 --runtime "$work/runtime" --data "$work/data" --port 8765 --public-port "$(cat /etc/enginex-preview-port)" &
viewer=$!
trap 'kill -TERM "$viewer" 2>/dev/null || true' EXIT
bash tools/preview/sandbox.sh "$work" interactive
