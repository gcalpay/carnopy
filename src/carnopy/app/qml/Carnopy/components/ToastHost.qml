import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Carnopy

Item {
    id: root

    property string message: ""
    property string tone: "information"

    function showMessage(nextMessage, nextTone) {
        root.message = nextMessage;
        root.tone = nextTone || "information";
        toast.visible = true;
        dismissTimer.restart();
    }

    anchors.fill: parent
    visible: toast.visible
    z: 100

    Timer {
        id: dismissTimer

        interval: 3600
        onTriggered: toast.visible = false
    }

    Rectangle {
        id: toast

        anchors.bottom: parent.bottom
        anchors.bottomMargin: 24
        anchors.horizontalCenter: parent.horizontalCenter
        border.color: Theme.borderStrong
        color: Theme.surface
        implicitHeight: toastRow.implicitHeight + 20
        implicitWidth: Math.min(520, toastRow.implicitWidth + 28)
        radius: Theme.radiusMedium
        visible: false

        RowLayout {
            id: toastRow

            anchors.fill: parent
            anchors.margins: 10
            spacing: Theme.spacingSmall

            StatusBadge {
                label: root.tone === "success" ? qsTr("Success") : qsTr("Notice")
                tone: root.tone
            }

            Label {
                Layout.fillWidth: true
                color: Theme.text
                font.family: Theme.sansFamily
                font.pixelSize: 13
                text: root.message
                wrapMode: Text.Wrap
            }
        }

        Behavior on opacity {
            NumberAnimation {
                duration: Theme.durationStandard
                easing.type: Easing.OutCubic
            }
        }
    }
}
