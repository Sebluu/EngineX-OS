#!/usr/bin/env python3
"""Instantiate optional panels with Qt 5, without Engine or a device."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch
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

# Use the actual generated startup bridge with a real Controls Drawer. A large
# z on a child of the main view cannot place it above the window's popup overlay.
import output_dsp_ui
with tempfile.TemporaryDirectory() as directory:
    base = Path(directory)
    for mid, title, section, eq, sub in builder.MODS:
        panel = base / mid / 'Panel.qml'
        panel.parent.mkdir()
        panel.write_bytes(builder.files(mid, title, section, eq, sub)['Panel.qml'])
    for section in ('eq', 'sub'):
        source = '''import QtQuick 2.12
import QtQuick.Controls 2.12
ApplicationWindow {
    id: root
    width: 1280; height: 800; visible: true
    property string scBoard: "JC11"
    Item { id: uiContainer; anchors.fill: parent }
    Drawer { id: settings; width: 900; height: root.height; modal: true }
    Timer {
        interval: 100; running: true
        onTriggered: { settings.open(); root.odMods=3; root.odOpen("@TEST_SECTION@") }
    }
    Connections {
        target: odModPanel
        onLoaded: finish.start()
    }
    Timer {
        id: finish; interval: 450
        onTriggered: {
            var overlay=root.Overlay.overlay
            console.warn("DSP_STACK|drawer=" + settings.position + "|overlayParent=" + (odModPanel.parent === overlay) + "|item=" + !!odModPanel.item + "|visible=" + (odModPanel.item ? odModPanel.item.visible : false) + "|size=" + odModPanel.width + "x" + odModPanel.height + "|")
            if(settings.position < .99 || odModPanel.parent !== overlay || !odModPanel.item || !odModPanel.item.visible){Qt.exit(3);return}
            var point=odModPanel.item.mapToItem(overlay,odModPanel.item.width/2,odModPanel.item.height/2)
            console.warn("DSP_TOP|same=" + (overlay.childAt(point.x,point.y) === odModPanel) + "|child=" + overlay.childAt(point.x,point.y) + "|loader=" + odModPanel + "|")
            if(overlay.childAt(point.x,point.y) !== odModPanel){Qt.exit(4);return}
            odModPanel.item.closed()
            if(odModPanel.active){Qt.exit(5);return}
            console.warn("DSP_SETTINGS_OVERLAY_PASSED=@TEST_SECTION@")
            Qt.quit()
        }
    }
    Timer { interval: 5000; running: true; onTriggered: Qt.exit(2) }
}
'''.replace('@TEST_SECTION@', section)
        pack = {'Skin/EmbeddedMain.qml': source,
                'Skin/MixerTabContent.qml': 'Item { property var entries: [EntryBase.ListEntry { text: "Fader Echo" }] }'}
        with patch.object(output_dsp_ui, 'feature', return_value=True):
            output_dsp_ui.add_output_dsp(pack, base, 'Skin/')
        source = pack['Skin/EmbeddedMain.qml']
        old_url='file:///data/enginex/ui/active/EngineXMods/'
        polling='running: root.scBoard === "JC11"; triggeredOnStart: true'
        assert source.count(old_url) == 1 and source.count(polling) == 1
        source=source.replace(old_url,base.as_uri()+'/').replace(polling,'running: false; triggeredOnStart: false')
        (base / 'Settings.qml').write_text(source)
        env = dict(os.environ, QT_QPA_PLATFORM='offscreen', QT_QUICK_BACKEND='software', QT_SELECT='qt5')
        if section == 'eq':
            old_source = source.replace('        parent: Overlay.overlay ? Overlay.overlay : uiContainer\n', '')
            assert old_source != source
            (base / 'Settings-old.qml').write_text(old_source)
            old_result = subprocess.run(['qmlscene', str(base / 'Settings-old.qml')], env=env, capture_output=True, text=True, timeout=15)
            if old_result.returncode != 3:
                print(old_result.stdout, old_result.stderr)
                raise SystemExit('Settings regression did not reject the old loader parent')
            print('PASS old Settings loader fails the popup-overlay check')
        result = subprocess.run(['qmlscene', str(base / 'Settings.qml')], env=env, capture_output=True, text=True, timeout=15)
        print(section, "exit="+str(result.returncode), result.stdout, result.stderr)
        if result.returncode or 'DSP_SETTINGS_OVERLAY_PASSED='+section not in result.stderr or any(word in result.stderr for word in ['ReferenceError', 'TypeError', 'is not a type', 'Cannot assign']):
            raise SystemExit('Settings overlay regression test failed')
