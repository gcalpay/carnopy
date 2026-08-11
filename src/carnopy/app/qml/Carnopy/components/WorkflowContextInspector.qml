pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Carnopy

Flickable {
    id: root

    required property var configController
    required property string firstInvalidField
    required property int firstInvalidRow
    required property string localIssue
    required property bool localValid
    required property bool transientEditActive
    required property var workflowController
    required property string workflowSection
    required property string workflowTitle
    readonly property bool documentActive: configController.documentKind
                                           === workflowController.documentKind

    signal attentionRequested(string section, string field, int row)
    signal validateRequested

    function stateLabel(value) {
        const labels = {
            "unavailable": qsTr("Unavailable"),
            "ready": qsTr("Ready"),
            "starting": qsTr("Starting"),
            "running": qsTr("Running"),
            "planned": qsTr("Planned"),
            "validated": qsTr("Validated"),
            "invalid": qsTr("Invalid"),
            "cancellation_requested": qsTr("Cancelling"),
            "force_stopping": qsTr("Force stopping"),
            "succeeded": qsTr("Succeeded"),
            "failed": qsTr("Failed"),
            "cancelled": qsTr("Cancelled"),
            "force_stopped": qsTr("Force stopped")
        };
        return labels[value] || value;
    }

    boundsBehavior: Flickable.StopAtBounds
    clip: true
    contentHeight: workflowInspectorColumn.implicitHeight
    contentWidth: width
    flickableDirection: Flickable.VerticalFlick
    objectName: "workflowContextInspector"
    pixelAligned: true

    ScrollBar.vertical: ScrollBar {
        policy: ScrollBar.AsNeeded
    }

    ColumnLayout {
        id: workflowInspectorColumn

        spacing: Theme.spacingMedium
        width: parent.width

        Card {
            flat: true
            Layout.fillWidth: true
            subtitle: root.documentActive ? (root.configController.fileDisplay.length > 0
                                             ? root.configController.fileDisplay : qsTr(
                                                   "Save this new configuration before planning.")) :
                                            qsTr("No %1 configuration is active. Historical results remain available below.").arg(
                                                root.workflowTitle)
            title: qsTr("%1 document").arg(root.workflowTitle)

            StatusBadge {
                label: !root.documentActive ? qsTr("Not active") : (root.configController.dirty ? qsTr(
                                                                                                      "Unsaved") :
                                                                                                  qsTr("Saved"))
                objectName: "workflowInspectorDocumentState"
                tone: !root.documentActive ? "neutral" : (root.configController.dirty ? "warning" :
                                                                                        "success")
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
            subtitle: !root.documentActive ? qsTr("Open or create a %1 configuration.").arg(
                                                 root.workflowTitle) : (root.localValid ? qsTr(
                                                                                              "Every structured field is locally complete.") :
                                                                                          root.localIssue)
            title: qsTr("Structured draft")

            StatusBadge {
                label: !root.documentActive ? qsTr("Not available") : (root.transientEditActive
                                                                       ? qsTr("Temporary edit open") :
                                                                         (root.localValid ? qsTr(
                                                                                                "Locally complete") :
                                                                                            qsTr("Needs attention")))
                objectName: "workflowInspectorDraftState"
                tone: !root.documentActive ? "neutral" : (root.transientEditActive ? "warning" : (
                                                                                         root.localValid
                                                                                         ? "success" :
                                                                                           "danger"))
            }

            AppButton {
                Layout.fillWidth: true
                enabled: root.documentActive && !root.localValid
                objectName: "workflowInspectorDraftFocusButton"
                onClicked: root.attentionRequested(root.workflowSection, root.firstInvalidField,
                                                   root.firstInvalidRow)
                text: qsTr("Focus first issue")
                visible: root.documentActive && !root.localValid
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
            subtitle: !root.documentActive ? qsTr(
                                                 "No active %1 configuration is available to validate.").arg(
                                                 root.workflowTitle) : (
                                                 root.configController.workerValidationIssue.length
                                                 > 0 ? root.configController.workerValidationIssue :
                                                       qsTr("Worker validation is informational; exact saved bytes remain authoritative for planning."))
            title: qsTr("Worker validation")

            StatusBadge {
                label: !root.documentActive ? qsTr("Not available") : (
                                                  root.configController.workerValidationState
                                                  === "not_run" ? qsTr("Not run") : root.stateLabel(
                                                                      root.configController.workerValidationState))
                objectName: "workflowInspectorValidationState"
                tone: !root.documentActive ? "neutral" : (
                                                 root.configController.workerValidationState
                                                 === "valid" ? "success" : (
                                                                   root.configController.workerValidationState
                                                                   === "invalid"
                                                                   || root.configController.workerValidationState
                                                                   === "failed" ? "danger" :
                                                                                  "neutral"))
            }

            AppButton {
                Layout.fillWidth: true
                enabled: root.documentActive && root.configController.canValidate
                objectName: "workflowInspectorValidateButton"
                onClicked: root.validateRequested()
                text: root.configController.workerValidationState === "running" ? qsTr(
                                                                                      "Checking draft…") :
                                                                                  qsTr("Check current draft YAML")
                tone: "primary"
                visible: root.documentActive
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
            subtitle: root.workflowController.hasPlan ? (root.workflowController.planCurrent ? qsTr(
                                                                                                   "The plan matches the exact current saved configuration.") :
                                                                                               qsTr("The retained plan is stale relative to current inputs.")) :
                                                        qsTr("No worker-verified plan exists yet.")
            title: qsTr("Plan relation")

            StatusBadge {
                label: root.workflowController.hasPlan ? (root.workflowController.planCurrent ? qsTr(
                                                                                                    "Current") :
                                                                                                qsTr("Stale")) :
                                                         qsTr("Not planned")
                objectName: "workflowInspectorPlanState"
                tone: root.workflowController.planCurrent ? "success" : (
                                                                root.workflowController.hasPlan
                                                                ? "warning" : "neutral")
            }

            Repeater {
                model: root.workflowController.planBlockingReasons

                delegate: AppButton {
                    required property string fieldId
                    required property int index
                    required property string message
                    required property int nestedRow
                    required property string section

                    Layout.fillWidth: true
                    objectName: "workflowInspectorPlanBlocker-" + index
                    onClicked: root.attentionRequested(section, fieldId, nestedRow)
                    text: "• " + message
                    tone: "quiet"
                }
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
            subtitle: root.workflowController.hasResult ? qsTr(
                                                              "The finalized result is retained independently of page and document lifetime.") :
                                                          qsTr("No finalized result exists in this session.")
            title: qsTr("Execution and result")

            Flow {
                Layout.fillWidth: true
                spacing: Theme.spacingSmall

                StatusBadge {
                    label: root.stateLabel(root.workflowController.workflowState)
                    objectName: "workflowInspectorExecutionState"
                    tone: root.workflowController.workflowState === "failed" ? "danger" : (
                                                                                   root.workflowController.operationActive
                                                                                   ? "information" :
                                                                                     "neutral")
                }

                StatusBadge {
                    label: root.workflowController.hasResult ? qsTr("Result %1").arg(
                                                                   root.workflowController.resultRelation) :
                                                               qsTr("No result")
                    objectName: "workflowInspectorResultState"
                    tone: root.workflowController.resultRelation === "current" ? "success" : (
                                                                                     root.workflowController.hasResult
                                                                                     ? "warning" :
                                                                                       "neutral")
                }
            }

            Label {
                Layout.fillWidth: true
                color: root.workflowController.protectedFinalization ? Theme.warning :
                                                                       Theme.textMuted
                font.family: Theme.sansFamily
                font.pixelSize: 11
                objectName: "workflowInspectorPhase"
                text: root.workflowController.protectedFinalization ? qsTr("Finalizing safely") :
                                                                      root.workflowController.workflowPhase
                visible: text.length > 0
                wrapMode: Text.Wrap
            }
        }
    }
}
