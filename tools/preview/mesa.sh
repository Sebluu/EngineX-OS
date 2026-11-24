#!/bin/bash
# Download ARM Mesa only into disposable preview storage, never onto a deck.
set -euo pipefail
work=$(realpath "${1:?private preview work directory}")
if [ "${GITHUB_ACTIONS:-}" != true ]; then
    grep -Eqi 'QEMU|Standard PC' /sys/class/dmi/id/product_name || exit 2
fi
mesa=$work/mesa
if [ ! -f "$mesa/ready" ]; then
    mkdir -p "$mesa/debs/partial" "$mesa/root"
    # An empty dpkg status obtains the complete ARM runtime without installing
    # foreign packages into Ubuntu. APT verifies the signed archive checksums.
    apt-get -o Dir::State::status=/dev/null -o Dir::Cache::archives="$mesa/debs" \
        -o Debug::NoLocking=true --download-only --assume-yes --no-install-recommends \
        install libegl-mesa0:armhf libegl1:armhf libgles2:armhf libgl1-mesa-dri:armhf
    (cd "$mesa/debs" && apt-get download libegl-dev:armhf libgl-dev:armhf)
    for archive in "$mesa/debs/"*.deb; do dpkg-deb -x "$archive" "$mesa/root"; done
    touch "$mesa/ready"
fi
prefix=/opt/enginex-preview-mesa
mkdir -p "$work/root$prefix"
cp -a "$mesa/root/." "$work/root$prefix/"
library_path="$prefix/usr/lib/arm-linux-gnueabihf:$prefix/lib/arm-linux-gnueabihf"
# dlopen from a vendor Qt plugin does not inherit the executable's path for
# every transitive Mesa/LLVM dependency. Keep that whole runtime self-contained.
while IFS= read -r -d '' library; do
    case "$library" in */ld-linux-armhf.so.3|*/libc.so.6) continue ;; esac
    patchelf --force-rpath --set-rpath "$library_path:\$ORIGIN" "$library"
done < <(find "$work/root$prefix" -type f -path '*/lib/*' -name '*.so*' -print0)
loader=$(find "$mesa/root" -type f -name ld-linux-armhf.so.3 -print -quit)
[ -n "$loader" ] || { echo 'Preview Mesa ARM loader missing' >&2; exit 1; }
# Only this private Engine copy gets the matching loader and transitive runtime
# search path. Its subprocesses retain their original vendor loader/libraries.
patchelf --set-interpreter "$prefix${loader#"$mesa/root"}" \
    --force-rpath --set-rpath "$library_path:/usr/qt/lib:/usr/lib:/lib" \
    "$work/root/usr/Engine/Engine"
