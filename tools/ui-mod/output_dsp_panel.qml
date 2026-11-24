import QtQuick 2.12
import QtQuick.Controls 2.5 as ODC
import QtQuick.Layouts 1.12 as ODL

Item {
    id: odHost
    signal closed()
    ODC.Popup {
        id: odDialog
        palette.windowText: "#e3eaf5"; palette.text: "#e3eaf5"
        objectName: "outputDSPDialog"
        parent: ODC.Overlay.overlay
        visible: odHost.visible; modal: true; focus: true; padding: 0; z: 100000
        closePolicy: ODC.Popup.NoAutoClose
        anchors.centerIn: parent
        width: Math.min(parent.width-32,920); height: Math.min(parent.height-32,580)
        onClosed: odHost.closed()
        contentItem: Rectangle {
    id: odPanel
    onClosed: odDialog.close()
    color: "#131b24"; radius: 8
    property string section: "@SECTION@"
    signal closed()
    property var pending: null
    Component.onCompleted: request(null)
    Component.onDestruction: if(pending)pending.abort()
    Timer { id: requestTimeout; interval: 3000; onTriggered: {if(odPanel.pending)odPanel.pending.abort();odPanel.pending=null;odPanel.busy=false;odPanel.message="DSP unavailable. Check the enabled Mod and native core."} }
    property bool advanced: false
    property bool busy: false
    property int pair: 0
    property var profiles: []
    property var vals: []
    property string message: ""
    property bool dirty: false
    function request(body) {
        if(busy)return
        busy=true
        var x=new XMLHttpRequest();pending=x;requestTimeout.restart()
        x.open(body?"POST":"GET","http://127.0.0.1:8080/v1/enginex/output-dsp")
        if(body)x.setRequestHeader("Content-Type","application/json")
        x.onreadystatechange=function(){
            if(x.readyState!==4)return
            requestTimeout.stop();pending=null;busy=false
            if(x.status!==200){message="DSP request failed: "+x.status;return}
            try {
                var data=JSON.parse(x.responseText), bit=section==="eq"?1:2
                if(data.version!==1 || !(data.enabled&bit) || !data.profiles || data.profiles.length!==4)throw new Error("Matching native core and enabled Mod required")
                for(var i=0;i<4;i++){if(data.profiles[i].length!==35)throw new Error("Invalid profile");for(var j=0;j<35;j++)if(typeof data.profiles[i][j]!=="number"||!isFinite(data.profiles[i][j]))throw new Error("Invalid value")}
                profiles=data.profiles;vals=profiles[pair].slice()
                dirty=false;message=body?"Saved settings":"Ready"
            } catch(e) { vals=[];message="DSP unavailable: "+e.message }
        }
        x.send(body?JSON.stringify(body):null)
    }
    function change(i,v){
        if(busy||vals.length!==35)return
        var a=vals.slice()
        if(i===4)v=Math.max(v,a[5]+5)
        if(i===5)v=Math.min(v,a[4]-5)
        a[i]=v;vals=a;dirty=true;message="Unsaved changes"
    }
    function select(i){
        if(busy||dirty||profiles.length!==4)return
        pair=i;vals=profiles[i].slice()
    }
    // RBJ coefficients match the native filters. 48 kHz is a preview rate.
    function response(type,hz,q,db,f) {
        if(hz<=0 || (type<3 && db===0))return 0
        var w=2*Math.PI*Math.min(hz,48000*.46)/48000, s=Math.sin(w), c=Math.cos(w)
        var A=Math.pow(10,db/40), al=s/(2*q), b0,b1,b2,a0,a1,a2
        if(type===0){b0=1+al*A;b1=-2*c;b2=1-al*A;a0=1+al/A;a1=-2*c;a2=1-al/A}
        else if(type===1||type===2){
            var t=2*Math.sqrt(A)*al,m=A-1,p=A+1
            if(type===1){b0=A*(p-m*c+t);b1=2*A*(m-p*c);b2=A*(p-m*c-t);a0=p+m*c+t;a1=-2*(m+p*c);a2=p+m*c-t}
            else {b0=A*(p+m*c+t);b1=-2*A*(m+p*c);b2=A*(p+m*c-t);a0=p-m*c+t;a1=2*(m-p*c);a2=p-m*c-t}
        } else {b0=(1+c)*.5;b1=-2*b0;b2=b0;a0=1+al;a1=-2*c;a2=1-al}
        var z=2*Math.PI*f/48000, cr=Math.cos(z), ci=Math.sin(z), dr=Math.cos(2*z), di=Math.sin(2*z)
        var nr=b0+b1*cr+b2*dr,ni=b1*ci+b2*di,ar=a0+a1*cr+a2*dr,ai=a1*ci+a2*di
        return 10*Math.log(Math.max(1e-16,(nr*nr+ni*ni)/(ar*ar+ai*ai)))/Math.LN10
    }
    onValsChanged: if(odGraph)odGraph.requestPaint()
    MouseArea { anchors.fill: parent; onClicked: {} }
    ODL.ColumnLayout {
        anchors.fill: parent; anchors.margins: 16; spacing: 8
        ODL.RowLayout {
            ODC.Label {text: odPanel.section==="eq"?"OUTPUT EQUALIZER":"SUBHARMONIC SYNTH";color:"white";font.pixelSize:22}
            Item {ODL.Layout.fillWidth:true}
            ODC.Switch {text:"Advanced";checked:odPanel.advanced;onToggled:odPanel.advanced=checked}
            ODC.Button {objectName:"outputDSPApply";text:"Apply";enabled:!odPanel.busy&&odPanel.vals.length===35&&odPanel.dirty;onClicked:odPanel.request({section:odPanel.section,pair:odPanel.pair,values:odPanel.vals})}
            ODC.Button {objectName:"outputDSPClose";text:odPanel.dirty?"Discard / close":"Close";onClicked:odPanel.closed()}
        }
        ODL.RowLayout {
            Repeater {
                model:["Main","Booth","Phones","Zone"]
                ODC.Button {text:modelData;checkable:true;checked:odPanel.pair===index;enabled:!odPanel.busy&&!odPanel.dirty;onClicked:odPanel.select(index)}
            }
            ODC.Label {text:odPanel.message;color:"#9ab4c6"}
        }
        ODC.ScrollView {
            ODL.Layout.fillWidth:true; ODL.Layout.fillHeight:true;clip:true
            Column {
                width:odPanel.width-52;spacing:10
                ODC.Switch {
                    visible:odPanel.section==="eq" && @EQ@;text:"Output EQ + highpass"
                    checked:odPanel.vals[0]===1;enabled:!odPanel.busy
                    onToggled:odPanel.change(0,checked?1:0)
                }
                Canvas {
                    id:odGraph;visible:odPanel.section==="eq" && @EQ@
                    width:parent.width;height:142
                    onPaint:{
                        var ctx=getContext("2d");ctx.clearRect(0,0,width,height)
                        ctx.fillStyle="#0b1219";ctx.fillRect(0,0,width,height)
                        ctx.strokeStyle="#304050";ctx.beginPath();ctx.moveTo(0,height/2);ctx.lineTo(width,height/2);ctx.stroke()
                        ctx.fillStyle="#9cabb9";ctx.font="11px sans-serif"
                        var ticks=[10,100,1000,3000,10000,22000]
                        for(var i=0;i<ticks.length;i++){var xx=Math.log(ticks[i]/10)/Math.log(2200)*width;ctx.fillText(ticks[i]>=1000?(ticks[i]/1000)+"k":ticks[i],Math.min(width-25,xx),height-5)}
                        var v=odPanel.vals;if(v.length!==35)return
                        ctx.strokeStyle="#44d4ba";ctx.lineWidth=2;ctx.beginPath()
                        for(var k=0;k<width;k++){
                            var f=10*Math.pow(2200,k/width),g=0
                            if(v[0]){
                                for(var b=0;b<8;b++){var j=11+3*b;g+=odPanel.response(b===0?1:b===7?2:0,v[j],v[j+1],v[j+2],f)}
                                if(v[1])g+=odPanel.response(3,v[1],.541196,0,f)+odPanel.response(3,v[1],1.306563,0,f)
                            }
                            var y=Math.max(3,Math.min(height-18,height/2-g*3));if(k===0)ctx.moveTo(k,y);else ctx.lineTo(k,y)
                        }ctx.stroke()
                    }
                }
                ODC.Label {visible:odPanel.section==="eq" && @EQ@;text:"10 Hz – 22 kHz · calculated response at 48 kHz";color:"#9ab4c6"}
                Row {
                    enabled:!odPanel.busy && odPanel.vals.length===35
                    visible:odPanel.section==="eq" && @EQ@;spacing:5
                    Repeater {
                        model:8
                        Column {
                            property int j:11+3*index
                            width:(odPanel.width-95)/8
                            ODC.Label {text:(index===0?"LOW ":index===7?"HIGH ":"")+Math.round(odPanel.vals[j]||0)+" Hz";color:"white"}
                            ODC.Slider {orientation:Qt.Vertical;height:105;from:-12;to:12;stepSize:.5;value:odPanel.vals[j+2]||0;onMoved:odPanel.change(j+2,value)}
                            ODC.Label {text:(odPanel.vals[j+2]||0).toFixed(1)+" dB";color:"white"}
                            ODC.SpinBox {visible:odPanel.advanced;width:parent.width;from:20;to:22000;editable:true;value:odPanel.vals[j]||90;onValueModified:odPanel.change(j,value)}
                            ODC.SpinBox {
                                visible:odPanel.advanced;width:parent.width;from:30;to:800;stepSize:5;editable:true;value:Math.round((odPanel.vals[j+1]||1)*100)
                                textFromValue:function(v){return "Q "+(v/100).toFixed(2)}
                                valueFromText:function(t){return Math.round(parseFloat(t.replace("Q ",""))*100)}
                                onValueModified:odPanel.change(j+1,value/100)
                            }
                        }
                    }
                }
                ODC.Label {visible:odPanel.section==="eq" && @EQ@;text:"Highpass · 24 dB/oct · "+(odPanel.vals[1]||0)+" Hz (0 = off)";color:"white"}
                ODC.Slider {enabled:!odPanel.busy && odPanel.vals.length===35;visible:odPanel.section==="eq" && @EQ@;width:parent.width;from:0;to:150;stepSize:5;value:odPanel.vals[1]||0;onMoved:odPanel.change(1,value<10?0:value)}
                ODC.Switch {enabled:!odPanel.busy && odPanel.vals.length===35;visible:odPanel.section==="sub" && @SUB@;text:"SUB · octave-down synthesizer";checked:odPanel.vals[2]===1;onToggled:odPanel.change(2,checked?1:0)}
                Repeater {
                    model:[{i:3,t:"Strength %",lo:0,hi:100},{i:4,t:"Maximum sub frequency Hz",lo:30,hi:80},{i:5,t:"Minimum sub frequency Hz",lo:15,hi:55},{i:6,t:"Low band %",lo:0,hi:100},{i:7,t:"High band %",lo:0,hi:100},{i:8,t:"Detection threshold dBFS",lo:-80,hi:-12},{i:9,t:"Attack ms",lo:2,hi:100},{i:10,t:"Release ms",lo:20,hi:500}]
                    ODL.RowLayout {
                        enabled:!odPanel.busy && odPanel.vals.length===35
                        visible:odPanel.section==="sub" && @SUB@ && (index<2||odPanel.advanced);width:odPanel.width-60
                        // Column is a positioner, so give each nested layout a height.
                        height:40
                        ODC.Label {text:modelData.t;color:"white";ODL.Layout.preferredWidth:240}
                        ODC.Slider {objectName:"outputDSPSubSlider"+index;ODL.Layout.fillWidth:true;from:modelData.lo;to:modelData.hi;stepSize:1;value:odPanel.vals[modelData.i]||0;onMoved:odPanel.change(modelData.i,value)}
                        ODC.Label {text:(odPanel.vals[modelData.i]||0).toFixed(0);color:"white"}
                    }
                }
            }
        }
    }
}

    }
}
