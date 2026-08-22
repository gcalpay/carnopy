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
        flickableDirection: Flickable.VerticalFlick
        objectName: "helpPageFlickable"
        pixelAligned: true

        ScrollBar.vertical: ScrollBar {
            policy: ScrollBar.AsNeeded
        }

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
                    text: qsTr("Core workflows, validation authority, and keyboard access.")
                    wrapMode: Text.Wrap
                }
            }

            ResponsiveCardGrid {
                Layout.fillWidth: true
                Layout.preferredHeight: implicitHeight

                Card {
                    Layout.fillWidth: true
                    subtitle: qsTr(
                                  "Create or open a workspace, create a Dataset configuration, Save it, then use Run to Generate the exact saved snapshot.")
                    title: qsTr("Generate a dataset")
                }

                Card {
                    Layout.fillWidth: true
                    subtitle: qsTr(
                                  "After Generate succeeds, Create plot from this run inspects the exact output and opens a compatible editable request. Rendering starts only when Render plot is pressed.")
                    title: qsTr("Plot generated data")
                }

                Card {
                    Layout.fillWidth: true
                    subtitle: qsTr(
                                  "Automate future plots stores plot definitions in YAML. Changes apply only to a later Generate and never add figures to an existing run.")
                    title: qsTr("Automate future plots")
                }

                Card {
                    Layout.fillWidth: true
                    subtitle: qsTr(
                                  "Inspect an eligible finalized source, choose Use for ML Preparation, then continue to configure, Save, Plan, Execute, and inspect the immutable result.")
                    title: qsTr("Prepare data for ML")
                }

                Card {
                    Layout.fillWidth: true
                    subtitle: qsTr(
                                  "Local draft checks provide immediate guidance. Fresh worker validation remains authoritative before Save, Generate, Plan, Execute, inspection, or rendering at their established boundaries.")
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
                                  "Carnopy operates on local workspaces. The desktop adds no web service, cloud database, or telemetry path.")
                    title: qsTr("Local data")
                }

                Card {
                    Layout.fillWidth: true
                    subtitle: qsTr(
                                  "Use Ctrl+B to toggle the wide rail, Ctrl+I for the inspector, Ctrl+, for Settings, F1 for Help, and Escape to dismiss transient drawers.")
                    title: qsTr("Keyboard")
                }
            }
        }
    }
}
