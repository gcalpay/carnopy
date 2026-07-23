import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Carnopy

Control {
    id: root

    property string tone: "neutral"
    property string label: ""
    property color statusColor: {
        if (tone === "success")
            return Theme.success;
        if (tone === "warning")
            return Theme.warning;
        if (tone === "danger")
            return Theme.danger;
        if (tone === "information")
            return Theme.information;
        return Theme.textMuted;
    }

    Accessible.name: label
    implicitHeight: 28
    implicitWidth: badgeRow.implicitWidth + 18
    leftPadding: 9
    rightPadding: 9

    background: Rectangle {
        border.color: Theme.border
        color: Theme.surfaceMuted
        radius: height / 2
    }

    contentItem: RowLayout {
        id: badgeRow

        spacing: 7

        Rectangle {
            Layout.alignment: Qt.AlignVCenter
            Layout.preferredHeight: 7
            Layout.preferredWidth: 7
            color: root.statusColor
            radius: 4
        }

        Label {
            Layout.alignment: Qt.AlignVCenter
            color: Theme.text
            font.family: Theme.sansFamily
            font.pixelSize: 12
            font.weight: Font.Medium
            text: root.label
        }
    }
}
