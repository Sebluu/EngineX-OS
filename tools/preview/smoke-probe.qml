// CI input target only. Never part of the interactive preview or a Mod.
import QtQuick
import QtQuick.Controls
import QtQuick.Window
Item {
    Popup {
        id: marker
        x: 20; y: 20; width: 120; height: 120
        padding: 0; modal: true; focus: true; visible: true
        parent: Overlay.overlay; z: 10000000
        closePolicy: Popup.NoAutoClose
        contentItem: Item {
            id: target
            focus: true
            Rectangle { anchors.fill: parent; color: "red" }
            MouseArea {
                anchors.fill: parent
                onClicked: { target.forceActiveFocus(); console.warn("PREVIEW_MOUSE_PASS") }
            }
            Keys.onPressed: function(event) {
                if (event.key === Qt.Key_A) console.warn("PREVIEW_KEY_PASS")
            }
        }
    }
    Timer {
        interval: 500; running: true; repeat: true
        onTriggered: {
            if (!target.Window.window || !marker.visible) return
            const point=target.mapToItem(target.Window.window.contentItem,60,60)
            console.warn("PREVIEW_TARGET|"+point.x+"|"+point.y+"|")
            stop()
        }
    }
}
