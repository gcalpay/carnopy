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
    property bool canValidate: false
    property bool configurationDirty: false
    property string configurationFile: ""
    property bool configurationOpen: false
    property var configController: null
    property bool datasetValid: false
    property string datasetIssue: ""
    property var executionController: null
    property var inspectionController: null
    property var activityController: null
    property var preparationDraft: null
    property var preparationWorkflowController: null
    property var sweepDraft: null
    property var sweepWorkflowController: null
    property string pageKey: "workspace"
    property bool visualizationActiveEdit: false
    property string visualizationIssue: ""
    property bool visualizationValid: false
    property string workerValidationIssue: ""
    property var workerValidationIssues: []
    property string workerValidationState: "unavailable"
    property string workspacePath: ""
    property string workspaceState: "unavailable"
    property bool yamlAvailable: false
    readonly property alias closeControl: inspectorCloseButton

    signal closeRequested
    signal attentionRequested(string section, string field, int row)
    signal inspectionExploreRequested
    signal validateRequested

    function validationLabel(state) {
        const labels = {
            "unavailable": qsTr("Not available"),
            "blocked": qsTr("Blocked"),
            "not_run": qsTr("Not run"),
            "running": qsTr("Running"),
            "valid": qsTr("Valid"),
            "invalid": qsTr("Invalid"),
            "failed": qsTr("Failed"),
            "stale": qsTr("Stale")
        };
        return labels[state] || qsTr("Not available");
    }

    implicitWidth: 304
    leftPadding: 18
    rightPadding: 18
    topPadding: 14
    bottomPadding: 14

    background: Rectangle {
        border.color: Theme.divider
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
            visible: root.pageKey !== "run" && root.pageKey !== "inspect" && root.pageKey
                     !== "activity" && root.pageKey !== "sweeps" && root.pageKey !== "preparation"

            ScrollBar.vertical: ScrollBar {
                policy: ScrollBar.AsNeeded
            }

            ColumnLayout {
                id: inspectorColumn

                spacing: Theme.spacingMedium
                width: parent.width

                Card {
                    flat: true
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

                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 1
                    color: Theme.divider
                }

                Card {
                    flat: true
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
                            text: qsTr("Draft YAML check")
                        }

                        Label {
                            color: Theme.text
                            font.family: Theme.sansFamily
                            font.pixelSize: 12
                            font.weight: Font.Medium
                            objectName: "inspectorWorkerValidationState"
                            text: root.validationLabel(root.workerValidationState)
                        }
                    }

                    Label {
                        Layout.fillWidth: true
                        color: Theme.textMuted
                        font.family: Theme.sansFamily
                        font.pixelSize: 11
                        objectName: "inspectorWorkerValidationIssue"
                        text: root.workerValidationIssue
                        visible: text.length > 0
                        wrapMode: Text.Wrap
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

                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 1
                    color: Theme.divider
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
                    flat: true
                    Layout.fillWidth: true
                    subtitle: root.workspaceState !== "editing" ? qsTr(
                                                                      "Open a configuration to see Dataset validation.") :
                                                                  (root.datasetValid ? qsTr(
                                                                                           "All Dataset fields are locally complete. The optional draft check does not authorize Save or Generate.") :
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

                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 1
                    color: Theme.divider
                }

                Card {
                    flat: true
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

                AppButton {
                    Layout.fillWidth: true
                    enabled: root.canValidate
                    objectName: "inspectorValidateButton"
                    onClicked: root.validateRequested()
                    text: root.workerValidationState === "running" ? qsTr("Checking draft…") : qsTr(
                                                                         "Check current draft YAML")
                    tone: "primary"
                    visible: root.configurationOpen
                }
            }
        }

        RunContextInspector {
            Layout.fillHeight: true
            Layout.fillWidth: true
            executionController: root.executionController
            visible: root.pageKey === "run" && root.executionController !== null
        }

        InspectionContextInspector {
            Layout.fillHeight: true
            Layout.fillWidth: true
            inspectionController: root.inspectionController
            onExploreRequested: root.inspectionExploreRequested()
            visible: root.pageKey === "inspect" && root.inspectionController !== null
        }

        ActivityContextInspector {
            Layout.fillHeight: true
            Layout.fillWidth: true
            activityController: root.activityController
            visible: root.pageKey === "activity" && root.activityController !== null
        }

        WorkflowContextInspector {
            Layout.fillHeight: true
            Layout.fillWidth: true
            configController: root.configController
            firstInvalidField: root.sweepDraft !== null ? root.sweepDraft.firstInvalidField : ""
            firstInvalidRow: root.sweepDraft !== null ? root.sweepDraft.firstInvalidRow : -1
            localIssue: root.sweepDraft !== null ? root.sweepDraft.issue : ""
            localValid: root.sweepDraft !== null && root.sweepDraft.locallyValid
            objectName: "sweepWorkflowContextInspector"
            onAttentionRequested: (section, field, row) => root.attentionRequested(section, field,
                                                                                   row)
            onValidateRequested: root.validateRequested()
            visible: root.pageKey === "sweeps" && root.sweepDraft !== null
                     && root.sweepWorkflowController !== null
            transientEditActive: root.sweepDraft !== null && root.sweepDraft.hasActiveComparisonEdit
            workflowController: root.sweepWorkflowController
            workflowSection: "sweep"
            workflowTitle: qsTr("Model Sweep")
        }

        WorkflowContextInspector {
            Layout.fillHeight: true
            Layout.fillWidth: true
            configController: root.configController
            firstInvalidField: root.preparationDraft !== null
                               ? root.preparationDraft.firstInvalidField : ""
            firstInvalidRow: root.preparationDraft !== null ? root.preparationDraft.firstInvalidRow :
                                                              -1
            localIssue: root.preparationDraft !== null ? root.preparationDraft.issue : ""
            localValid: root.preparationDraft !== null && root.preparationDraft.locallyValid
            objectName: "preparationWorkflowContextInspector"
            onAttentionRequested: (section, field, row) => root.attentionRequested(section, field,
                                                                                   row)
            onValidateRequested: root.validateRequested()
            visible: root.pageKey === "preparation" && root.preparationDraft !== null
                     && root.preparationWorkflowController !== null
            transientEditActive: root.preparationDraft !== null
                                 && root.preparationDraft.hasActiveScenarioEdit
            workflowController: root.preparationWorkflowController
            workflowSection: "preparation"
            workflowTitle: qsTr("ML Preparation")
        }
    }
}
