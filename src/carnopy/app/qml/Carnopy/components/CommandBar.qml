import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Carnopy

Control {
    id: root

    property string breadcrumb: qsTr("Local workbench")
    property bool canSave: false
    property bool canSaveAs: false
    property string effectiveTheme: "dark"
    property bool documentOpen: false
    property bool documentDirty: false
    property bool appearanceExpanded: true
    property string pageTitle: qsTr("Workspace")
    property bool showRailMenu: false
    property bool showInspectorButton: false
    property bool inspectorOpen: false
    property bool showAppearanceSelector: true
    property string statusLabel: qsTr("Shell ready")
    property string statusTone: "success"
    property string themeMode: "dark"
    readonly property alias inspectorToggleControl: inspectorToggleButton
    readonly property alias railMenuControl: railMenuButton

    signal inspectorToggleRequested
    signal appearanceModeRequested(string mode)
    signal railMenuRequested
    signal closeConfigurationRequested
    signal saveAsRequested
    signal saveRequested

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
            id: railMenuButton

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
            enabled: root.canSave
            objectName: "commandSaveButton"
            onClicked: root.saveRequested()
            text: root.documentDirty ? qsTr("Save changes") : qsTr("Save")
            tone: "primary"
            visible: root.documentOpen
        }

        AppButton {
            enabled: root.canSaveAs
            objectName: "commandSaveAsButton"
            onClicked: root.saveAsRequested()
            text: qsTr("Save As…")
            visible: root.documentOpen && root.width >= 760
        }

        AppButton {
            objectName: "commandCloseConfigurationButton"
            onClicked: root.closeConfigurationRequested()
            text: qsTr("Close")
            visible: root.documentOpen && root.width >= 620
        }

        AppearanceSelector {
            effectiveTheme: root.effectiveTheme
            expanded: root.appearanceExpanded
            objectName: "commandAppearanceSelector"
            onModeRequested: mode => root.appearanceModeRequested(mode)
            themeMode: root.themeMode
            visible: root.showAppearanceSelector
        }

        AppButton {
            id: inspectorToggleButton

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
