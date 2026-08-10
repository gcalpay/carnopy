pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Carnopy

Card {
    id: root

    required property var workflowController
    required property string workflowKind

    signal cancelRequested(string workflow)
    signal executeRequested(string workflow)
    signal forceStopRequested(string workflow)
    signal inspectResultRequested(string workflow)
    signal issueFocusRequested(string section, string field, int row)
    signal planRequested(string workflow)

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

    Layout.fillWidth: true
    objectName: root.workflowKind + "WorkflowRunPanel"
    subtitle: qsTr(
                  "Planning and execution remain bound to exact saved bytes and worker-verified context.")
    title: qsTr("Plan and execute")

    Flow {
        Layout.fillWidth: true
        spacing: Theme.spacingSmall

        StatusBadge {
            label: root.stateLabel(root.workflowController.workflowState)
            objectName: root.workflowKind + "WorkflowState"
            tone: root.workflowController.workflowState === "failed" ? "danger" : (
                                                                           root.workflowController.workflowState
                                                                           === "succeeded"
                                                                           ? "success" : (
                                                                                 root.workflowController.operationActive
                                                                                 ? "information" :
                                                                                   "neutral"))
        }

        StatusBadge {
            label: root.workflowController.hasPlan ? (root.workflowController.planCurrent ? qsTr(
                                                                                                "Plan current") :
                                                                                            qsTr("Plan stale")) :
                                                     qsTr("No plan")
            objectName: root.workflowKind + "PlanRelation"
            tone: root.workflowController.planCurrent ? "success" : (
                                                            root.workflowController.hasPlan
                                                            ? "warning" : "neutral")
        }

        StatusBadge {
            label: root.workflowController.hasResult ? qsTr("Result %1").arg(
                                                           root.workflowController.resultRelation) :
                                                       qsTr("No result")
            objectName: root.workflowKind + "ResultRelation"
            tone: root.workflowController.resultRelation === "current" ? "success" : (
                                                                             root.workflowController.hasResult
                                                                             ? "warning" :
                                                                               "neutral")
        }
    }

    Label {
        Accessible.name: text
        Layout.fillWidth: true
        color: root.workflowController.protectedFinalization ? Theme.warning : Theme.textMuted
        font.family: Theme.sansFamily
        font.pixelSize: 12
        font.weight: root.workflowController.protectedFinalization ? Font.DemiBold : Font.Normal
        objectName: root.workflowKind + "WorkflowPhase"
        text: root.workflowController.protectedFinalization ? qsTr(
                                                                  "Finalizing safely — cancellation and force stop are disabled.") :
                                                              (root.workflowController.workflowPhase.length
                                                               > 0 ? qsTr("Phase: %1").arg(
                                                                         root.workflowController.workflowPhase) :
                                                                     qsTr("No worker phase is active."))
        wrapMode: Text.Wrap
    }

    ProgressBar {
        Accessible.name: qsTr("Workflow progress")
        Accessible.description: root.workflowController.progressTotal > 0 ? qsTr("%1 of %2").arg(
                                                                                root.workflowController.progressCompleted).arg(
                                                                                root.workflowController.progressTotal) :
                                                                            qsTr("In progress")
        Layout.fillWidth: true
        from: 0
        indeterminate: root.workflowController.operationActive
                       && root.workflowController.progressTotal <= 0
        objectName: root.workflowKind + "WorkflowProgress"
        to: Math.max(1, root.workflowController.progressTotal)
        value: Math.min(to, root.workflowController.progressCompleted)
        visible: root.workflowController.operationActive
    }

    Label {
        Layout.fillWidth: true
        color: Theme.textMuted
        font.family: Theme.monoFamily
        font.pixelSize: 10
        objectName: root.workflowKind + "PlanIdentity"
        text: root.workflowController.planId.length > 0 ? qsTr("Plan %1").arg(
                                                              root.workflowController.planId) : ""
        visible: text.length > 0
        wrapMode: Text.WrapAnywhere
    }

    ColumnLayout {
        Layout.fillWidth: true
        spacing: Theme.spacingTiny
        visible: root.workflowController.planBlockingReasons.count > 0

        Label {
            Layout.fillWidth: true
            color: Theme.warning
            font.family: Theme.sansFamily
            font.pixelSize: 12
            font.weight: Font.Medium
            text: qsTr("Planning is unavailable:")
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
                objectName: root.workflowKind + "PlanBlocker-" + index
                onClicked: root.issueFocusRequested(section, fieldId, nestedRow)
                text: "• " + message
                tone: "quiet"
            }
        }
    }

    ColumnLayout {
        Layout.fillWidth: true
        spacing: Theme.spacingTiny
        visible: root.workflowController.hasPlan
                 && root.workflowController.executionBlockingReasons.count > 0

        Label {
            Layout.fillWidth: true
            color: Theme.warning
            font.family: Theme.sansFamily
            font.pixelSize: 12
            font.weight: Font.Medium
            text: qsTr("Execution is unavailable:")
        }

        Repeater {
            model: root.workflowController.executionBlockingReasons

            delegate: AppButton {
                required property string fieldId
                required property int index
                required property string message
                required property int nestedRow
                required property string section

                Layout.fillWidth: true
                objectName: root.workflowKind + "ExecutionBlocker-" + index
                onClicked: root.issueFocusRequested(section, fieldId, nestedRow)
                text: "• " + message
                tone: "quiet"
            }
        }
    }

    ValidationIssue {
        Layout.fillWidth: true
        field: root.workflowController.failureCode
        issue: root.workflowController.failureMessage
        objectName: root.workflowKind + "WorkflowFailure"
    }

    Label {
        Layout.fillWidth: true
        color: Theme.warning
        font.family: Theme.sansFamily
        font.pixelSize: 11
        text: root.workflowController.activityPersistenceIssue
        visible: text.length > 0
        wrapMode: Text.Wrap
    }

    Flow {
        Layout.fillWidth: true
        spacing: Theme.spacingSmall

        AppButton {
            Accessible.description: qsTr(
                                        "Create a worker-verified plan from the exact saved configuration")
            enabled: root.workflowController.canPlan
            objectName: root.workflowKind + "PlanButton"
            onClicked: root.planRequested(root.workflowKind)
            text: qsTr("Plan")
            tone: "primary"
        }

        AppButton {
            Accessible.description: qsTr("Execute the current worker-verified plan")
            enabled: root.workflowController.canExecute
            objectName: root.workflowKind + "ExecuteButton"
            onClicked: root.executeRequested(root.workflowKind)
            text: qsTr("Execute")
            tone: "primary"
        }

        AppButton {
            enabled: root.workflowController.cancellationAvailable
            objectName: root.workflowKind + "CancelButton"
            onClicked: root.cancelRequested(root.workflowKind)
            text: qsTr("Cancel")
            visible: root.workflowController.operationActive
        }

        AppButton {
            enabled: root.workflowController.forceStopAvailable
            objectName: root.workflowKind + "ForceStopButton"
            onClicked: root.forceStopRequested(root.workflowKind)
            text: qsTr("Force stop")
            tone: "danger"
            visible: root.workflowController.workflowState === "cancellation_requested"
                     || root.workflowController.workflowState === "force_stopping"
        }

        AppButton {
            enabled: root.workflowController.hasResult
                     && root.workflowController.resultOutputDirectory.length > 0
            objectName: root.workflowKind + "InspectResultButton"
            onClicked: root.inspectResultRequested(root.workflowKind)
            text: qsTr("Inspect finalized output")
        }
    }
}
