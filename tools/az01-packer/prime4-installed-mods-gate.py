#!/usr/bin/env python3
"""Add installed-Mod assertions to a private copy of the upstream release gate.

The original assertions stay byte-for-byte intact. No firmware or deck is opened
here; execution is a separate, disposable GitHub runner job.
"""
from pathlib import Path
import os

def instrument(source):
    anchor = '    if [ "$name" = new ]; then\n        local log=$W/new-engine.log files label\n'
    if source.count(anchor) != 1:
        raise ValueError("release gate fixture anchor changed")
    extra = '''    if [ "$name" != old ]; then
        check "$name: installed Mods, exact active overlays and DSP profiles persist" \\
            "$GATE_MODS_CHECKER" verify "$D/ui"
        curl -sf "http://127.0.0.1:8080$N_API/output-dsp" > "$W/$name-output-dsp.json" || :
        check "$name: real loopback DSP gateway preserves four enabled profiles" \\
            json "$W/$name-output-dsp.json" "j.get('version') == 1 and len(j.get('profiles', [])) == 4 and all(p[0] == 1 and p[2] == 1 and p[13] == -1 for p in j['profiles']) and j.get('enabled', 0) == (j.get('available', 0) & 3)"
    fi
'''
    return source.replace(anchor, extra + anchor)

def main():
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise SystemExit("disposable runner only")
    repo = Path(__file__).resolve().parents[2]
    path = repo / "tools/az01-packer/release-gate.sh"
    output = path.with_name(".prime4-installed-mods-gate.sh")
    if output.exists():
        raise SystemExit("refusing to replace an existing test gate")
    output.write_text(instrument(path.read_text()))
    output.chmod(0o755)
    print(output)

if __name__ == "__main__":
    main()
