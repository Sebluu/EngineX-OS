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
    panel_checks = '''        check "$name: Output Equalizer instantiates in Engine's own Qt" grep -aqF 'SCPROBE dsp-panel|output-equalizer|ready|' "$W/$name-engine.log"
        check "$name: Subharmonic Synthesizer instantiates in Engine's own Qt" grep -aqF 'SCPROBE dsp-panel|subharmonic-synth|ready|' "$W/$name-engine.log"
'''
    if extra.count("    fi\n") != 1:
        raise ValueError("installed-Mod assertion anchor changed")
    extra = extra.replace("    fi\n", panel_checks + "    fi\n")
    original_probe = '$REPO/tools/az01-packer/gate-ui-probe.qml'
    private_probe = '$REPO/tools/az01-packer/.prime4-native-ui-probe.qml'
    if source.count(original_probe) != 1:
        raise ValueError("release gate UI probe anchor changed")
    return source.replace(anchor, extra + anchor).replace(original_probe, private_probe)

def main():
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise SystemExit("disposable runner only")
    repo = Path(__file__).resolve().parents[2]
    path = repo / "tools/az01-packer/release-gate.sh"
    output = path.with_name(".prime4-installed-mods-gate.sh")
    if output.exists():
        raise SystemExit("refusing to replace an existing test gate")
    probe_source = path.with_name("gate-ui-probe.qml").read_text()
    probe_anchor = "    function report() {\n"
    if probe_source.count(probe_anchor) != 1:
        raise SystemExit("native UI probe anchor changed")
    panel_probe = '''    function reportDSPPanels() {
        for (const id of ["output-equalizer", "subharmonic-synth"]) {
            const component = Qt.createComponent("file:///data/enginex/ui/mods-overlay/EngineXMods/" + id + "/Panel.qml")
            if (component.status !== Component.Ready) {
                console.warn("SCPROBE error|DSP panel " + id + ": " + component.errorString() + "|")
                continue
            }
            const panel = component.createObject(probe, {visible: false, width: 1280, height: 800})
            if (!panel) console.warn("SCPROBE error|DSP panel creation " + id + ": " + component.errorString() + "|")
            else console.warn("SCPROBE dsp-panel|" + id + "|ready|")
        }
    }
'''
    private_probe = path.with_name(".prime4-native-ui-probe.qml")
    if private_probe.exists():
        raise SystemExit("refusing to replace an existing private UI probe")
    private_probe.write_text(probe_source.replace(probe_anchor, panel_probe + probe_anchor + "        reportDSPPanels()\n"))
    output.write_text(instrument(path.read_text()))
    output.chmod(0o755)
    print(output)

if __name__ == "__main__":
    main()
