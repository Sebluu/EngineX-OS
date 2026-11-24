#!/bin/bash
# Run only inside the desktop VM or on a disposable CI runner. Never on a deck.
set -euo pipefail
script=$(realpath "$0")
repo=$(cd "$(dirname "$script")/../.." && pwd)
work=$(realpath "${1:?preview work directory}")
mode=${2:-interactive}
if [ "$mode" != --inner ]; then
    [ "$(id -u)" = 0 ] || { echo 'Run in the preview VM' >&2; exit 2; }
    if [ "${GITHUB_ACTIONS:-}" != true ]; then
        grep -Eqi 'QEMU|Standard PC' /sys/class/dmi/id/product_name || { echo 'Preview VM required' >&2; exit 2; }
    fi
    case "$work" in /|/data|/usr|/home|/dev|/sys|/proc) exit 2 ;; esac
    [ -f "$work/root/usr/Engine/Engine" ] && [ -f "$work/bridge.so" ] || exit 2
    [ "$mode" = smoke ] || [ "$mode" = interactive ] || exit 2
    export PREVIEW_WORK=$work PREVIEW_REPO=$repo PREVIEW_MODE=$mode
    exec setpriv --inh-caps=-sys_time --bounding-set=-sys_time unshare -m -n -p -f --kill-child bash "$script" "$work" --inner
fi
root=$work/root
mount --make-rprivate /
ip link set lo up
mkdir -p "$work/data" "$work/runtime"
mount --bind "$root" "$root"
for directory in tmp run dev sys proc; do mount -t tmpfs tmpfs "$root/$directory"; done
mount --bind "$work/data" "$root/data"
mkdir -p "$root/tmp/preview" "$root/dev/pts" "$root/dev/shm" "$root/run/dbus" "$root/tmp/home" \
    "$root/sys/firmware/devicetree/base" "$root/sys/devices/system/cpu"
mount --bind "$work/runtime" "$root/tmp/preview"
for device in null zero full random urandom; do
    touch "$root/dev/$device"; mount --bind "/dev/$device" "$root/dev/$device"
done
printf 'JC11\0' > "$root/sys/firmware/devicetree/base/inmusic,product-code"
printf 'inmusic,jc11\0rockchip,rk3288\0' > "$root/sys/firmware/devicetree/base/compatible"
for item in online possible present; do echo 0-3 > "$root/sys/devices/system/cpu/$item"; done
printf 'local-vm-only\n' > "$root/run/enginex-desktop-preview"
mkdir -p "$root/run/preview-shims"
cat > "$root/run/preview-shims/blocked" <<'SH'
#!/bin/sh
echo "PREVIEW_BLOCKED $0" >&2
exit 0
SH
chmod 755 "$root/run/preview-shims/blocked"
for command in /usr/bin/systemctl /sbin/reboot /usr/sbin/kexec /usr/sbin/az01-update /usr/Engine/Scripts/encrypt-fs.sh /usr/Engine/Reporter; do
    if [ -L "$root$command" ]; then
        rm "$root$command"; cp "$root/run/preview-shims/blocked" "$root$command"
    elif [ -f "$root$command" ]; then
        mount --bind "$root/run/preview-shims/blocked" "$root$command"
    fi
done
mkdir -p "$root/proc/sys/net/core" "$root/proc/sys/net/ipv4" "$root/proc/sys/vm" "$root/proc/sys/fs"
for setting in net/core/rmem_max net/core/wmem_max net/ipv4/tcp_rmem net/ipv4/tcp_wmem vm/swappiness fs/file-max; do
    echo 0 > "$root/proc/sys/$setting"
