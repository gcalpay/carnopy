pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Carnopy

Control {
    id: root

    property var issues: []
    property string message: ""
    property string operation: ""
    property string title: ""

    signal dismissed

    function issueText(index) {
        const issue = root.issues[index];
        if (issue === undefined || issue === null)
            return "";
        const path = issue.path === undefined ? "$" : String(issue.path);
        const detail = issue.message === undefined ? qsTr("Invalid value") : String(issue.message);
        return path + ": " + detail;
    }

    implicitHeight: feedbackContent.implicitHeight + topPadding + bottomPadding
    leftPadding: 18
    rightPadding: 18
    topPadding: 10
    bottomPadding: 10
    visible: message.length > 0

    background: Rectangle {
        border.color: Theme.danger
        border.width: 1
        color: Theme.dangerSoft
    }

    contentItem: RowLayout {
        id: feedbackContent

        spacing: Theme.spacingMedium

        StatusBadge {
            label: qsTr("Blocked")
            tone: "danger"
        }

        ColumnLayout {
            Layout.fillWidth: true
            spacing: Theme.spacingTiny

            Label {
                Layout.fillWidth: true
                color: Theme.text
                font.family: Theme.sansFamily
                font.pixelSize: 13
                font.weight: Font.DemiBold
                text: root.title
                wrapMode: Text.Wrap
            }

            Label {
                Layout.fillWidth: true
                color: Theme.textMuted
                font.family: Theme.sansFamily
                font.pixelSize: 12
                text: root.message
                wrapMode: Text.Wrap
            }

            Repeater {
                model: Math.min(3, root.issues.length)

                delegate: Label {
                    required property int index

                    Layout.fillWidth: true
                    color: Theme.textMuted
                    font.family: Theme.monoFamily
                    font.pixelSize: 10
                    text: root.issueText(index)
                    wrapMode: Text.Wrap
                }
            }
        }

        AppButton {
            compact: true
            objectName: "operationFeedbackDismiss"
            onClicked: root.dismissed()
            text: qsTr("Dismiss")
        }
    }
}
