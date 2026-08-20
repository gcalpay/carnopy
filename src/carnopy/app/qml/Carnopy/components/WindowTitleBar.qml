pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import Carnopy

Item {
    id: root

    required property bool emulateMaximize
    required property bool emulatedMaximized
    required property Window targetWindow
    property string applicationTitle: qsTr("Carnopy")
    readonly property bool maximized: emulatedMaximized || targetWindow.visibility
                                      === Window.Maximized
    readonly property bool windowActive: targetWindow.active

    signal maximizeRestoreRequested

    function toggleMaximized() {
        if (emulateMaximize) {
            maximizeRestoreRequested();
            return;
        }
        if (maximized)
            targetWindow.showNormal();
        else
            targetWindow.showMaximized();
    }

    function beginSystemMove() {
        // A maximized window must be restored before an interactive move.
        // The WSLg/XCB fallback delegates that restore to the runtime so it
        // never enters WSLg's broken borderless maximized state.
        if (maximized) {
            toggleMaximized();
            return;
        }
        targetWindow.startSystemMove();
    }

    implicitHeight: 40

    Rectangle {
        id: titleBarBackground

        anchors.fill: parent
        color: root.windowActive ? Theme.surfaceRaised : Theme.surface
        objectName: "windowTitleBarBackground"

        Behavior on color {
            ColorAnimation {
                duration: Theme.durationFast
            }
        }

        Rectangle {
            anchors.bottom: parent.bottom
            anchors.left: parent.left
            anchors.right: parent.right
            color: root.windowActive ? Theme.borderStrong : Theme.border
            height: 1
        }
    }

    RowLayout {
        anchors.fill: parent
        spacing: 0

        Item {
            id: dragRegion

            Layout.fillHeight: true
            Layout.fillWidth: true
            objectName: "windowTitleDragArea"

            TapHandler {
                acceptedButtons: Qt.LeftButton
                gesturePolicy: TapHandler.DragThreshold
                onTapped: {
                    if (tapCount === 2)
                    root.toggleMaximized();
                }
            }

            DragHandler {
                acceptedButtons: Qt.LeftButton
                target: null
                onActiveChanged: {
                    if (active)
                    root.beginSystemMove();
                }
            }

            Label {
                anchors.left: parent.left
                anchors.leftMargin: 14
                anchors.verticalCenter: parent.verticalCenter
                color: root.windowActive ? Theme.text : Theme.textMuted
                elide: Text.ElideRight
                font.family: Theme.sansFamily
                font.pixelSize: 12
                font.weight: Font.DemiBold
                text: root.applicationTitle
            }
        }

        WindowButton {
            Layout.fillHeight: true
            activeWindow: root.windowActive
            controlKind: "minimize"
            objectName: "windowMinimizeButton"
            onClicked: root.targetWindow.showMinimized()
            text: qsTr("Minimize")
        }

        WindowButton {
            Layout.fillHeight: true
            activeWindow: root.windowActive
            controlKind: root.maximized ? "restore" : "maximize"
            objectName: "windowMaximizeRestoreButton"
            onClicked: root.toggleMaximized()
            text: root.maximized ? qsTr("Restore") : qsTr("Maximize")
        }

        WindowButton {
            Layout.fillHeight: true
            activeWindow: root.windowActive
            closeControl: true
            controlKind: "close"
            objectName: "windowCloseButton"
            onClicked: root.targetWindow.close()
            text: qsTr("Close")
        }
    }

    component WindowButton: Button {
        id: control

        required property bool activeWindow
        required property string controlKind
        property bool closeControl: false
        readonly property color buttonColor: {
            if (closeControl && (hovered || down))
            return Theme.danger;
            if (down)
            return Theme.surfaceMuted;
            return hovered ? Theme.hover : "transparent";
        }
        readonly property color glyphColor: {
            if (closeControl && (hovered || down))
            return Theme.highlightedText;
            return activeWindow ? Theme.text : Theme.textMuted;
        }

        Accessible.name: text
        activeFocusOnTab: true
        hoverEnabled: true
        implicitHeight: root.implicitHeight
        implicitWidth: 46

        ToolTip.delay: 600
        ToolTip.text: text
        ToolTip.visible: hovered

        contentItem: Item {
            Rectangle {
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.verticalCenter: parent.verticalCenter
                anchors.verticalCenterOffset: 3
                color: control.glyphColor
                height: 1
                visible: control.controlKind === "minimize"
                width: 11
            }

            Rectangle {
                anchors.centerIn: parent
                border.color: control.glyphColor
                border.width: 1
                color: "transparent"
                height: 10
                visible: control.controlKind === "maximize"
                width: 10
            }

            Item {
                anchors.centerIn: parent
                height: 12
                visible: control.controlKind === "restore"
                width: 13

                Rectangle {
                    anchors.right: parent.right
                    anchors.top: parent.top
                    border.color: control.glyphColor
                    border.width: 1
                    color: "transparent"
                    height: 8
                    width: 9
                }

                Rectangle {
                    anchors.bottom: parent.bottom
                    anchors.left: parent.left
                    border.color: control.glyphColor
                    border.width: 1
                    color: control.buttonColor === "transparent" ? (control.activeWindow
                                                                    ? Theme.surfaceRaised :
                                                                      Theme.surface) :
                                                                   control.buttonColor
                    height: 8
                    width: 9
                }
            }

            Item {
                anchors.centerIn: parent
                height: 12
                visible: control.controlKind === "close"
                width: 12

                Rectangle {
                    anchors.centerIn: parent
                    color: control.glyphColor
                    height: 1
                    rotation: 45
                    width: 13
                }

                Rectangle {
                    anchors.centerIn: parent
                    color: control.glyphColor
                    height: 1
                    rotation: -45
                    width: 13
                }
            }
        }

        background: Rectangle {
            border.color: control.activeFocus ? Theme.focus : "transparent"
            border.width: control.activeFocus ? 2 : 0
            color: control.buttonColor

            Behavior on color {
                ColorAnimation {
                    duration: Theme.durationFast
                }
            }
        }
    }
}
