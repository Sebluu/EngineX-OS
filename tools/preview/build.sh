#!/bin/bash
# Build only in the preview VM or disposable CI runner.
set -euo pipefail
repo=$(cd "$(dirname "$0")/../.." && pwd)
work=$(realpath "${1:?private preview work directory}")
sdk=$work/qt-sdk/usr/include/arm-linux-gnueabihf/qt6
cd "$repo"
mkdir -p "$work/bin"
if [ "${GITHUB_ACTIONS:-}" != true ]; then
    grep -Eqi 'QEMU|Standard PC' /sys/class/dmi/id/product_name || exit 2
fi
/usr/lib/qt6/libexec/moc -I"$sdk" -I"$sdk/QtCore" -I"$sdk/QtGui" tools/preview/bridge.cpp -o "$work/bridge.moc"
arm-linux-gnueabihf-g++ -std=c++17 -O2 -Wall -Wextra -Werror -shared -fPIC -pthread -I"$work" \
    -I"$sdk" -I"$sdk/QtCore" -I"$sdk/QtGui" -I"$sdk/QtQuick" -I"$sdk/QtQml" \
    -o "$work/bridge.so" tools/preview/bridge.cpp -L"$work/qt-sdk/usr/lib/arm-linux-gnueabihf" -l:libQt6Test.so.6
GOOS=linux GOARCH=arm GOARM=7 CGO_ENABLED=0 go build -trimpath -o "$work/backend" tools/preview/backend.go
arm-linux-gnueabihf-gcc -O2 -shared -fPIC tools/ui-mod/qrc_dump.c -ldl -o "$work/qrc-dump.so"
if [ ! -d "$work/qrc" ]; then
    # Read vendor resources from the unmodified, hash-pinned stock tree.
    # The published EngineX tree has its own first-boot preparation contract.
    python3 -I tools/ui-mod/extract_qrc.py --tree "$work/stock-root" --preload "$work/qrc-dump.so" --out "$work/qrc"
fi
python3 tools/ui-mod/build_packs.py --qrc "$work/qrc" --out "$work/packs"
# No firmware is repacked: these UI assets belong only to this VM's copied root.
gzip -dc "$work/packs.tar.gz" | xz -1 --check=crc32 -c > "$work/root/usr/share/enginex/ui-packs.tar.xz"
python3 tools/mods/build_output_dsp_mods.py --out "$work/runtime/mods"
python3 tools/mods/build_prime4_led_mod.py --rootfs "$work/root" --qrc "$work/qrc" --out "$work/runtime/mods"
if [ -f "$repo/.preview-source-sha" ]; then
    commit=$(cat "$repo/.preview-source-sha")
else
    commit=$(git rev-parse HEAD)
fi
printf '%s' "$commit" | python3 -c 'import json,sys; print(json.dumps({"sourceCommit":sys.stdin.read().strip()}))' > "$work/runtime/build.json"
