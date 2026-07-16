import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Carnopy

Control {
    id: root

    property bool closeButtonVisible: false
    property string pageTitle: qsTr("Workspace")

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

    contentItem: Flickable {
        boundsBehavior: Flickable.StopAtBounds
        clip: true
        contentHeight: inspectorColumn.implicitHeight
        contentWidth: width

        ColumnLayout {
            id: inspectorColumn

            spacing: Theme.spacingMedium
            width: parent.width

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
                    onClicked: root.closeRequested()
                    visible: root.closeButtonVisible
                }
            }

            Card {
                Layout.fillWidth: true
                subtitle: qsTr("This shell does not fabricate document or worker state.")
                title: root.pageTitle

                Label {
                    Layout.fillWidth: true
                    color: Theme.textMuted
                    font.family: Theme.sansFamily
                    font.pixelSize: 12
                    text: qsTr(
                              "Page-specific issues and guidance will appear here as each authoritative workflow is bound.")
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
                        text: qsTr("Not loaded")
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
                              "Workspace lifecycle binding is the next independently verified implementation commit.")
                title: qsTr("Next implementation step")
            }

            Item {
                Layout.fillHeight: true
                Layout.minimumHeight: 1
            }
        }
    }
}
