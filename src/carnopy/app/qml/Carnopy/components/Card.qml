import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Carnopy

Control {
    id: root

    default property alias contentData: body.data
    property string title: ""
    property string subtitle: ""

    implicitHeight: Math.max(120, body.implicitHeight + topPadding + bottomPadding)
    implicitWidth: 300
    bottomPadding: 18
    leftPadding: 18
    rightPadding: 18
    topPadding: 18

    background: Rectangle {
        border.color: Theme.border
        border.width: 1
        color: Theme.surface
        radius: Theme.radiusMedium
    }

    contentItem: ColumnLayout {
        id: body

        spacing: Theme.spacingSmall

        Label {
            Layout.fillWidth: true
            color: Theme.text
            font.family: Theme.sansFamily
            font.pixelSize: 15
            font.weight: Font.DemiBold
            text: root.title
            visible: root.title.length > 0
            wrapMode: Text.Wrap
        }

        Label {
            Layout.fillWidth: true
            color: Theme.textMuted
            font.family: Theme.sansFamily
            font.pixelSize: 12
            text: root.subtitle
            visible: root.subtitle.length > 0
            wrapMode: Text.Wrap
        }
    }
}
