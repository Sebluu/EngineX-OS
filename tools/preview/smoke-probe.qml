// CI bootstrap only. Create the target outside the disabled debug-warning item.
import QtQuick
import QtQuick.Window
Item {
    id: bootstrap
    property var probe: null
    Timer {
        interval: 500; running: true; repeat: true
        onTriggered: {
            const window=bootstrap.Window.window
            if (!window) return
            const component=Qt.createComponent("file:/tmp/preview/smoke-target.qml")
            if (component.status !== Component.Ready) { console.warn(component.errorString()); return }
            bootstrap.probe=component.createObject(window.contentItem)
            if (!bootstrap.probe) return
            bootstrap.probe.open()
            stop()
        }
    }
}
