#!/usr/bin/env python3
"""Instantiate optional panels with Qt 5, without Engine or a device."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'mods'))
import build_output_dsp_mods as builder

with tempfile.TemporaryDirectory() as directory:
    base = Path(directory)
    for mid, title, section, eq, sub in builder.MODS:
        (base / 'Panel.qml').write_bytes(builder.files(mid, title, section, eq, sub)['Panel.qml'])
        (base / 'Smoke.qml').write_text('''import QtQuick 2.12
import QtQuick.Window 2.12
Window {
    width: 1024; height: 600; visible: true
    Loader { anchors.fill: parent; source: "Panel.qml"
        onStatusChanged: if(status === Loader.Error)Qt.exit(1)
        onLoaded: finish.start()
    }
    Timer { id: finish; interval: 200; onTriggered: Qt.quit() }
    Timer { interval: 5000; running: true; onTriggered: Qt.exit(2) }
}
''')
        env = dict(os.environ, QT_QPA_PLATFORM='offscreen', QT_QUICK_BACKEND='software', QT_SELECT='qt5')
        result = subprocess.run(['qmlscene', str(base / 'Smoke.qml')], env=env, capture_output=True, text=True, timeout=15)
        print(mid, result.stdout, result.stderr)
        if result.returncode or any(word in result.stderr for word in ['ReferenceError', 'TypeError', 'is not a type', 'Cannot assign']):
            raise SystemExit('QML smoke test failed')
