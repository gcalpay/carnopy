import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Carnopy

Control {
    id: root

    property string breadcrumb: qsTr("Local workbench")
    property string pageTitle: qsTr("Workspace")
    property bool showRailMenu: false
    property bool showInspectorButton: false
    property bool inspectorOpen: false
    property string statusLabel: qsTr("Shell ready")
    property string statusTone: "success"

    signal inspectorToggleRequested
    signal railMenuRequested

    implicitHeight: 68
    leftPadding: 18
    rightPadding: 18

    background: Rectangle {
        border.color: Theme.border
        border.width: 1
        color: Theme.surface
    }

    contentItem: RowLayout {
        spacing: Theme.spacingMedium

        AppButton {
            Accessible.description: qsTr("Open application navigation")
            compact: true
            iconName: "panel-left-open"
            objectName: "railMenuButton"
            onClicked: root.railMenuRequested()
            visible: root.showRailMenu
        }

        ColumnLayout {
            Layout.fillWidth: true
            spacing: 1

            Label {
                Layout.fillWidth: true
                color: Theme.text
                elide: Text.ElideRight
                font.family: Theme.sansFamily
                font.pixelSize: 17
                font.weight: Font.DemiBold
                text: root.pageTitle
            }

            Label {
                Layout.fillWidth: true
                color: Theme.textMuted
                elide: Text.ElideMiddle
                font.family: Theme.sansFamily
                font.pixelSize: 11
                text: root.breadcrumb
            }
        }

        StatusBadge {
            label: root.statusLabel
            tone: root.statusTone
            visible: root.width >= 560
        }

        AppButton {
            Accessible.description: root.inspectorOpen ? qsTr("Collapse context inspector") : qsTr(
                                                             "Open context inspector")
            compact: true
            iconName: root.inspectorOpen ? "panel-right-close" : "panel-right-open"
            objectName: "inspectorToggleButton"
            onClicked: root.inspectorToggleRequested()
            visible: root.showInspectorButton
        }
    }
}