done
run() { chroot "$root" /usr/bin/env -i PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin "$@"; }
run /usr/libexec/enginex-etc-reset > "$work/prepare.log" 2>&1
run /usr/libexec/enginex-prepare >> "$work/prepare.log" 2>&1
if [ ! -f "$work/data/enginex/ui/settings.conf" ]; then echo lang=en > "$work/data/enginex/ui/settings.conf"; fi
umount "$root/proc"
mount -t proc proc "$root/proc"
printf '           CPU0\n 41:        100     GICv2  32 Level     ttyS0\n' > "$root/run/preview-shims/interrupts"
mount --bind "$root/run/preview-shims/interrupts" "$root/proc/interrupts"
mount -t tmpfs tmpfs "$root/proc/irq"
mkdir -p "$root/proc/irq/41"
echo f > "$root/proc/irq/41/smp_affinity"
echo 0-3 > "$root/proc/irq/41/smp_affinity_list"
mkdir -p "$root/tmp/preview/plugins/generic"
cp "$work/bridge.so" "$root/tmp/preview/plugins/generic/libenginexpreview.so"
if [ "$PREVIEW_MODE" = smoke ]; then
    cp "$PREVIEW_REPO/tools/preview/smoke-target.qml" "$root/tmp/preview/smoke-target.qml"
    for pack in "$work/data/enginex/ui/packs/"*; do
        [ -d "$pack" ] || continue
        probe="$pack/Skins/Common/Items/QmlWarnings.qml"
        mkdir -p "$(dirname "$probe")"
        cp "$PREVIEW_REPO/tools/preview/smoke-probe.qml" "$probe"
    done
fi
run /usr/bin/dbus-daemon --system --fork --nopidfile > "$work/dbus.log" 2>&1
if [ -f "$work/backend" ]; then
    cp "$work/backend" "$root/tmp/preview/backend"
    run /tmp/preview/backend > "$work/backend.log" 2>&1 &
else
    run /usr/local/bin/stream-sync --listen 127.0.0.1:8080 --deemixd= --relay-url= --disable-guard --state-dir /data/enginex/state > "$work/backend.log" 2>&1 &
fi
backend=$!
for attempt in $(seq 120); do
    curl -sf http://127.0.0.1:8080/v1/enginex/ui > /dev/null && break
    kill -0 "$backend" || { echo 'Preview backend failed' >&2; exit 1; }
    sleep .5
done
run /etc/enginex/engine-ui-guard pre >> "$work/prepare.log" 2>&1
start_engine() {
rm -f "$work/runtime/frame.json" "$work/runtime/frame.png" "$work/runtime/restart.request"
echo starting > "$work/runtime/engine.state"
chroot "$root" /usr/bin/env -i PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    HOME=/tmp/home LD_LIBRARY_PATH=/usr/qt/lib QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software \
    ENGINEX_DESKTOP_PREVIEW=1 MALLOC_ARENA_MAX=1 \
    ENGINEX_PREVIEW_SMOKE="$([ "$PREVIEW_MODE" = smoke ] && echo 1 || true)" \
    QT_DEBUG_PLUGINS="$([ "$PREVIEW_MODE" = smoke ] && echo 1 || echo 0)" \
    QT_PLUGIN_PATH=/tmp/preview/plugins:/usr/lib/plugins QT_QPA_GENERIC_PLUGINS=enginexpreview \
    LD_PRELOAD=/etc/enginex/libengine-ui-hook.so \
    /usr/Engine/Engine -d0 > "$work/engine.log" 2>&1 &
engine=$!
}
stop_engine() {
    [ -n "${engine:-}" ] || return 0
    kill -TERM "$engine" 2>/dev/null || true
    for attempt in $(seq 40); do kill -0 "$engine" 2>/dev/null || break; sleep .25; done
    kill -KILL "$engine" 2>/dev/null || true
    wait "$engine" 2>/dev/null || true
    engine=
    echo stopped > "$work/runtime/engine.state"
    run /etc/enginex/engine-ui-guard stop >> "$work/prepare.log" 2>&1 || true
}
start_engine
trap 'stop_engine; kill -TERM "$backend" 2>/dev/null || true' EXIT
trap 'exit 0' TERM INT
if [ "$PREVIEW_MODE" = smoke ]; then
    for attempt in $(seq 120); do
        if [ -s "$work/runtime/frame.json" ]; then break; fi
        kill -0 "$engine" || { tail -20 "$work/engine.log"; exit 1; }
        sleep .5
    done
    [ -s "$work/runtime/frame.json" ] || { tail -35 "$work/engine.log"; exit 1; }
    python3 "$PREVIEW_REPO/tools/preview/test_live_bridge.py" "$work/runtime" "$work/engine.log"
else
    while :; do
        if [ -e "$work/runtime/restart.request" ]; then
            stop_engine
            run /etc/enginex/engine-ui-guard pre >> "$work/prepare.log" 2>&1
            start_engine
        elif [ -n "$engine" ] && ! kill -0 "$engine" 2>/dev/null; then
            stop_engine
        fi
        sleep .25
    done
fi
