import QtQuick
import QtQuick.Controls
import Carnopy

Item {
    id: root

    property string name: ""
    property color iconColor: Theme.text
    property int iconSize: 20

    implicitWidth: iconSize
    implicitHeight: iconSize

    ToolButton {
        anchors.fill: parent
        Accessible.ignored: true
        display: AbstractButton.IconOnly
        enabled: false
        focusPolicy: Qt.NoFocus
        hoverEnabled: false
        icon.color: root.iconColor
        icon.height: root.iconSize
        icon.source: Theme.iconSource(root.name)
        icon.width: root.iconSize
        opacity: 1
        padding: 0

        background: Item {}
    }
}
