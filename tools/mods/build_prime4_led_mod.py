#!/usr/bin/env python3
"""Build an experimental QML-only JC11 LED Mod from verified official fixtures."""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import tarfile

PREFIX = "ControlSurfaceModules/ControlSurfaceModules/"
CONTROLLER = "usr/Engine/AssignmentFiles/PresetAssignmentFiles/JC11/JC11_Controller_Assignments.qml"
CONTROLLER_SHA256 = "e6d61ec266798abc62352a62dc48df30d63a348c0a91a07500389df26426840b"
SCOPE = "PRIME 4 Controller Assignment"
HASHES = {
    "PlayCue.qml": "1e0739b6528ed22673da49e66235141292362d521220479fa2b8954097161952",
    "DJFxActivate.qml": "9044981ebc82c6e52772ea1b75e654d0c4415eda377441c27f769d4bd784b4da",
    "SweepFxSelect.qml": "e5f0b8779be8a681e9bca6b5cc2c8de50e089d2e1441290da650fbbf1da11b03",
}
GUARD = '    readonly property bool scPrime4SteadyLEDs: typeof assignment !== "undefined" && assignment !== null && assignment.objectName === "PRIME 4 Controller Assignment"\n'
PLAY_MARKER = 'objectName: "Play LED Deck%1".arg(deckConfig.name)'
SWEEP_MARKER = "id: sweepFxSelectLED"
FX_MARKER = 'objectName: "FX Enable LED %1".arg(nameSuffix).trim()'

def verify(raw, digest, label):
    if hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError(label + ": unsupported source hash; no package written")

def binding_span(text, marker):
    start = text.index("readonly property int ledValue:", text.index(marker))
    opening = text.index("{", start)
    depth = 1
    for i in range(opening + 1, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if not depth:
                return opening + 1, i
    raise ValueError("unbalanced LED binding")

def transform(name, raw):
    verify(raw, HASHES[name], name)
    text = raw.decode("utf-8")
    if text.count("    id: module\n") != 1 or "scPrime4SteadyLEDs" in text:
        raise ValueError("module structure changed")
    text = text.replace("    id: module\n", "    id: module\n" + GUARD, 1)
    if name == "PlayCue.qml":
        if text.count(PLAY_MARKER) != 1 or "enabled: !deckConfig.inComputerMode" not in text:
            raise ValueError("Play LED anchor changed")
        at, _ = binding_span(text, PLAY_MARKER)
        override = '''
                if (module.scPrime4SteadyLEDs) {
                    if (deckConfig.inLineInMode) return 0
                    if (deckConfig.inBluetoothMode) return globalConfig.bluetooth.play ? 127 : 0
                    return ((deckConfig.songLoaded && deckConfig.playing) || deckConfig.playlistDeckPlaying) ? 127 : 0
                }
'''
        text = text[:at] + override + text[at:]
    elif name == "DJFxActivate.qml":
        before = "fxOn && (!module.flashOnActive || globalConfig.flashStateFast)"
        if text.count(before) != 1:
            raise ValueError("FX LED anchor changed")
        text = text.replace(before, "fxOn && (module.scPrime4SteadyLEDs || !module.flashOnActive || globalConfig.flashStateFast)", 1)
    elif name == "SweepFxSelect.qml":
        start, end = binding_span(text, SWEEP_MARKER)
        body = text[start:end]
        if body.count("if (flashOnActive)") != 1:
            raise ValueError("Sweep FX LED anchor changed")
        body = body.replace("if (flashOnActive)", "if (flashOnActive && !module.scPrime4SteadyLEDs)", 1)
        text = text[:start] + body + text[end:]
    else:
        raise ValueError("unknown LED module")
    return text.encode("utf-8")

def validate_scope(rootfs):
    path = rootfs / CONTROLLER
    verify(path.read_bytes(), CONTROLLER_SHA256, "JC11 controller")
    matches = []
    base = rootfs / "usr/Engine/AssignmentFiles/PresetAssignmentFiles"
    for candidate in base.rglob("*Controller_Assignments.qml"):
        if candidate.is_symlink():
            continue
        first = re.search(r'objectName:\s*"([^"]+)"', candidate.read_text(encoding="utf-8"))
        if first and first.group(1) == SCOPE:
            matches.append(candidate.relative_to(rootfs).as_posix())
    if matches != [CONTROLLER]:
        raise ValueError("controller scope is not uniquely JC11")

def build(rootfs, qrc, destination):
    validate_scope(rootfs)
    data = {name: transform(name, (qrc / PREFIX / name).read_bytes()) for name in HASHES}
    manifest = dict(
        id="prime4-steady-leds", name="PRIME 4 Steady LEDs", version="0.1.0",
        author="Sebluu", category="interface",
        homepage="https://github.com/Sebluu/EngineX-OS",
        description="Experimental original PRIME 4 / JC11, Engine OS 5.3.0 only. Steady DJ-FX and Sweep-FX LEDs; PLAY off while paused, ended or empty. Engine UI restart required after enable/disable.",
        qmlFiles={name: PREFIX + name for name in HASHES},
    )
    data["mod.json"] = (json.dumps(manifest, indent=2) + "\n").encode()
    data["provenance.json"] = (json.dumps({"controller": CONTROLLER_SHA256, "modules": HASHES}, indent=2) + "\n").encode()
    data["README.md"] = (Path(__file__).resolve().parents[2] / "docs/mods/src/prime4-steady-leds/README.md").read_bytes()
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / "prime4-steady-leds-0.1.0.tar.gz"
    with target.open("wb") as raw, gzip.GzipFile(fileobj=raw, filename="", mode="wb", mtime=0) as gz:
        with tarfile.open(fileobj=gz, mode="w") as archive:
            for name, raw in sorted(data.items()):
                entry = tarfile.TarInfo(name)
                entry.size = len(raw)
                entry.mode = 0o644
                archive.addfile(entry, io.BytesIO(raw))
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    target.with_suffix(target.suffix + ".sha256").write_text(digest + "  " + target.name + "\n")
    return target

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rootfs", type=Path, required=True)
    parser.add_argument("--qrc", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    print(build(args.rootfs, args.qrc, args.out))
