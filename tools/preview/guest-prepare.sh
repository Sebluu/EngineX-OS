#!/bin/bash
# This is invoked by cloud-init inside our local x86 VM, never on the laptop.
set -euo pipefail
grep -Eqi 'QEMU|Standard PC' /sys/class/dmi/id/product_name || exit 2
[ "$(id -u)" = 0 ] || exit 2
repo=$(cd "$(dirname "$0")/../.." && pwd)
mkdir -p /var/lib/enginex-preview/work /var/cache/enginex-preview
if ! grep -q '^Architectures:' /etc/apt/sources.list.d/ubuntu.sources; then
    sed -i '/^Types: deb/a Architectures: amd64' /etc/apt/sources.list.d/ubuntu.sources
fi
dpkg --add-architecture armhf
printf '%s\n' 'Types: deb' 'URIs: https://ports.ubuntu.com/ubuntu-ports' 'Suites: noble noble-updates noble-security' 'Components: main universe' 'Architectures: armhf' 'Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg' > /etc/apt/sources.list.d/preview-armhf.sources
apt-get -o Acquire::Retries=2 update
update-binfmts --enable qemu-arm
grep -q '^flags:.*F' /proc/sys/fs/binfmt_misc/qemu-arm
cd /var/lib/enginex-preview/work
mkdir -p qt-sdk
cd qt-sdk
apt-get download qt6-base-dev:armhf qt6-declarative-dev:armhf libqt6test6t64:armhf
for archive in *.deb; do dpkg-deb -x "$archive" .; done
cd /var/cache/enginex-preview
image=PRIME4-5.3.0.5-r1.img
if [ ! -f "$image" ]; then
    curl --fail --location --retry 2 'https://github.com/Cd1s/EngineX-OS/releases/download/v5.3.0.5-r1/PRIME4-5.3.0.5-EngineX-OS-Denon-PRIME-4-JC11-Update.img' -o "$image.download"
    echo 'a76b3eaefdb24dab01ec70f2316c0809a6b25d281fa6c03d751437463a1f25e6  PRIME4-5.3.0.5-r1.img.download' | sha256sum -c -
    mv "$image.download" "$image"
fi
echo 'a76b3eaefdb24dab01ec70f2316c0809a6b25d281fa6c03d751437463a1f25e6  PRIME4-5.3.0.5-r1.img' | sha256sum -c -
work=/var/lib/enginex-preview/work
if [ ! -d "$work/root" ]; then
    python3 -I "$repo/tools/az01-packer/az01_packer.py" unpack "$PWD/$image" --output "$work/parts"
    mkdir "$work/root"
    debugfs -R "rdump / $work/root" "$work/parts/rootfs.ext2" 2>"$work/debugfs.log"
fi
stock=PRIME4-5.3.0-stock.img
if [ ! -f "$stock" ]; then
    curl --fail --location --retry 2 'https://public.inmusiccdn.com/Engine/5.3.0/RELEASE/d41cd81e67f225bf/PRIME4-5.3.0-Update.img' -o "$stock.download"
    echo '8e49313be0ef338d5452631c5772ee5b1d72e076cae65bf69a6df8b5b210029f  PRIME4-5.3.0-stock.img.download' | sha256sum -c -
    mv "$stock.download" "$stock"
fi
echo '8e49313be0ef338d5452631c5772ee5b1d72e076cae65bf69a6df8b5b210029f  PRIME4-5.3.0-stock.img' | sha256sum -c -
if [ ! -d "$work/stock-root" ]; then
    python3 -I "$repo/tools/az01-packer/az01_packer.py" unpack "$PWD/$stock" --output "$work/stock-parts"
    mkdir "$work/stock-root"
    debugfs -R "rdump / $work/stock-root" "$work/stock-parts/rootfs.ext2" 2>"$work/stock-debugfs.log"
fi
