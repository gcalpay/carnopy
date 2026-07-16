import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Carnopy

Item {
    id: root

    Flickable {
        anchors.fill: parent
        boundsBehavior: Flickable.StopAtBounds
        clip: true
        contentHeight: pageColumn.implicitHeight + 48
        contentWidth: width

        ColumnLayout {
            id: pageColumn

            anchors.left: parent.left
            anchors.leftMargin: 24
            anchors.right: parent.right
            anchors.rightMargin: 24
            anchors.top: parent.top
            anchors.topMargin: 24
            spacing: Theme.spacingLarge

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 3

                Label {
                    color: Theme.text
                    font.family: Theme.sansFamily
                    font.pixelSize: 23
                    font.weight: Font.DemiBold
                    text: qsTr("Help")
                }

                Label {
                    Layout.fillWidth: true
                    color: Theme.textMuted
                    font.family: Theme.sansFamily
                    font.pixelSize: 13
                    text: qsTr("Workflow boundaries, keyboard access, and validation authority.")
                    wrapMode: Text.Wrap
                }
            }

            ResponsiveCardGrid {
                Layout.fillWidth: true
                Layout.preferredHeight: implicitHeight

                Card {
                    Layout.fillWidth: true
                    subtitle: qsTr(
                                  "Use Ctrl+B to toggle the wide rail, Ctrl+I for the inspector, Ctrl+, for Settings, F1 for Help, and Escape to dismiss transient drawers.")
                    title: qsTr("Keyboard")
                }

                Card {
                    Layout.fillWidth: true
                    subtitle: qsTr(
                                  "Local draft checks provide immediate guidance. Worker validation remains authoritative before any configuration is written.")
                    title: qsTr("Validation")
                }

                Card {
                    Layout.fillWidth: true
                    subtitle: qsTr(
                                  "CoolProp, generation, pandas, PyArrow, Matplotlib, and rendering remain outside the QML process and execute through the private worker boundary.")
                    title: qsTr("Scientific isolation")
                }

                Card {
                    Layout.fillWidth: true
                    subtitle: qsTr(
                                  "Carnopy operates on local workspaces. The QML shell does not add a web service, cloud database, or telemetry path.")
                    title: qsTr("Local data")
                }

                Card {
                    Layout.fillWidth: true
                    subtitle: qsTr(
                                  "Stage 2 provides bounded QML startup and interaction smoke coverage. Full Windows, macOS, Linux, packaging, and release qualification remains a Stage 8 gate.")
                    title: qsTr("Qualification status")
                }

                Card {
                    Layout.fillWidth: true
                    subtitle: qsTr(
                                  "Unavailable navigation entries name their planned stage and remain outside keyboard focus until their authoritative controllers are bound.")
                    title: qsTr("Migration status")
                }
            }
        }
    }
}
