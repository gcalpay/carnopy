import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Carnopy

Control {
    id: root

    property bool closeButtonVisible: false
    property string blockingField: ""
    property string blockingIssue: ""
    property int blockingRow: -1
    property string blockingSection: "none"
    property bool configurationDirty: false
    property string configurationFile: ""
    property bool configurationOpen: false
    property bool datasetValid: false
    property string datasetIssue: ""
    property bool visualizationActiveEdit: false
    property string visualizationIssue: ""
    property bool visualizationValid: false
    property string workspacePath: ""
    property string workspaceState: "unavailable"
    property bool yamlAvailable: false
    readonly property alias closeControl: inspectorCloseButton

    signal closeRequested
    signal attentionRequested(string section, string field, int row)

    implicitWidth: 304
    leftPadding: 16
    rightPadding: 16
    topPadding: 16
    bottomPadding: 16

    background: Rectangle {
        border.color: Theme.border
        border.width: 1
        color: Theme.surfaceRaised
    }

    contentItem: ColumnLayout {
        spacing: Theme.spacingMedium

        RowLayout {
            Layout.fillWidth: true

            Label {
                Layout.fillWidth: true
                color: Theme.text
                font.family: Theme.sansFamily
                font.pixelSize: 16
                font.weight: Font.DemiBold
                text: qsTr("Context inspector")
            }

            AppButton {
                id: inspectorCloseButton

                Accessible.description: qsTr("Close context inspector")
                compact: true
                iconName: "panel-right-close"
                objectName: "inspectorCloseButton"
                onClicked: root.closeRequested()
                visible: root.closeButtonVisible
            }
        }

        Flickable {
            Layout.fillHeight: true
            Layout.fillWidth: true
            boundsBehavior: Flickable.StopAtBounds
            clip: true
            contentHeight: inspectorColumn.implicitHeight
            contentWidth: width
            flickableDirection: Flickable.VerticalFlick
            pixelAligned: true

            ScrollBar.vertical: ScrollBar {
                policy: ScrollBar.AsNeeded
            }

            ColumnLayout {
                id: inspectorColumn

                spacing: Theme.spacingMedium
                width: parent.width

                Card {
                    Layout.fillWidth: true
                    subtitle: root.workspacePath.length > 0 ? root.workspacePath : qsTr(
                                                                  "No local workspace is open.")
                    title: qsTr("Workspace")

                    Label {
                        Layout.fillWidth: true
                        color: Theme.textMuted
                        font.family: Theme.sansFamily
                        font.pixelSize: 12
                        text: root.workspaceState === "loading" ? qsTr(
                                                                      "Worker capabilities are loading through the shared request coordinator.") :
                                                                  qsTr("Workspace state comes from the authoritative desktop composition.")
                        wrapMode: Text.Wrap
                    }
                }

                Card {
                    Layout.fillWidth: true
                    title: qsTr("Document state")

                    RowLayout {
                        Layout.fillWidth: true

                        Label {
                            Layout.fillWidth: true
                            color: Theme.textMuted
                            font.family: Theme.sansFamily
                            font.pixelSize: 12
                            text: qsTr("Configuration")
                        }

                        Label {
                            color: Theme.text
                            font.family: Theme.sansFamily
                            font.pixelSize: 12
                            font.weight: Font.Medium
                            objectName: "inspectorConfigurationState"
                            text: !root.configurationOpen ? qsTr("Not loaded") : (
                                                                root.configurationDirty ? qsTr(
                                                                                              "Unsaved") :
                                                                                          qsTr("Saved"))
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true

                        Label {
                            Layout.fillWidth: true
                            color: Theme.textMuted
                            font.family: Theme.sansFamily
                            font.pixelSize: 12
                            text: qsTr("Worker validation")
                        }

                        Label {
                            color: Theme.text
                            font.family: Theme.sansFamily
                            font.pixelSize: 12
                            font.weight: Font.Medium
                            objectName: "inspectorWorkerValidationState"
                            text: !root.configurationOpen ? qsTr("Not available") : (
                                                                root.yamlAvailable ? qsTr(
                                                                                         "Validated on Save") :
                                                                                     qsTr("Blocked locally"))
                        }
                    }

                    Label {
                        Layout.fillWidth: true
                        color: Theme.textMuted
                        elide: Text.ElideMiddle
                        font.family: Theme.monoFamily
                        font.pixelSize: 10
                        text: root.configurationFile
                        visible: root.configurationOpen && text.length > 0
                    }
                }

                BlockingBanner {
                    Layout.fillWidth: true
                    actionText: qsTr("Focus")
                    field: root.blockingField
                    message: root.blockingIssue
                    onActionRequested: (section, field, row) => root.attentionRequested(section,
                                                                                        field, row)
                    row: root.blockingRow
                    section: root.blockingSection
                    title: qsTr("Configuration blocker")
                    visible: root.configurationOpen && !root.yamlAvailable && root.blockingSection
                             !== "none"
                }

                Card {
                    Layout.fillWidth: true
                    subtitle: root.workspaceState !== "editing" ? qsTr(
                                                                      "Open a configuration to see Dataset validation.") :
                                                                  (root.datasetValid ? qsTr(
                                                                                           "All Dataset fields are locally complete. Worker validation still runs before Save.") :
                                                                                       root.datasetIssue)
                    title: qsTr("Dataset validation")

                    StatusBadge {
                        label: root.workspaceState !== "editing" ? qsTr("Not available") : (
                                                                       root.datasetValid ? qsTr(
                                                                                               "Locally complete") :
                                                                                           qsTr("Needs attention"))
                        tone: root.workspaceState !== "editing" ? "neutral" : (root.datasetValid
                                                                               ? "success" :
                                                                                 "danger")
                    }
                }

                Card {
                    Layout.fillWidth: true
                    subtitle: root.workspaceState !== "editing" ? qsTr(
                                                                      "Open a configuration to define configured visualization.") :
                                                                  (root.visualizationActiveEdit
                                                                   ? qsTr("A temporary plot edit must be committed or cancelled before lifecycle changes.") :
                                                                     (root.visualizationValid ? qsTr(
                                                                                                    "Configured visualization is locally complete or disabled with latent state retained.") :
                                                                                                root.visualizationIssue))
                    title: qsTr("Visualization validation")

                    StatusBadge {
                        label: root.workspaceState !== "editing" ? qsTr("Not available") : (
                                                                       root.visualizationActiveEdit
                                                                       ? qsTr("Edit active") : (
                                                                             root.visualizationValid
                                                                             ? qsTr("Locally complete") :
                                                                               qsTr("Needs attention")))
                        tone: root.workspaceState !== "editing" ? "neutral" : (
                                                                      root.visualizationActiveEdit
                                                                      ? "warning" : (
                                                                            root.visualizationValid
                                                                            ? "success" : "danger"))
                    }
                }

                Item {
                    Layout.fillHeight: true
                    Layout.minimumHeight: 1
                }
            }
        }
    }
}
