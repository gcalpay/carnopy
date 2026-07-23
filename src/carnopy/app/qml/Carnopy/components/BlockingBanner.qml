import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Carnopy

Control {
    id: root

    property string actionText: qsTr("Go to issue")
    property string field: ""
    property string message: ""
    property int row: -1
    property string section: "none"
    property string title: qsTr("Configuration needs attention")

    signal actionRequested(string section, string field, int row)

    implicitHeight: content.implicitHeight + topPadding + bottomPadding
    leftPadding: 16
    rightPadding: 16
    topPadding: 14
    bottomPadding: 14

    background: Rectangle {
        border.color: Theme.danger
        border.width: 1
        color: Theme.dangerSoft
        radius: Theme.radiusMedium
    }

    contentItem: RowLayout {
        id: content

        spacing: Theme.spacingMedium

        ColumnLayout {
            Layout.fillWidth: true
            spacing: Theme.spacingTiny

            Label {
                Layout.fillWidth: true
                color: Theme.danger
                font.family: Theme.sansFamily
                font.pixelSize: 14
                font.weight: Font.DemiBold
                text: root.title
                wrapMode: Text.Wrap
            }

            Label {
                Layout.fillWidth: true
                color: Theme.text
                font.family: Theme.sansFamily
                font.pixelSize: 12
                text: root.message
                visible: text.length > 0
                wrapMode: Text.Wrap
            }

            Label {
                Layout.fillWidth: true
                color: Theme.textMuted
                font.family: Theme.monoFamily
                font.pixelSize: 10
                text: root.row >= 0 ? root.field + qsTr(" · row %1").arg(root.row + 1) : root.field
                visible: root.field.length > 0
            }
        }

        AppButton {
            objectName: "blockingBannerAction"
            onClicked: root.actionRequested(root.section, root.field, root.row)
            text: root.actionText
            tone: "danger"
            visible: root.section !== "none" && root.field.length > 0
        }
    }
}
