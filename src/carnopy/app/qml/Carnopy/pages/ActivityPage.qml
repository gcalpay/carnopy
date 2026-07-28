pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Carnopy

Item {
    id: root

    required property var activityController

    signal inspectRunRequested
    signal removeRecordRequested
    signal removeRecoveryRequested
    signal viewPlotsRequested

    property bool diagnosticExpanded: false

    function summaryValue(name, fallback) {
        const summary = root.activityController.selectedRecordSummary;
        if (summary === null || summary === undefined || summary[name] === undefined
                || summary[name] === null || String(summary[name]).length === 0)
            return fallback;
        return String(summary[name]);
    }

    function recoveryConfirmationText() {
        const paths = root.activityController.selectedRecoveryPaths;
        return qsTr("Permanently remove %1 recognized staging director%2?\n\n%3").arg(
                    paths.length).arg(paths.length === 1 ? "y" : "ies").arg(
                    root.activityController.selectedRecoveryPathsText);
    }

    TabBar {
        id: activityTabs

        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        objectName: "activityTabs"

        TabButton {
            objectName: "runActivityTab"
            text: qsTr("Run activity")
        }

        TabButton {
            objectName: "stagingRecoveryTab"
            text: qsTr("Staging Recovery")
        }
    }

    StackLayout {
        anchors.bottom: parent.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: activityTabs.bottom
        currentIndex: activityTabs.currentIndex

        Flickable {
            boundsBehavior: Flickable.StopAtBounds
            clip: true
            contentHeight: activityColumn.implicitHeight + 48
            contentWidth: width
            flickableDirection: Flickable.VerticalFlick
            objectName: "activityPageFlickable"

            ScrollBar.vertical: ScrollBar {
                policy: ScrollBar.AsNeeded
            }

            ColumnLayout {
                id: activityColumn

                anchors.left: parent.left
                anchors.leftMargin: 24
                anchors.right: parent.right
                anchors.rightMargin: 24
                anchors.top: parent.top
                anchors.topMargin: 22
                spacing: Theme.spacingMedium

                RowLayout {
                    Layout.fillWidth: true

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 3

                        Label {
                            Layout.fillWidth: true
                            color: Theme.text
                            font.family: Theme.sansFamily
                            font.pixelSize: 23
                            font.weight: Font.DemiBold
                            text: qsTr("Activity")
                        }

                        Label {
                            Layout.fillWidth: true
                            color: Theme.textMuted
                            font.family: Theme.sansFamily
                            font.pixelSize: 12
                            text: qsTr(
                                      "Review private Run records without treating them as ownership of generated data or figures.")
                            wrapMode: Text.Wrap
                        }
                    }

                    AppButton {
                        iconName: "rotate-ccw"
                        objectName: "activityRefreshButton"
                        onClicked: root.activityController.refreshRecords()
                        text: qsTr("Refresh")
                    }
                }

                GridLayout {
                    Layout.fillWidth: true
                    columnSpacing: Theme.spacingMedium
                    columns: root.width >= 920 ? 2 : 1
                    rowSpacing: Theme.spacingMedium

                    Card {
                        Layout.fillWidth: true
                        Layout.minimumWidth: 300
                        subtitle: qsTr(
                                      "Newest persisted records appear first. Running records without a matching live request are shown as interrupted.")
                        title: qsTr("Run records")

                        ListView {
                            Layout.fillWidth: true
                            Layout.preferredHeight: Math.max(120, Math.min(360, count * 52))
                            boundsBehavior: Flickable.StopAtBounds
                            clip: true
                            model: root.activityController.recordsModel
                            objectName: "activityRecordsList"
                            spacing: Theme.spacingTiny

                            ScrollBar.vertical: ScrollBar {
                                policy: ScrollBar.AsNeeded
                            }

                            delegate: AppButton {
                                required property string createdAtUtc
                                required property string issue
                                required property string operation
                                required property string recordId
                                required property bool readable
                                required property string stateLabel

                                Accessible.description: issue.length > 0 ? issue : qsTr(
                                                                               "%1 request created %2").arg(
                                                                               operation).arg(
                                                                               createdAtUtc)
                                objectName: "activityRecord-" + recordId
                                onClicked: root.activityController.selectRecord(recordId)
                                text: readable ? stateLabel + " · " + operation + " · "
                                                 + createdAtUtc : qsTr("Unreadable · ") + recordId
                                tone: root.activityController.selectedRecordId === recordId
                                      ? "primary" : "secondary"
                                width: ListView.view.width
                            }
                        }

                        Label {
                            Layout.fillWidth: true
                            color: Theme.textMuted
                            font.family: Theme.sansFamily
                            font.pixelSize: 11
                            text: qsTr("No Run activity has been recorded in this workspace.")
                            visible: root.activityController.recordsModel.count === 0
                            wrapMode: Text.Wrap
                        }
                    }

                    Card {
                        Layout.fillWidth: true
                        Layout.minimumWidth: 300
                        meta: root.activityController.selectedRecordState.length > 0
                              ? root.activityController.selectedRecordState : qsTr("No selection")
                        metaColor: root.activityController.selectedRecordState === "completed"
                                   ? Theme.success : (root.activityController.selectedRecordState
                                                      === "failed" ? Theme.danger : Theme.textMuted)
                        subtitle: root.activityController.selectedRecordId.length > 0
                                  ? root.activityController.selectedRecordId : qsTr(
                                        "Select a record to review its typed summary and exact actions.")
                        title: qsTr("Selected record")

                        Label {
                            Layout.fillWidth: true
                            color: Theme.textMuted
                            font.family: Theme.sansFamily
                            font.pixelSize: 11
                            text: qsTr("Configuration: %1").arg(root.summaryValue(
                                                                    "configurationPath", qsTr(
                                                                        "Unavailable")))
                            wrapMode: Text.WrapAnywhere
                        }

                        Label {
                            Accessible.description: root.summaryValue("configurationSha256", "")
                            Layout.fillWidth: true
                            color: Theme.textMuted
                            elide: Text.ElideMiddle
                            font.family: Theme.monoFamily
                            font.pixelSize: 10
                            text: qsTr("SHA-256: %1").arg(root.summaryValue("configurationSha256",
                                                                            qsTr("Unavailable")))
                        }

                        Label {
                            Layout.fillWidth: true
                            color: Theme.text
                            font.family: Theme.sansFamily
                            font.pixelSize: 11
                            text: qsTr("Rows: %1 total · %2 valid · %3 invalid").arg(
                                      root.summaryValue("rowCount", "0")).arg(root.summaryValue(
                                                                                  "validRowCount",
                                                                                  "0")).arg(
                                      root.summaryValue("invalidRowCount", "0"))
                            visible: root.activityController.selectedRecordId.length > 0
                            wrapMode: Text.Wrap
                        }

                        Label {
                            Layout.fillWidth: true
                            color: Theme.textMuted
                            font.family: Theme.monoFamily
                            font.pixelSize: 10
                            text: root.summaryValue("outputDirectory", "")
                            visible: text.length > 0
                            wrapMode: Text.WrapAnywhere
                        }

                        RowLayout {
                            Layout.fillWidth: true

                            AppButton {
                                enabled: root.activityController.canInspectRun
                                iconName: "search"
                                objectName: "activityInspectRunButton"
                                onClicked: root.inspectRunRequested()
                                text: qsTr("Inspect Run")
                            }

                            AppButton {
                                enabled: root.activityController.canViewPlots
                                iconName: "chart-spline"
                                objectName: "activityViewPlotsButton"
                                onClicked: root.viewPlotsRequested()
                                text: qsTr("View Plots")
                            }
                        }

                        AppButton {
                            Layout.fillWidth: true
                            enabled: root.activityController.canRemoveRecord
                            objectName: "activityRemoveRecordButton"
                            onClicked: removeRecordDialog.open()
                            text: qsTr("Remove private record…")
                            tone: "danger"
                        }
                    }
                }

                Card {
                    Layout.fillWidth: true
                    subtitle: qsTr(
                                  "This is the persisted diagnostic envelope. It is display-only and is not lifecycle authority.")
                    title: qsTr("Diagnostic envelope")

                    AppButton {
                        enabled: root.activityController.selectedDiagnosticText.length > 0
                        objectName: "activityDiagnosticToggle"
                        onClicked: root.diagnosticExpanded = !root.diagnosticExpanded
                        text: root.diagnosticExpanded ? qsTr("Hide diagnostic details") : qsTr(
                                                            "Show diagnostic details")
                    }

                    TextArea {
                        Accessible.name: qsTr("Selected Run diagnostic envelope")
                        Layout.fillWidth: true
                        Layout.preferredHeight: root.diagnosticExpanded ? 260 : 0
                        color: Theme.text
                        font.family: Theme.monoFamily
                        font.pixelSize: 10
                        objectName: "activityDiagnosticText"
                        readOnly: true
                        text: root.activityController.selectedDiagnosticText
                        visible: root.diagnosticExpanded
                        wrapMode: TextEdit.NoWrap

                        background: Rectangle {
                            border.color: Theme.border
                            border.width: 1
                            color: Theme.canvas
                            radius: Theme.radiusSmall
                        }
                    }
                }
            }
        }

        Flickable {
            boundsBehavior: Flickable.StopAtBounds
            clip: true
            contentHeight: recoveryColumn.implicitHeight + 48
            contentWidth: width
            flickableDirection: Flickable.VerticalFlick
            objectName: "recoveryPageFlickable"

            ScrollBar.vertical: ScrollBar {
                policy: ScrollBar.AsNeeded
            }

            ColumnLayout {
                id: recoveryColumn

                anchors.left: parent.left
                anchors.leftMargin: 24
                anchors.right: parent.right
                anchors.rightMargin: 24
                anchors.top: parent.top
                anchors.topMargin: 22
                spacing: Theme.spacingMedium

                RowLayout {
                    Layout.fillWidth: true

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 3

                        Label {
                            Layout.fillWidth: true
                            color: Theme.text
                            font.family: Theme.sansFamily
                            font.pixelSize: 23
                            font.weight: Font.DemiBold
                            text: qsTr("Staging Recovery")
                        }

                        Label {
                            Layout.fillWidth: true
                            color: Theme.textMuted
                            font.family: Theme.sansFamily
                            font.pixelSize: 12
                            text: qsTr(
                                      "Only recognized direct staging children are listed. Selection never removes immutable runs or arbitrary folders.")
                            wrapMode: Text.Wrap
                        }
                    }

                    AppButton {
                        iconName: "rotate-ccw"
                        objectName: "recoveryRefreshButton"
                        onClicked: root.activityController.refreshRecovery()
                        text: qsTr("Rescan")
                    }
                }

                Card {
                    Layout.fillWidth: true
                    meta: qsTr("%1 selected").arg(root.activityController.selectedRecoveryCount)
                    metaColor: root.activityController.selectedRecoveryCount > 0 ? Theme.warning :
                                                                                   Theme.textMuted
                    subtitle: qsTr(
                                  "Carnopy rescans each selected path and verifies containment, type, device, inode, and absence of symbolic links immediately before removal.")
                    title: qsTr("Recognized staging candidates")

                    ListView {
                        Layout.fillWidth: true
                        Layout.preferredHeight: Math.max(120, Math.min(420, count * 62))
                        boundsBehavior: Flickable.StopAtBounds
                        clip: true
                        model: root.activityController.recoveryCandidatesModel
                        objectName: "recoveryCandidatesList"
                        spacing: Theme.spacingTiny

                        ScrollBar.vertical: ScrollBar {
                            policy: ScrollBar.AsNeeded
                        }

                        delegate: CheckBox {
                            required property real ageSeconds
                            required property int index
                            required property string issue
                            required property string name
                            required property string path
                            required property bool removable
                            required property bool selected

                            Accessible.description: issue.length > 0 ? issue : path
                            checked: selected
                            enabled: removable
                            objectName: "recoveryCandidate-" + index
                            onToggled: root.activityController.setRecoverySelected(index, checked)
                            text: qsTr("%1 · %2 minutes old").arg(name).arg((ageSeconds
                                                                             / 60).toFixed(1))
                            width: ListView.view.width
                        }
                    }

                    Label {
                        Layout.fillWidth: true
                        color: root.activityController.recoveryState === "failed" ? Theme.danger :
                                                                                    Theme.textMuted
                        font.family: Theme.sansFamily
                        font.pixelSize: 11
                        objectName: "recoveryIssue"
                        text: root.activityController.recoveryIssue.length > 0
                              ? root.activityController.recoveryIssue : (
                                    root.activityController.recoveryCandidatesModel.count === 0
                                    ? qsTr("No recognized staging candidates were found.") : "")
                        visible: text.length > 0
                        wrapMode: Text.Wrap
                    }

                    AppButton {
                        Layout.fillWidth: true
                        enabled: root.activityController.selectedRecoveryCount > 0
                        objectName: "recoveryRemoveButton"
                        onClicked: removeRecoveryDialog.open()
                        text: qsTr("Remove selected staging directories…")
                        tone: "danger"
                    }
                }
            }
        }
    }

    DecisionDialog {
        id: removeRecordDialog

        acceptText: qsTr("Remove record")
        bodyText: qsTr(
                      "Remove this private Run activity record? Generated datasets and figures remain untouched.")
        objectName: "removeActivityRecordDialog"
        onAccepted: root.removeRecordRequested()
        rejectText: qsTr("Cancel")
        title: qsTr("Remove activity record?")
    }

    DecisionDialog {
        id: removeRecoveryDialog

        acceptText: qsTr("Remove selected")
        bodyText: root.recoveryConfirmationText()
        objectName: "removeRecoveryDialog"
        onAccepted: root.removeRecoveryRequested()
        rejectText: qsTr("Cancel")
        title: qsTr("Remove staging directories?")
    }
}
