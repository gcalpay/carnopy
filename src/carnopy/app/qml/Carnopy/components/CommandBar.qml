import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Carnopy

Control {
    id: root

    property string breadcrumb: qsTr("Local workbench")
    property bool canImport: false
    property bool canNew: false
    property bool canSave: false
    property bool canSaveAs: false
    property string effectiveTheme: "dark"
    property bool documentOpen: false
    property bool documentDirty: false
    property bool appearanceExpanded: true
    property string pageTitle: qsTr("Workspace")
    property string shellMode: "wide"
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
    signal importRequested
    signal newRequested
    signal railMenuRequested
    signal closeConfigurationRequested
    signal saveAsRequested
    signal saveRequested

    implicitHeight: 68
    leftPadding: 18
    rightPadding: 18

    background: Rectangle {
        color: Theme.surface

        Rectangle {
            anchors.bottom: parent.bottom
            anchors.left: parent.left
            anchors.right: parent.right
            color: Theme.divider
            height: 1
        }
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
            enabled: root.canNew
            iconName: root.shellMode === "compact" ? "database" : ""
            objectName: "commandNewButton"
            onClicked: root.newRequested()
            text: qsTr("New")
            visible: root.shellMode !== "narrow"
        }

        AppButton {
            enabled: root.canImport
            iconName: root.shellMode === "compact" ? "file-code" : ""
            objectName: "commandImportButton"
            onClicked: root.importRequested()
            text: qsTr("Import")
            visible: root.shellMode !== "narrow"
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
            visible: root.documentOpen && root.shellMode !== "narrow"
        }

        AppButton {
            objectName: "commandCloseConfigurationButton"
            onClicked: root.closeConfigurationRequested()
            text: qsTr("Close")
            visible: root.documentOpen && root.shellMode === "wide"
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

        ToolButton {
            id: overflowButton

            Accessible.name: qsTr("More document actions")
            activeFocusOnTab: true
            hoverEnabled: true
            implicitHeight: 36
            implicitWidth: 36
            objectName: "commandOverflowButton"
            onClicked: overflowMenu.open()
            visible: root.shellMode === "narrow"

            contentItem: Label {
                color: Theme.text
                font.family: Theme.sansFamily
                font.pixelSize: 22
                horizontalAlignment: Text.AlignHCenter
                text: "⋮"
                verticalAlignment: Text.AlignVCenter
            }

            background: Rectangle {
                border.color: overflowButton.activeFocus ? Theme.focus : Theme.borderStrong
                border.width: overflowButton.activeFocus ? 2 : 1
                color: overflowButton.hovered || overflowButton.down ? Theme.hover : Theme.surface
                radius: Theme.radiusSmall
            }
        }

        Menu {
            id: overflowMenu

            objectName: "commandOverflowMenu"

            MenuItem {
                enabled: root.canNew
                objectName: "commandOverflowNew"
                onTriggered: root.newRequested()
                text: qsTr("New")
            }

            MenuItem {
                enabled: root.canImport
                objectName: "commandOverflowImport"
                onTriggered: root.importRequested()
                text: qsTr("Import")
            }

            MenuItem {
                enabled: root.canSaveAs
                objectName: "commandOverflowSaveAs"
                onTriggered: root.saveAsRequested()
                text: qsTr("Save As…")
                visible: root.documentOpen
            }

            MenuItem {
                objectName: "commandOverflowClose"
                onTriggered: root.closeConfigurationRequested()
                text: qsTr("Close configuration")
                visible: root.documentOpen
            }
        }
    }
}
