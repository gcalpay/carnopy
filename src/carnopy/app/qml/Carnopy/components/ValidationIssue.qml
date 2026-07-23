import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Carnopy

Control {
    id: root

    property string field: ""
    property string issue: ""

    Accessible.name: issue.length > 0 ? issue : qsTr("No local validation issue")
    bottomPadding: 10
    leftPadding: 12
    rightPadding: 12
    topPadding: 10
    visible: issue.length > 0

    background: Rectangle {
        border.color: Theme.danger
        border.width: 1
        color: Theme.dangerSoft
        radius: Theme.radiusSmall
    }

    contentItem: ColumnLayout {
        spacing: Theme.spacingTiny

        Label {
            Layout.fillWidth: true
            color: Theme.danger
            font.family: Theme.sansFamily
            font.pixelSize: 12
            font.weight: Font.Medium
            text: root.issue
            wrapMode: Text.Wrap
        }

        Label {
            Layout.fillWidth: true
            color: Theme.textMuted
            font.family: Theme.monoFamily
            font.pixelSize: 10
            text: root.field
            visible: root.field.length > 0
            wrapMode: Text.WrapAnywhere
        }
    }
}
