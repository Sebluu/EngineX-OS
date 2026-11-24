#!/bin/bash
# Fail fast on an upstream assertion failure, never turn it into a passing gate.
set -euo pipefail
[ "${GITHUB_ACTIONS:-}" = true ] && [ "$(id -u)" = 0 ] && [ -n "${RUNNER_TEMP:-}" ] && [ "$#" = 5 ] || exit 2
script=$(realpath "$1")
[ "${script##*/}" = .prime4-installed-mods-gate.sh ] && [ -f "$script" ] || exit 2
for path in "$2" "$3" "$5"; do
    case $(realpath -m "$path") in "$RUNNER_TEMP"/*) ;; *) echo 'Runner fixtures only' >&2; exit 2 ;; esac
done
work=$5
shift
setsid bash "$script" "$@" &
gate_pid=$!
cleanup() {
    kill -TERM -- "-$gate_pid" 2>/dev/null || :
    for attempt in 1 2 3 4 5; do
        kill -0 "$gate_pid" 2>/dev/null || break
        sleep .2
    done
    kill -KILL -- "-$gate_pid" 2>/dev/null || :
    wait "$gate_pid" 2>/dev/null || :
}
trap cleanup EXIT
while kill -0 "$gate_pid" 2>/dev/null; do
    if grep -qs '^FAIL ' "$work/results.txt"; then
        echo 'Upstream assertion failed: aborting this candidate, not approving installation.' >&2
        exit 1
    fi
    sleep 2
done
set +e
wait "$gate_pid"
rc=$?
set -e
trap - EXIT
exit "$rc"
