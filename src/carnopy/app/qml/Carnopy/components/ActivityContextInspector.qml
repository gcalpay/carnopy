pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Carnopy

Flickable {
    id: root

    required property var activityController

    boundsBehavior: Flickable.StopAtBounds
    clip: true
    contentHeight: activityInspectorColumn.implicitHeight
    contentWidth: width
    flickableDirection: Flickable.VerticalFlick
    objectName: "activityContextInspector"

    ScrollBar.vertical: ScrollBar {
        policy: ScrollBar.AsNeeded
    }

    ColumnLayout {
        id: activityInspectorColumn

        spacing: Theme.spacingMedium
        width: parent.width

        Card {
            Layout.fillWidth: true
            flat: true
            subtitle: root.activityController.recordsModel.count === 0 ? qsTr(
                                                                             "No private Run records are stored in this workspace.") :
                                                                         qsTr("Select a record to inspect its typed summary and diagnostic envelope.")
            title: qsTr("Run activity")

            StatusBadge {
                label: qsTr("%1 record(s)").arg(root.activityController.recordsModel.count)
                tone: root.activityController.recordsModel.count > 0 ? "information" : "neutral"
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            color: Theme.divider
        }

        Card {
            Layout.fillWidth: true
            flat: true
            subtitle: root.activityController.selectedRecordId.length > 0
                      ? root.activityController.selectedRecordId : qsTr("No record selected")
            title: qsTr("Selected record")

            StatusBadge {
                label: root.activityController.selectedRecordState.length > 0
                       ? root.activityController.selectedRecordState : qsTr("Not selected")
                tone: root.activityController.selectedRecordState === "completed" ? "success" : (
                                                                                        root.activityController.selectedRecordState
                                                                                        === "failed"
                                                                                        || root.activityController.selectedRecordState
                                                                                        === "force_stopped"
                                                                                        ? "danger" :
                                                                                          "neutral")
            }

            Label {
                Layout.fillWidth: true
                color: Theme.textMuted
                font.family: Theme.sansFamily
                font.pixelSize: 11
                text: root.activityController.canInspectRun ? qsTr(
                                                                  "The recorded output directory can be submitted explicitly to Inspect.") :
                                                              qsTr("Inspect is unavailable for this record.")
                wrapMode: Text.Wrap
            }

            Label {
                Layout.fillWidth: true
                color: Theme.textMuted
                font.family: Theme.sansFamily
                font.pixelSize: 11
                text: root.activityController.canViewPlots ? qsTr(
                                                                 "Configured plot evidence is recorded for this generation.") :
                                                             qsTr("No configured plot evidence is available for this record.")
                wrapMode: Text.Wrap
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            color: Theme.divider
        }

        Card {
            Layout.fillWidth: true
            flat: true
            subtitle: root.activityController.recoveryIssue.length > 0
                      ? root.activityController.recoveryIssue : qsTr(
                            "Removal is explicit, rescanned, and identity checked.")
            title: qsTr("Staging recovery")

            StatusBadge {
                label: root.activityController.recoveryState === "ready" ? qsTr(
                                                                               "%1 candidate(s)").arg(
                                                                               root.activityController.recoveryCandidatesModel.count) :
                                                                           root.activityController.recoveryState
                tone: root.activityController.recoveryState === "failed" ? "danger" : "neutral"
            }
        }
    }
}
