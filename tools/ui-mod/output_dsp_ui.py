"""Add only JC11 controls to generated QML packs; never change vendor resources."""
from pathlib import Path
import re

HERE=Path(__file__).resolve().parent
def feature(name):
    return bool(re.search(r'^#define OD_FEATURE_'+name+r' 1$',(HERE/'output_dsp_features.h').read_text(),re.M))

def add_output_dsp(base,qrc,skin):
    eq,sub=feature("EQ"),feature("SUB")
    if not (eq or sub): return
    rel=skin+"EmbeddedMain.qml"
    src=base[rel]
    panel=(HERE/"output_dsp_panel.qml").read_text()
    panel=panel.replace("@EQ@",str(eq).lower()).replace("@SUB@",str(sub).lower())
    at=re.search(r'^import ',src,re.M)
    if not at: raise RuntimeError("EmbeddedMain imports missing")
    src=src[:at.start()]+"import QtQuick.Controls 2.5 as ODC\nimport QtQuick.Layouts 1.12 as ODL\n"+src[at.start():]
    at=src.rfind("}")
    bridge='''
    function odOpen(section) {
        if (Config.device.name !== "JC11") return
        if (odPanel.busy) return
        odPanel.section=section; odPanel.pair=0; odPanel.advanced=false
        odPanel.vals=[]; odPanel.profiles=[]; odPanel.dirty=false; odPanel.message="Loading..."
        odPanel.visible=true; odPanel.request(null)
    }
    property bool odSubEnabled: false
    property bool odSubBusy: false
    function odToggle() {
        if (odSubBusy || Config.device.name !== "JC11") return
        odSubBusy=true
        var x=new XMLHttpRequest()
        x.open("POST","http://127.0.0.1:8080/v1/enginex/output-dsp")
        x.setRequestHeader("Content-Type","application/json")
        x.onreadystatechange=function(){
            if(x.readyState!==4)return
            root.odSubBusy=false
            if(x.status===200)root.odSubEnabled=JSON.parse(x.responseText)[0][2]===1
        }
        x.send(JSON.stringify({section:"sub",pair:0,toggle:true}))
    }
    Timer {
        interval: 1500; repeat: true; running: @SUB@ && Config.device.name==="JC11"
        onTriggered: {
            if(root.odSubBusy || odPanel.visible)return
            root.odSubBusy=true
            var x=new XMLHttpRequest()
            x.open("GET","http://127.0.0.1:8080/v1/enginex/output-dsp")
            x.onreadystatechange=function(){
                if(x.readyState!==4)return
                root.odSubBusy=false
                if(x.status===200)root.odSubEnabled=JSON.parse(x.responseText)[0][2]===1
            }
            x.send()
        }
    }
'''.replace("@SUB@",str(sub).lower())
    base[rel]=src[:at]+bridge+"\n"+panel+"\n"+src[at:]
    # Existing generated Mixer settings, before Fader Echo. No EQ performance shortcut.
    candidates=[p for p,t in base.items() if p.endswith("MixerTabContent.qml") and 'text: "Fader Echo"' in t]
    if len(candidates)!=1: raise RuntimeError("Output DSP: missing unique mixer settings anchor")
    p=candidates[0];t=base[p]
    m=re.search(r'EntryBase\.ListEntry\s*\{\s*text: "Fader Echo"',t)
    if not m: raise RuntimeError("Output DSP: mixer anchor changed")
    rows=[]
    for enabled,title,section in [(eq,"Output Equalizer","eq"),(sub,"Subharmonic Synthesizer","sub")]:
        if enabled:
            rows.append('EntryBase.ListEntry { text: "'+title+'"; visible: Config.device.name === "JC11"; values: ["Closed", "Open"]; currentValue: "Closed"; onSelected: function(index) { if(index===1)root.odOpen("'+section+'") } },\n\t\t')
    base[p]=t[:m.start()]+"".join(rows)+t[m.start():]
    if not sub:return
    # Match the *instance*, never the type declaration. If stock skin changes,
    # retain settings access rather than covering the performance screen.
    candidates=[]
    for f in (qrc/skin).rglob("*.qml"):
        path=f.relative_to(qrc).as_posix()
        t=base.get(path) or f.read_text(encoding="utf-8")
        for m in re.finditer(r'(?mi)^([ \t]*)(?:\w+\.)?TouchFxButton\s*\{',t):
            if path!=rel:candidates.append((path,t,m))
    if len(candidates)!=1:
        print("Output DSP: Touch FX placement unverified; SUB available in Mixer settings only")
        return
    p,t,m=candidates[0]
    button=m.group(1)+'''Rectangle {
        visible: Config.device.name === "JC11"; width: 52; height: 34; radius: 5
        color: root.odSubEnabled ? "#167c66" : "#23313e"
        Text { anchors.centerIn: parent; text: "SUB"; color: "white" }
        MouseArea {
            anchors.fill: parent
            property bool held: false
            onPressed: held=false
            onClicked: if(!held)root.odToggle()
            onPressAndHold: {held=true;root.odOpen("sub")}
        }
    }
'''
    base[p]=t[:m.start()]+button+t[m.start():]
