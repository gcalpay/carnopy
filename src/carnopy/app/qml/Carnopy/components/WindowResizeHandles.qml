pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Window
import Carnopy

Item {
    id: root

    required property Window targetWindow
    readonly property bool resizeEnabled: targetWindow.visibility === Window.Windowed
    readonly property bool windowActive: targetWindow.active
    property int cornerExtent: 12
    property int edgeThickness: 6

    enabled: resizeEnabled

    Rectangle {
        anchors.fill: parent
        border.color: root.windowActive ? Theme.borderStrong : Theme.border
        border.width: root.resizeEnabled ? 1 : 0
        color: "transparent"
        objectName: "customWindowFrameOutline"
    }

    ResizeHandle {
        anchors.bottom: parent.bottom
        anchors.left: parent.left
        anchors.top: parent.top
        anchors.bottomMargin: root.cornerExtent
        anchors.topMargin: root.cornerExtent
        cursorShape: Qt.SizeHorCursor
        objectName: "windowResizeLeft"
        resizeEdges: Qt.LeftEdge
        targetWindow: root.targetWindow
        width: root.edgeThickness
    }

    ResizeHandle {
        anchors.bottom: parent.bottom
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.bottomMargin: root.cornerExtent
        anchors.topMargin: root.cornerExtent
        cursorShape: Qt.SizeHorCursor
        objectName: "windowResizeRight"
        resizeEdges: Qt.RightEdge
        targetWindow: root.targetWindow
        width: root.edgeThickness
    }

    ResizeHandle {
        anchors.left: parent.left
        anchors.leftMargin: root.cornerExtent
        anchors.right: parent.right
        anchors.rightMargin: root.cornerExtent
        anchors.top: parent.top
        cursorShape: Qt.SizeVerCursor
        height: root.edgeThickness
        objectName: "windowResizeTop"
        resizeEdges: Qt.TopEdge
        targetWindow: root.targetWindow
    }

    ResizeHandle {
        anchors.bottom: parent.bottom
        anchors.left: parent.left
        anchors.leftMargin: root.cornerExtent
        anchors.right: parent.right
        anchors.rightMargin: root.cornerExtent
        cursorShape: Qt.SizeVerCursor
        height: root.edgeThickness
        objectName: "windowResizeBottom"
        resizeEdges: Qt.BottomEdge
        targetWindow: root.targetWindow
    }

    ResizeHandle {
        anchors.left: parent.left
        anchors.top: parent.top
        cursorShape: Qt.SizeFDiagCursor
        height: root.cornerExtent
        objectName: "windowResizeTopLeft"
        resizeEdges: Qt.LeftEdge | Qt.TopEdge
        targetWindow: root.targetWindow
        width: root.cornerExtent
    }

    ResizeHandle {
        anchors.right: parent.right
        anchors.top: parent.top
        cursorShape: Qt.SizeBDiagCursor
        height: root.cornerExtent
        objectName: "windowResizeTopRight"
        resizeEdges: Qt.RightEdge | Qt.TopEdge
        targetWindow: root.targetWindow
        width: root.cornerExtent
    }

    ResizeHandle {
        anchors.bottom: parent.bottom
        anchors.left: parent.left
        cursorShape: Qt.SizeBDiagCursor
        height: root.cornerExtent
        objectName: "windowResizeBottomLeft"
        resizeEdges: Qt.LeftEdge | Qt.BottomEdge
        targetWindow: root.targetWindow
        width: root.cornerExtent
    }

    ResizeHandle {
        anchors.bottom: parent.bottom
        anchors.right: parent.right
        cursorShape: Qt.SizeFDiagCursor
        height: root.cornerExtent
        objectName: "windowResizeBottomRight"
        resizeEdges: Qt.RightEdge | Qt.BottomEdge
        targetWindow: root.targetWindow
        width: root.cornerExtent
    }

    component ResizeHandle: MouseArea {
        id: handle

        required property int resizeEdges
        required property Window targetWindow

        acceptedButtons: Qt.LeftButton
        enabled: targetWindow.visibility === Window.Windowed
        hoverEnabled: true
        onPressed: mouse => {
            if (!targetWindow.startSystemResize(resizeEdges))
                mouse.accepted = false;
        }
    }
}
