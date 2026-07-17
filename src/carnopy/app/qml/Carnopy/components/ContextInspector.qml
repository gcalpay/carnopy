import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Carnopy

Control {
    id: root

    property bool closeButtonVisible: false
    property string workspacePath: ""
    property string workspaceState: "unavailable"

    signal closeRequested

    implicitWidth: 304
    leftPadding: 16
    rightPadding: 16
    topPadding: 16
    bottomPadding: 16

    background: Rectangle {
        border.color: Theme.border
        border.width: 1
        color: Theme.surfaceRaised
    }

    contentItem: ColumnLayout {
        spacing: Theme.spacingMedium

        RowLayout {
            Layout.fillWidth: true

            Label {
                Layout.fillWidth: true
                color: Theme.text
                font.family: Theme.sansFamily
                font.pixelSize: 16
                font.weight: Font.DemiBold
                text: qsTr("Context inspector")
            }

            AppButton {
                Accessible.description: qsTr("Close context inspector")
                compact: true
                iconName: "panel-right-close"
                objectName: "inspectorCloseButton"
                onClicked: root.closeRequested()
                visible: root.closeButtonVisible
            }
        }

        Flickable {
            Layout.fillHeight: true
            Layout.fillWidth: true
            boundsBehavior: Flickable.StopAtBounds
            clip: true
            contentHeight: inspectorColumn.implicitHeight
            contentWidth: width

            ColumnLayout {
                id: inspectorColumn

                spacing: Theme.spacingMedium
                width: parent.width

                Card {
                    Layout.fillWidth: true
                    subtitle: root.workspacePath.length > 0 ? root.workspacePath : qsTr(
                                                                  "No local workspace is open.")
                    title: qsTr("Workspace")

                    Label {
                        Layout.fillWidth: true
                        color: Theme.textMuted
                        font.family: Theme.sansFamily
                        font.pixelSize: 12
                        text: root.workspaceState === "loading" ? qsTr(
                                                                      "Worker capabilities are loading through the shared request coordinator.") :
                                                                  qsTr("Workspace state comes from the authoritative desktop composition.")
                        wrapMode: Text.Wrap
                    }
                }

                Card {
                    Layout.fillWidth: true
                    title: qsTr("Document state")

                    RowLayout {
                        Layout.fillWidth: true

                        Label {
                            Layout.fillWidth: true
                            color: Theme.textMuted
                            font.family: Theme.sansFamily
                            font.pixelSize: 12
                            text: qsTr("Configuration")
                        }

                        Label {
                            color: Theme.text
                            font.family: Theme.sansFamily
                            font.pixelSize: 12
                            font.weight: Font.Medium
                            text: root.workspaceState === "editing" ? qsTr("Open") : qsTr(
                                                                          "Not loaded")
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true

                        Label {
                            Layout.fillWidth: true
                            color: Theme.textMuted
                            font.family: Theme.sansFamily
                            font.pixelSize: 12
                            text: qsTr("Worker validation")
                        }

                        Label {
                            color: Theme.text
                            font.family: Theme.sansFamily
                            font.pixelSize: 12
                            font.weight: Font.Medium
                            text: qsTr("Not available")
                        }
                    }
                }

                Card {
                    Layout.fillWidth: true
                    subtitle: qsTr(
                                  "Dataset cards and safe unit changes are the next independently verified implementation commit.")
                    title: qsTr("Next implementation step")
                }

                Item {
                    Layout.fillHeight: true
                    Layout.minimumHeight: 1
                }
            }
        }
    }
}
