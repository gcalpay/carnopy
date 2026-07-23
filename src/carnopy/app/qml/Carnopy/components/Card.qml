import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Carnopy

Control {
    id: root

    default property alias contentData: body.data
    property bool flat: false
    property color metaColor: Theme.success
    property string meta: ""
    property string metaObjectName: ""
    property string sectionNumber: ""
    property string title: ""
    property string subtitle: ""

    implicitHeight: Math.max(120, body.implicitHeight + topPadding + bottomPadding)
    implicitWidth: 300
    bottomPadding: flat ? 0 : 16
    leftPadding: flat ? 0 : 16
    rightPadding: flat ? 0 : 16
    topPadding: flat ? 0 : 16

    background: Rectangle {
        border.color: root.flat ? "transparent" : Theme.divider
        border.width: root.flat ? 0 : 1
        color: root.flat ? "transparent" : Theme.surface
        radius: root.flat ? 0 : Theme.radiusMedium
    }

    contentItem: ColumnLayout {
        id: body

        spacing: Theme.spacingSmall

        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.spacingSmall
            visible: root.title.length > 0

            Label {
                Layout.fillWidth: true
                color: Theme.text
                font.family: Theme.sansFamily
                font.pixelSize: 15
                font.weight: Font.DemiBold
                text: (root.sectionNumber.length > 0 ? root.sectionNumber + ".  " : "") + root.title
                wrapMode: Text.Wrap
            }

            Label {
                color: root.metaColor
                font.family: Theme.sansFamily
                font.pixelSize: 12
                font.weight: Font.Medium
                objectName: root.metaObjectName
                text: root.meta
                visible: root.meta.length > 0
            }
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
