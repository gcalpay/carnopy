import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Carnopy

Button {
    id: control

    property string tone: "secondary"
    property string iconName: ""
    property color iconColor: foregroundColor
    property bool compact: false
    property color foregroundColor: {
        if (!control.enabled)
            return Theme.textSubtle;
        if (control.tone === "primary")
            return Theme.highlightedText;
        if (control.tone === "quiet")
            return Theme.textMuted;
        return Theme.text;
    }

    Accessible.name: text
    activeFocusOnTab: enabled
    hoverEnabled: true
    implicitHeight: 36
    implicitWidth: compact ? 36 : Math.max(82, contentRow.implicitWidth + 22)
    leftPadding: compact ? 8 : 11
    rightPadding: compact ? 8 : 11

    contentItem: RowLayout {
        id: contentRow

        spacing: control.compact || control.iconName.length === 0 ? 0 : 8

        AppIcon {
            Layout.alignment: Qt.AlignVCenter
            iconColor: control.iconColor
            iconSize: 18
            name: control.iconName
            visible: name.length > 0
        }

        Label {
            Layout.alignment: Qt.AlignVCenter
            color: control.foregroundColor
            elide: Text.ElideRight
            font.family: Theme.sansFamily
            font.pixelSize: 13
            font.weight: control.tone === "primary" ? Font.Medium : Font.Normal
            horizontalAlignment: Text.AlignHCenter
            text: control.compact ? "" : control.text
            visible: !control.compact
        }
    }

    background: Rectangle {
        border.color: {
            if (control.tone === "primary" || control.tone === "quiet")
                return "transparent";
            return control.activeFocus ? Theme.focus : Theme.borderStrong;
        }
        border.width: control.activeFocus ? 2 : 1
        color: {
            if (!control.enabled)
                return Theme.surfaceMuted;
            if (control.tone === "primary") {
                if (control.down)
                    return Theme.primaryPressed;
                return control.hovered ? Theme.primaryHover : Theme.primary;
            }
            if (control.tone === "quiet")
                return control.hovered || control.down ? Theme.hover : "transparent";
            return control.hovered || control.down ? Theme.hover : Theme.surface;
        }
        radius: Theme.radiusSmall

        Behavior on color {
            ColorAnimation {
                duration: Theme.durationFast
            }
        }
    }
}
