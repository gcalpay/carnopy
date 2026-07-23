pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Carnopy

Flickable {
    id: root

    required property var executionController

    function abbreviatedHash(value) {
        const text = String(value);
        return text.length > 12 ? text.slice(0, 12) + "…" : text;
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
            "invalid": qsTr("Invalid"),
            "failed": qsTr("Failed"),
            "cancelled": qsTr("Cancelled"),
            "force_stopped": qsTr("Force stopped")
        };
        return labels[state] || state;
    }

    boundsBehavior: Flickable.StopAtBounds
    clip: true
    contentHeight: runInspectorColumn.implicitHeight
    contentWidth: width
    flickableDirection: Flickable.VerticalFlick
    objectName: "runContextInspector"
    pixelAligned: true

    ScrollBar.vertical: ScrollBar {
        policy: ScrollBar.AsNeeded
    }

    ColumnLayout {
        id: runInspectorColumn

        spacing: Theme.spacingMedium
        width: parent.width

        Card {
            flat: true
            Layout.fillWidth: true
            subtitle: root.executionController.snapshotAvailable
                      ? root.executionController.snapshotPath :
                        root.executionController.snapshotIssue
            title: qsTr("Saved configuration")

            Label {
                Accessible.description: root.executionController.snapshotSha256
                Layout.fillWidth: true
                color: Theme.textMuted
                elide: Text.ElideRight
                font.family: Theme.monoFamily
                font.pixelSize: 10
                objectName: "runInspectorSnapshotHash"
                text: root.abbreviatedHash(root.executionController.snapshotSha256)
                visible: root.executionController.snapshotAvailable
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
            title: qsTr("Worker request")

            RowLayout {
                Layout.fillWidth: true

                Label {
                    Layout.fillWidth: true
                    color: Theme.textMuted
                    font.family: Theme.sansFamily
                    font.pixelSize: 12
                    text: qsTr("State")
                }

                Label {
                    color: Theme.text
                    font.family: Theme.sansFamily
                    font.pixelSize: 12
                    font.weight: Font.Medium
                    objectName: "runInspectorState"
                    text: root.stateLabel(root.executionController.state)
                }
            }

            RowLayout {
                Layout.fillWidth: true
                visible: root.executionController.phase.length > 0

                Label {
                    Layout.fillWidth: true
                    color: Theme.textMuted
                    font.family: Theme.sansFamily
                    font.pixelSize: 12
                    text: qsTr("Phase")
                }

                Label {
                    color: Theme.text
                    font.family: Theme.sansFamily
                    font.pixelSize: 12
                    objectName: "runInspectorPhase"
                    text: root.executionController.phase
                }
            }

            Label {
                Layout.fillWidth: true
                color: Theme.textMuted
                font.family: Theme.monoFamily
                font.pixelSize: 10
                text: qsTr("%1 / %2 rows").arg(root.executionController.completedRows).arg(
                          root.executionController.totalRows)
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
            subtitle: root.executionController.state !== "succeeded" ? qsTr(
                                                                           "A completed result has not been recorded in this session.") :
                                                                       (root.executionController.resultMatchesCurrentSavedBaseline
                                                                        ? (root.executionController.resultRelationIssue.length
                                                                           > 0 ? root.executionController.resultRelationIssue :
                                                                                 qsTr("Result identity matches the current saved configuration.")) :
                                                                          root.executionController.resultRelationIssue)
            title: qsTr("Result relation")

            StatusBadge {
                label: root.executionController.state !== "succeeded" ? qsTr("Not available") : (
                                                                            root.executionController.resultMatchesCurrentSavedBaseline
                                                                            ? qsTr("Current saved baseline") :
                                                                              qsTr("Historical"))
                objectName: "runInspectorResultRelation"
                tone: root.executionController.state !== "succeeded" ? "neutral" : (
                                                                           root.executionController.resultMatchesCurrentSavedBaseline
                                                                           ? "success" : "warning")
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
            subtitle: root.executionController.activityPersistenceIssue.length > 0
                      ? root.executionController.activityPersistenceIssue : (
                            root.executionController.activityRecordAvailable ? qsTr(
                                                                                   "A readable schema-version-1 Run activity record exists.") :
                                                                               qsTr("No Run activity record exists for the current session."))
            title: qsTr("Run activity")

            StatusBadge {
                label: root.executionController.activityPersistenceIssue.length > 0 ? qsTr(
                                                                                          "Persistence degraded") :
                                                                                      (root.executionController.activityRecordAvailable
                                                                                       ? qsTr("Recorded") :
                                                                                         qsTr("Not recorded"))
                objectName: "runInspectorActivityState"
                tone: root.executionController.activityPersistenceIssue.length > 0 ? "warning" : (
                                                                                         root.executionController.activityRecordAvailable
                                                                                         ? "success" :
                                                                                           "neutral")
            }
        }
    }
}
