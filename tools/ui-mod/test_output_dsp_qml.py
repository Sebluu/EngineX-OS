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

# Exercise real pointer delivery above a modal Settings Drawer. childAt() in Qt 5
# does not sort by z, so a structural hit-test alone cannot verify this behavior.
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
    property int testClicks: 0
    property alias mainButton: mainButton
    property alias settingsButton: settingsButton
    property alias panelLoader: odModPanel
    property alias settingsDrawer: settings
    readonly property var overlayParent: root.Overlay.overlay
    Item { id: uiContainer; anchors.fill: parent
        Button { id: mainButton; x: 100; y: 50; width: 200; height: 100; text: "Main"; onClicked: root.testClicks++ }
    }
    Drawer { id: settings; width: 900; height: root.height; modal: true
        Button { id: settingsButton; x: 100; y: 50; width: 200; height: 100; text: "Settings"; onClicked: root.testClicks++ }
    }
    function startDSP() { settings.open(); root.odMods=3; root.odOpen("@TEST_SECTION@") }
}
'''.replace('@TEST_SECTION@', section)
        pack = {'Skin/EmbeddedMain.qml': source,
                'Skin/MixerTabContent.qml': 'Item { property var entries: [EntryBase.ListEntry { text: "Fader Echo" }] }'}
        with patch.object(output_dsp_ui, 'feature', return_value=True):
            output_dsp_ui.add_output_dsp(pack, base, 'Skin/')
        source = pack['Skin/EmbeddedMain.qml']
        old_url='file:///data/enginex/ui/mods-overlay/EngineXMods/'
        polling='running: root.scBoard === "JC11"; triggeredOnStart: true'
        assert source.count(old_url) == 1 and source.count(polling) == 1
        source=source.replace(old_url,base.as_uri()+'/').replace(polling,'running: false; triggeredOnStart: false')
        (base / 'Settings.qml').write_text(source)
        test = '''import QtQuick 2.12
import QtTest 1.2
TestCase {
    name: "DSPSettings"
    when: windowShown
    function test_panel_above_settings() {
        var component=Qt.createComponent("Settings.qml")
        compare(component.status,Component.Ready,component.errorString())
        var win=component.createObject(null)
        verify(win !== null,"Settings window creation")
        try {
            wait(200)
            mouseClick(win.mainButton)
            compare(win.testClicks,1,"Inactive DSP loader leaves main UI interactive")
            win.startDSP()
            tryCompare(win.settingsDrawer,"position",1,5000)
            tryCompare(win.panelLoader,"status",Loader.Ready,5000)
            verify(win.panelLoader.parent === win.overlayParent,"DSP_PARENT_BELOW_SETTINGS")
            var popup=findChild(win.panelLoader.item,"outputDSPDialog")
            verify(popup !== null,"DSP popup exists")
            tryCompare(popup,"visible",true,1000)
            var closeButton=findChild(win.panelLoader.item,"outputDSPClose")
            verify(closeButton !== null,"DSP close button exists")
            wait(300)
            mouseClick(closeButton)
            tryCompare(win.panelLoader,"active",false,1000)
            verify(win.settingsDrawer.visible,"Settings stays accessible after closing DSP")
            mouseClick(win.settingsButton)
            compare(win.testClicks,2,"Settings accepts input after DSP closes")
            win.settingsDrawer.close()
            tryCompare(win.settingsDrawer,"position",0,5000)
            mouseClick(win.mainButton)
            compare(win.testClicks,3,"Main UI accepts input after Settings closes")
        } finally {
            win.destroy()
        }
    }
}
'''
        (base / 'tst_Settings.qml').write_text(test)
        env = dict(os.environ, QT_QPA_PLATFORM='offscreen', QT_QUICK_BACKEND='software', QT_SELECT='qt5')
        command=['qmltestrunner','-input',str(base / 'tst_Settings.qml')]
        if section == 'eq':
            (base / 'Settings.qml').write_text(source.replace('        parent: Overlay.overlay ? Overlay.overlay : uiContainer\n',''))
            old_result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=20)
            old_log=old_result.stdout+old_result.stderr
            if old_result.returncode == 0 or 'DSP_PARENT_BELOW_SETTINGS' not in old_log:
                print(old_log)
                raise SystemExit('Settings regression did not reject the old loader parent')
            print('PASS old Settings loader fails the popup-overlay check')
            (base / 'Settings.qml').write_text(source)
        result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=20)
        print(section,"exit="+str(result.returncode),result.stdout,result.stderr)
        if result.returncode or any(word in result.stdout+result.stderr for word in ['ReferenceError','TypeError','is not a type','Cannot assign']):
            raise SystemExit('Settings pointer-delivery regression test failed')
