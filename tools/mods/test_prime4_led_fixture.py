#!/usr/bin/env python3
"""Exercise actual transformed LED bindings with Qt 5 and synthetic deck states."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import build_prime4_led_mod as led

def run(rootfs, qrc):
    with tempfile.TemporaryDirectory() as work:
        base = Path(work)
        a = led.build(rootfs, qrc, base / "one")
        b = led.build(rootfs, qrc, base / "two")
        assert a.read_bytes() == b.read_bytes(), "non-reproducible LED archive"
        with tarfile.open(a) as archive:
            manifest = json.load(archive.extractfile("mod.json"))
            assert "script" not in manifest
            patched = {name: archive.extractfile(name).read().decode() for name in led.HASHES}
        play_start, play_end = led.binding_span(patched["PlayCue.qml"], led.PLAY_MARKER)
        fx_start, fx_end = led.binding_span(patched["DJFxActivate.qml"], led.FX_MARKER)
        play = patched["PlayCue.qml"][play_start:play_end]
        fx = patched["DJFxActivate.qml"][fx_start:fx_end]
        assert "enabled: !deckConfig.inComputerMode" in patched["PlayCue.qml"]
        deck = dict(inLineInMode=False, inBluetoothMode=False, downloading=False,
                    playAfterDownload=False, playing=False, playlistDeckPlaying=False,
                    songLoaded=True, cueLEDState=True, cueLEDFlashing=False,
                    tempoSyncedFlashState=False, inComputerMode=False)
        cases = []
        def add(name, changes, expected, board=led.SCOPE, active=True, bluetooth=False):
            for phase in (False, True):
                d = copy.deepcopy(deck); d.update(changes); d["tempoSyncedFlashState"] = phase
                play_value = expected if isinstance(expected, int) else expected(phase)
                fx_value = (127 if active else 1) if board == led.SCOPE else (127 if active and phase else 1)
                cases.append(dict(name=name + "/" + str(phase), deck=d,
                                  assignment={"objectName": board},
                                  globalState={"bluetooth": {"play": bluetooth}, "flashStateFast": phase},
                                  active=active, play=play_value, fx=fx_value,
                                  enabled=not d["inComputerMode"]))
        add("playing", {"playing": True}, 127)
        add("paused", {}, 0)
        add("track-end", {"playing": False}, 0, active=False)
        add("empty", {"songLoaded": False}, 0)
        add("download-pending", {"songLoaded": False, "downloading": True, "playAfterDownload": True}, 0)
        add("playlist", {"songLoaded": False, "playlistDeckPlaying": True}, 127)
        add("bluetooth-playing", {"inBluetoothMode": True}, 127, bluetooth=True)
        add("bluetooth-paused", {"inBluetoothMode": True}, 0)
        add("line-input", {"inLineInMode": True, "playing": True}, 0)
        add("computer-mode", {"inComputerMode": True, "playing": True}, 127)
        add("other-board-paused", {}, lambda phase: 127 if phase else 0, board="PRIME 2 Controller Assignment")
        add("other-board-empty", {"songLoaded": False}, 1, board="PRIME 4+ Controller Assignment")
        qml = '''import QtQuick 2.12
Item {
    id: module
    width: 800; height: 480
    property var assignment: ({objectName: ""})
    property var deckConfig: ({})
    property var globalConfig: ({bluetooth: {play: false}, flashStateFast: false})
    property var fxLEDsItem: ({inDJMode: true, mixerChannel: {active: false}})
    property var fxConfig: ({fxEnabled: true})
    property bool flashOnActive: true
    readonly property bool fxOn: fxLEDsItem.mixerChannel.active
@GUARD@
    readonly property bool nativePlayLEDEnabled: !deckConfig.inComputerMode
    readonly property int playValue: { @PLAY@ }
    readonly property int fxValue: { @FX@ }
    property var cases: @CASES@
    property int caseIndex: 0
    function step() {
        if(caseIndex === cases.length) {console.log("LED_QT_CASES_PASSED=" + cases.length);Qt.quit();return}
        var row=cases[caseIndex]
        assignment=row.assignment;deckConfig=row.deck;globalConfig=row.globalState
        fxLEDsItem={inDJMode:true,mixerChannel:{active:row.active}}
        Qt.callLater(function(){
            if(playValue!==row.play || fxValue!==row.fx || nativePlayLEDEnabled!==row.enabled) {
                console.error("LED CASE FAILED",row.name,playValue,row.play,fxValue,row.fx,nativePlayLEDEnabled,row.enabled)
                Qt.exit(3);return
            }
            caseIndex++;next.restart()
        })
    }
    Component.onCompleted: next.start()
    Timer {id:next;interval:5;onTriggered:module.step()}
    Timer {interval:8000;running:true;onTriggered:Qt.exit(4)}
}
'''
        qml = qml.replace("@GUARD@", led.GUARD).replace("@PLAY@", play).replace("@FX@", fx).replace("@CASES@", json.dumps(cases))
        target = base / "LEDStates.qml"; target.write_text(qml)
        env = dict(os.environ, QT_SELECT="qt5", QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software")
        result = subprocess.run(["qmlscene", str(target)], env=env, capture_output=True, text=True, timeout=15)
        print(result.stdout, result.stderr)
        if result.returncode or "LED_QT_CASES_PASSED=" not in result.stderr + result.stdout:
            raise SystemExit("LED Qt state matrix failed")
        if any(word in result.stderr for word in ("ReferenceError", "TypeError", "is not a type")):
            raise SystemExit("invalid LED QML binding")
        print("LED_FIXTURE_ARCHIVE=" + str(a))
        return a.read_bytes()

if __name__ == "__main__":
    data = run(Path(sys.argv[1]), Path(sys.argv[2]))
    if len(sys.argv) > 3:
        Path(sys.argv[3]).write_bytes(data)
