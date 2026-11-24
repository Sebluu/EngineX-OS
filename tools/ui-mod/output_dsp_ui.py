"""Lazy Settings launchers. Controls live in optional Mod Hub overlays, not the boot UI."""
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent

def feature(name):
    return bool(re.search(r'^#define OD_FEATURE_' + name + r' 1$',
                         (HERE / 'output_dsp_features.h').read_text(), re.M))

def add_output_dsp(base, qrc, skin):
    eq, sub = feature('EQ'), feature('SUB')
    if not (eq or sub):
        return
    rel = skin + 'EmbeddedMain.qml'
    src = base[rel]
    if not re.search(r'^import ', src, re.M) or not src.rstrip().endswith('}'):
        raise RuntimeError('Output DSP: EmbeddedMain structure changed')
    if 'function odOpen(' in src:
        raise RuntimeError('Output DSP: launchers already inserted')
    candidates = [p for p, t in base.items()
                  if p.endswith('MixerTabContent.qml') and 'text: "Fader Echo"' in t]
    if len(candidates) != 1:
        raise RuntimeError('Output DSP: missing unique mixer settings anchor')
    p = candidates[0]
    t = base[p]
    matches = list(re.finditer(r'EntryBase\.ListEntry\s*\{\s*text: "Fader Echo"', t))
    if len(matches) != 1:
        raise RuntimeError('Output DSP: mixer anchor changed or ambiguous')
    bridge = '''
    property int odMods: 0
    property var odStatusRequest: null
    function odOpen(section) {
        if (root.scBoard !== "JC11" || !(odMods & (section === "eq" ? 1 : 2))) return
        odModPanel.active=false
        odModPanel.source="file:///data/enginex/ui/active/EngineXMods/" + (section === "eq" ? "output-equalizer" : "subharmonic-synth") + "/Panel.qml"
        odModPanel.active=true
    }
    Loader {
        id: odModPanel
        anchors.fill: parent; z: 100000; active: false; asynchronous: true
        onStatusChanged: if(status===Loader.Error)active=false
    }
    Connections {
        target: odModPanel.item; ignoreUnknownSignals: true
        onClosed: odModPanel.active=false
    }
    Timer {
        id: odStatusTimeout; interval: 2000
        onTriggered: { if(root.odStatusRequest)root.odStatusRequest.abort();root.odStatusRequest=null;root.odMods=0 }
    }
    Timer {
        interval: 2500; repeat: true; running: root.scBoard === "JC11"; triggeredOnStart: true
        onTriggered: {
            if(root.odStatusRequest)return
            var x=new XMLHttpRequest();root.odStatusRequest=x;odStatusTimeout.restart()
            x.open("GET","http://127.0.0.1:8080/v1/enginex/output-dsp")
            x.onreadystatechange=function(){
                if(x.readyState!==4)return
                odStatusTimeout.stop();root.odStatusRequest=null;root.odMods=0
                try { if(x.status===200){var d=JSON.parse(x.responseText);if(d.version===1)root.odMods=d.enabled&@MASK@} }catch(e){}
                if(!root.odMods)odModPanel.active=false
            }
            x.send()
        }
    }
'''.replace('@MASK@', str((1 if eq else 0) | (2 if sub else 0)))
    rows = []
    for enabled, title, section, bit in [(eq, 'Output Equalizer', 'eq', 1),
                                          (sub, 'Subharmonic Synthesizer', 'sub', 2)]:
        if enabled:
            rows.append('EntryBase.ListEntry { text: "' + title + '"; visible: root.scBoard === "JC11" && !!(root.odMods & ' + str(bit) + '); values: ["Closed", "Open"]; currentValue: "Closed"; onSelected: function(index) { if(index===1)root.odOpen("' + section + '") } },\n\t\t')
    # Validate everything before mutating the pack. No Controls import at startup.
    at = src.rfind('}')
    base[rel] = src[:at] + bridge + src[at:]
    at = matches[0].start()
    base[p] = t[:at] + ''.join(rows) + t[at:]
