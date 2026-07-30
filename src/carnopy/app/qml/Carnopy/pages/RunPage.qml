pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Carnopy

Item {
    id: root

    required property var executionController
    property int expectedColumns: 1
    property bool inspectRunAvailable: false
    property bool configuredPlotsAvailable: false

    readonly property bool requestActive: {
        const state = executionController.state;
        return state === "starting" || state === "running" || state === "cancellation_requested"
        || state === "force_stopping";
    }
    readonly property bool generationSucceeded: executionController.operation === "generate"
                                                && executionController.state === "succeeded"
                                                && executionController.resultOutputDirectory.length
                                                > 0

    signal validateRequested
    signal generateRequested
    signal cancelRequested
    signal forceStopRequested
    signal inspectRunRequested
    signal viewPlotsRequested

    function abbreviatedHash(value) {
        const text = String(value);
        return text.length > 16 ? text.slice(0, 16) + "…" : text;
    }

    function stateLabel(state) {
        const labels = {
            "unavailable": qsTr("Unavailable"),
            "ready": qsTr("Ready"),
            "starting": qsTr("Starting"),
            "running": qsTr("Running"),
            "cancellation_requested": qsTr("Cancelling"),
            "force_stopping": qsTr("Force stopping"),
            "succeeded": qsTr("Succeeded"),
            "invalid": qsTr("Invalid configuration"),
            "failed": qsTr("Failed"),
            "cancelled": qsTr("Cancelled"),
            "force_stopped": qsTr("Force stopped")
        };
        return labels[state] || state;
    }

    function stateTone(state) {
        if (state === "succeeded")
            return "success";
        if (state === "invalid" || state === "failed" || state === "force_stopped")
            return "danger";
        if (state === "cancelled" || state === "cancellation_requested")
            return "warning";
        if (state === "starting" || state === "running" || state === "force_stopping")
            return "information";
        return "neutral";
    }

    function formatCount(value) {
        return Number(value).toLocaleString(Qt.locale("en_US"), "f", 0);
    }

    Flickable {
        anchors.fill: parent
        boundsBehavior: Flickable.StopAtBounds
        clip: true
        contentHeight: pageColumn.implicitHeight + 48
        contentWidth: width
        flickableDirection: Flickable.VerticalFlick
        objectName: "runPageFlickable"
        pixelAligned: true

        ScrollBar.vertical: ScrollBar {
            policy: ScrollBar.AsNeeded
        }

        ColumnLayout {
            id: pageColumn

            anchors.left: parent.left
            anchors.leftMargin: 24
            anchors.right: parent.right
            anchors.rightMargin: 24
            anchors.top: parent.top
            anchors.topMargin: 22
            spacing: Theme.spacingMedium

            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.spacingMedium

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 3

                    Label {
                        Layout.fillWidth: true
                        color: Theme.text
                        font.family: Theme.sansFamily
                        font.pixelSize: 23
                        font.weight: Font.DemiBold
                        text: qsTr("Run dataset")
                    }

                    Label {
                        Layout.fillWidth: true
                        color: Theme.textMuted
                        font.family: Theme.sansFamily
                        font.pixelSize: 12
                        text: qsTr(
                                  "Validate or generate from the exact clean configuration saved in this workspace.")
                        wrapMode: Text.Wrap
                    }
                }

                StatusBadge {
                    label: root.stateLabel(root.executionController.state)
                    objectName: "runStateBadge"
                    tone: root.stateTone(root.executionController.state)
                }
            }

            BlockingBanner {
                Layout.fillWidth: true
                message: root.executionController.snapshotIssue
                objectName: "runSnapshotBlocker"
                title: qsTr("Saved configuration required")
                visible: !root.executionController.snapshotAvailable
            }

            ResponsiveCardGrid {
                Layout.fillWidth: true
                Layout.preferredHeight: implicitHeight
                maximumColumns: Math.min(2, root.expectedColumns)
                minimumCardWidth: 320
                objectName: "runWorkflowGrid"
                uniformHeights: false

                Card {
                    Layout.fillHeight: true
                    Layout.fillWidth: true
                    meta: root.executionController.snapshotAvailable ? qsTr("Exact saved bytes") :
                                                                       qsTr("Unavailable")
                    metaColor: root.executionController.snapshotAvailable ? Theme.success :
                                                                            Theme.textMuted
                    objectName: "runSavedConfigurationCard"
                    sectionNumber: "1"
                    subtitle: qsTr(
                                  "Run never consumes unsaved editor state or a cached validation result.")
                    title: qsTr("Saved configuration")

                    Label {
                        Layout.fillWidth: true
                        color: Theme.text
                        elide: Text.ElideMiddle
                        font.family: Theme.monoFamily
                        font.pixelSize: 11
                        objectName: "runSnapshotPath"
                        text: root.executionController.snapshotAvailable
                              ? root.executionController.snapshotPath : qsTr(
                                    "No executable snapshot")
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        visible: root.executionController.snapshotAvailable

                        Label {
                            color: Theme.textMuted
                            font.family: Theme.sansFamily
                            font.pixelSize: 11
                            text: qsTr("SHA-256")
                        }

                        Label {
                            Accessible.description: root.executionController.snapshotSha256
                            Layout.fillWidth: true
                            color: Theme.text
                            elide: Text.ElideRight
                            font.family: Theme.monoFamily
                            font.pixelSize: 11
                            horizontalAlignment: Text.AlignRight
                            objectName: "runSnapshotHash"
                            text: root.abbreviatedHash(root.executionController.snapshotSha256)
                        }
                    }
                }

                Card {
                    Layout.fillHeight: true
                    Layout.fillWidth: true
                    meta: root.requestActive ? qsTr("Worker active") : qsTr("Awaiting request")
                    metaColor: root.requestActive ? Theme.information : Theme.textMuted
                    objectName: "runOperationCard"
                    sectionNumber: "2"
                    subtitle: qsTr(
                                  "The saved-config check is optional. Generate always performs its own fresh worker validation before backend initialization.")
                    title: qsTr("Choose operation")

                    AppButton {
                        Accessible.description: qsTr(
                                                    "Validate the exact saved YAML without generating a dataset")
                        Layout.fillWidth: true
                        enabled: root.executionController.canValidate
                        objectName: "runValidateButton"
                        onClicked: root.validateRequested()
                        text: qsTr("Check saved configuration")
                    }

                    AppButton {
                        Accessible.description: qsTr(
                                                    "Freshly validate the exact saved YAML and generate its dataset")
                        Layout.fillWidth: true
                        enabled: root.executionController.canGenerate
                        iconName: "play"
                        objectName: "runGenerateButton"
                        onClicked: root.generateRequested()
                        text: qsTr("Generate dataset")
                        tone: "primary"
                    }
                }

                Card {
                    Layout.fillHeight: true
                    Layout.fillWidth: true
                    meta: root.executionController.phase.length > 0
                          ? root.executionController.phase : root.stateLabel(
                                root.executionController.state)
                    metaColor: root.requestActive ? Theme.information : Theme.textMuted
                    objectName: "runProgressCard"
                    sectionNumber: "3"
                    subtitle: qsTr(
                                  "Progress is live. Cooperative cancellation appears only at a worker-declared safe phase.")
                    title: qsTr("Worker progress")

                    ProgressBar {
                        Accessible.name: qsTr("Dataset generation progress")
                        Layout.fillWidth: true
                        from: 0
                        indeterminate: root.requestActive && root.executionController.totalRows <= 0
                        objectName: "runProgressBar"
                        to: Math.max(1, root.executionController.totalRows)
                        value: Math.min(to, root.executionController.completedRows)
                    }

                    Label {
                        Layout.fillWidth: true
                        color: Theme.textMuted
                        font.family: Theme.monoFamily
                        font.pixelSize: 11
                        horizontalAlignment: Text.AlignRight
                        objectName: "runProgressLabel"
                        text: root.formatCount(root.executionController.completedRows) + " / "
                              + root.formatCount(root.executionController.totalRows) + qsTr(" rows")
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        visible: root.requestActive

                        AppButton {
                            Layout.fillWidth: true
                            enabled: root.executionController.canCancel
                            objectName: "runCancelButton"
                            onClicked: root.cancelRequested()
                            text: root.executionController.state === "cancellation_requested" ? qsTr(
                                                                                                    "Cancellation requested") :
                                                                                                qsTr("Cancel safely")
                        }

                        AppButton {
                            Layout.fillWidth: true
                            enabled: root.executionController.canForceStop
                            foregroundColor: Theme.danger
                            objectName: "runForceStopButton"
                            onClicked: root.forceStopRequested()
                            text: qsTr("Force stop")
                            visible: root.executionController.canForceStop
                        }
                    }
                }

                Card {
                    Layout.fillHeight: true
                    Layout.fillWidth: true
                    meta: root.executionController.state === "succeeded" ? qsTr("Worker complete") :
                                                                           ""
                    metaColor: Theme.success
                    objectName: "runResultCard"
                    sectionNumber: "4"
                    subtitle: root.executionController.state === "succeeded" ? qsTr(
                                                                                   "The result remains bound to the saved configuration identity captured at request start.") :
                                                                               qsTr("Validation or generation results appear here without automatic navigation.")
                    title: qsTr("Result")

                    Label {
                        Layout.fillWidth: true
                        color: Theme.text
                        font.family: Theme.sansFamily
                        font.pixelSize: 12
                        objectName: "runResultSummary"
                        text: {
                            if (root.executionController.state === "succeeded"
                                && root.executionController.operation === "validate")
                            return qsTr("Validation accepted · %1 · %2 projected rows").arg(
                                root.executionController.resultMode).arg(root.formatCount(
                                                                             root.executionController.resultProjectedRows));
                            if (root.generationSucceeded)
                            return qsTr("%1 · %2 rows · %3 valid · %4 invalid").arg(
                                root.executionController.resultRunStatus).arg(root.formatCount(
                                                                                  root.executionController.resultRowCount)).arg(
                                root.formatCount(root.executionController.resultValidRowCount)).arg(
                                root.formatCount(root.executionController.resultInvalidRowCount));
                            if (root.executionController.state === "invalid"
                                || root.executionController.state === "failed"
                                || root.executionController.state === "cancelled"
                                || root.executionController.state === "force_stopped")
                            return root.executionController.failureCode + ": "
                            + root.executionController.failureMessage;
                            return qsTr("No completed request yet.");
                        }
                        wrapMode: Text.Wrap
                    }

                    Label {
                        Layout.fillWidth: true
                        color: Theme.textMuted
                        elide: Text.ElideMiddle
                        font.family: Theme.monoFamily
                        font.pixelSize: 10
                        objectName: "runResultOutputPath"
                        text: root.executionController.resultOutputDirectory
                        visible: root.generationSucceeded
                    }

                    StatusBadge {
                        label: root.executionController.resultMatchesCurrentSavedBaseline ? qsTr(
                                                                                                "Current saved baseline") :
                                                                                            qsTr("Historical result")
                        objectName: "runResultRelationBadge"
                        tone: root.executionController.resultMatchesCurrentSavedBaseline
                              ? "success" : "warning"
                        visible: root.executionController.state === "succeeded"
                    }

                    Label {
                        Layout.fillWidth: true
                        color: Theme.textMuted
                        font.family: Theme.sansFamily
                        font.pixelSize: 11
                        objectName: "runResultRelationIssue"
                        text: root.executionController.resultRelationIssue
                        visible: text.length > 0
                        wrapMode: Text.Wrap
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        visible: root.generationSucceeded

                        AppButton {
                            Accessible.description: root.inspectRunAvailable ? qsTr(
                                                                                   "Inspect this exact generated output") :
                                                                               qsTr("Available after a successful generation with a recorded output directory")
                            Layout.fillWidth: true
                            enabled: root.inspectRunAvailable
                            objectName: "runInspectButton"
                            onClicked: root.inspectRunRequested()
                            text: qsTr("Inspect Run")
                        }

                        AppButton {
                            Accessible.description: root.configuredPlotsAvailable ? qsTr(
                                                                                        "Open configured plots for this exact generation request") :
                                                                                    qsTr("Available after a successful generation with a persisted request identity")
                            Layout.fillWidth: true
                            enabled: root.configuredPlotsAvailable
                            objectName: "runViewPlotsButton"
                            onClicked: root.viewPlotsRequested()
                            text: qsTr("View Plots")
                        }
                    }
                }
            }

            Label {
                Layout.fillWidth: true
                color: Theme.warning
                font.family: Theme.sansFamily
                font.pixelSize: 11
                objectName: "runActivityPersistenceIssue"
                text: root.executionController.activityPersistenceIssue
                visible: text.length > 0
                wrapMode: Text.Wrap
            }
        }
    }
}
