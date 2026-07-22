pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Carnopy

Control {
    id: root

    property string effectiveTheme: "dark"
    property bool expanded: true
    property bool showBoundary: false
    property string themeMode: "dark"

    signal modeRequested(string mode)

    function iconName(mode) {
        if (mode === "light")
            return "appearance-light";
        if (mode === "warm")
            return "appearance-warm";
        return "appearance-dark";
    }

    function modeLabel(mode) {
        if (mode === "light")
            return qsTr("Light");
        if (mode === "warm")
            return qsTr("Warm");
        if (mode === "dark")
            return qsTr("Dark");
        return qsTr("System");
    }

    function selected(mode) {
        return themeMode === mode || (themeMode === "system" && effectiveTheme === mode);
    }

    implicitHeight: 68
    implicitWidth: expanded ? 154 : 54
    leftPadding: 10
    rightPadding: 10

    background: Rectangle {
        color: Theme.surface

        Rectangle {
            anchors.bottom: parent.bottom
            anchors.left: parent.left
            anchors.top: parent.top
            color: Theme.border
            visible: root.showBoundary
            width: 1
        }
    }

    contentItem: Item {
        RowLayout {
            anchors.centerIn: parent
            spacing: 4
            visible: root.expanded

            Repeater {
                model: [
                    {
                        "mode": "light",
                        "label": qsTr("Light")
                    },
                    {
                        "mode": "warm",
                        "label": qsTr("Warm")
                    },
                    {
                        "mode": "dark",
                        "label": qsTr("Dark")
                    }
                ]

                delegate: ToolButton {
                    id: modeButton

                    required property var modelData
                    readonly property bool isAuto: root.themeMode === "system"
                                                   && root.effectiveTheme === modelData.mode

                    Accessible.description: isAuto ? qsTr(
                                                         "The operating-system appearance currently resolves to %1.").arg(
                                                         modelData.label) : qsTr(
                                                         "Use the %1 appearance mode.").arg(
                                                         modelData.label)
                    Accessible.name: qsTr("%1 appearance").arg(modelData.label)
                    activeFocusOnTab: true
                    display: AbstractButton.IconOnly
                    hoverEnabled: true
                    implicitHeight: 36
                    implicitWidth: 40
                    objectName: "appearance" + modelData.mode.charAt(0).toUpperCase()
                                + modelData.mode.slice(1) + "Button"
                    onClicked: root.modeRequested(modelData.mode)

                    contentItem: Item {
                        AppIcon {
                            anchors.centerIn: parent
                            iconColor: modeButton.modelData.mode === "warm" ? Theme.warning :
                                                                              Theme.text
                            iconSize: 21
                            name: root.iconName(modeButton.modelData.mode)
                        }

                        Rectangle {
                            anchors.bottom: parent.bottom
                            anchors.right: parent.right
                            color: Theme.surfaceRaised
                            height: 12
                            objectName: "appearanceAutoMarker"
                            radius: 2
                            visible: modeButton.isAuto
                            width: 12

                            AppIcon {
                                anchors.centerIn: parent
                                iconColor: Theme.textMuted
                                iconSize: 8
                                name: "monitor"
                            }
                        }
                    }

                    background: Rectangle {
                        border.color: modeButton.activeFocus ? Theme.information : (root.selected(
                                                                                        modeButton.modelData.mode)
                                                                                    ? Theme.primary :
                                                                                      "transparent")
                        border.width: modeButton.activeFocus ? 2 : 1
                        color: modeButton.hovered || modeButton.down ? Theme.surfaceMuted :
                                                                       "transparent"
                        radius: Theme.radiusSmall
                    }

                    ToolTip.delay: 350
                    ToolTip.text: isAuto ? qsTr("%1 · Auto").arg(modelData.label) : modelData.label
                    ToolTip.visible: hovered
                }
            }
        }

        ToolButton {
            id: compactButton

            Accessible.description: root.themeMode === "system" ? qsTr(
                                                                      "System appearance is active. Open appearance choices.") :
                                                                  qsTr("Open appearance choices.")
            Accessible.name: qsTr("Appearance: %1").arg(root.modeLabel(root.themeMode))
            activeFocusOnTab: true
            anchors.centerIn: parent
            display: AbstractButton.IconOnly
            hoverEnabled: true
            implicitHeight: 36
            implicitWidth: 38
            objectName: "appearanceMenuButton"
            onClicked: appearanceMenu.open()
            visible: !root.expanded

            contentItem: Item {
                AppIcon {
                    anchors.centerIn: parent
                    iconColor: root.effectiveTheme === "warm" ? Theme.warning : Theme.text
                    iconSize: 21
                    name: root.iconName(root.effectiveTheme)
                }

                Rectangle {
                    anchors.bottom: parent.bottom
                    anchors.right: parent.right
                    color: Theme.surfaceRaised
                    height: 12
                    objectName: "appearanceCompactAutoMarker"
                    radius: 2
                    visible: root.themeMode === "system"
                    width: 12

                    AppIcon {
                        anchors.centerIn: parent
                        iconColor: Theme.textMuted
                        iconSize: 8
                        name: "monitor"
                    }
                }
            }

            background: Rectangle {
                border.color: compactButton.activeFocus ? Theme.information : Theme.primary
                border.width: compactButton.activeFocus ? 2 : 1
                color: compactButton.hovered || compactButton.down ? Theme.surfaceMuted :
                                                                     "transparent"
                radius: Theme.radiusSmall
            }

            ToolTip.delay: 350
            ToolTip.text: qsTr("Appearance")
            ToolTip.visible: hovered
        }

        Menu {
            id: appearanceMenu

            objectName: "appearanceMenu"
            y: compactButton.y + compactButton.height

            MenuItem {
                checkable: true
                checked: root.themeMode === "system"
                objectName: "appearanceSystemMenuItem"
                onTriggered: root.modeRequested("system")
                text: qsTr("System")
            }

            MenuItem {
                checkable: true
                checked: root.themeMode === "light"
                objectName: "appearanceLightMenuItem"
                onTriggered: root.modeRequested("light")
                text: qsTr("Light")
            }

            MenuItem {
                checkable: true
                checked: root.themeMode === "warm"
                objectName: "appearanceWarmMenuItem"
                onTriggered: root.modeRequested("warm")
                text: qsTr("Warm")
            }

            MenuItem {
                checkable: true
                checked: root.themeMode === "dark"
                objectName: "appearanceDarkMenuItem"
                onTriggered: root.modeRequested("dark")
                text: qsTr("Dark")
            }
        }
    }
}
