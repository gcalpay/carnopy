import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Carnopy

Item {
    id: root

    property int expectedColumns: 1

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
                    Layout.fillWidth: true
                    color: Theme.text
                    font.family: Theme.sansFamily
                    font.pixelSize: 23
                    font.weight: Font.DemiBold
                    text: qsTr("Workspace")
                }

                Label {
                    Layout.fillWidth: true
                    color: Theme.textMuted
                    font.family: Theme.sansFamily
                    font.pixelSize: 13
                    text: qsTr(
                              "A dense, local-first workbench for reproducible thermophysical datasets.")
                    wrapMode: Text.Wrap
                }
            }

            Card {
                Layout.fillWidth: true
                subtitle: qsTr(
                              "This commit establishes the responsive application shell only. Workspace creation and opening are bound in the next verified slice.")
                title: qsTr("No workspace loaded")

                StatusBadge {
                    label: qsTr("Interface ready")
                    tone: "success"
                }
            }

            ResponsiveCardGrid {
                id: overviewGrid

                Layout.fillWidth: true
                Layout.preferredHeight: implicitHeight
                maximumColumns: 3
                minimumCardWidth: 300
                objectName: "workspaceOverviewGrid"

                Card {
                    Layout.fillWidth: true
                    subtitle: qsTr(
                                  "Persistent navigation, a slim command bar, and an adaptive inspector keep scientific context visible.")
                    title: qsTr("Precision Grid")
                }

                Card {
                    Layout.fillWidth: true
                    subtitle: qsTr(
                                  "The QML process remains isolated from CoolProp, NumPy, pandas, PyArrow, Matplotlib, generation, and rendering.")
                    title: qsTr("Scientific isolation")
                }

                Card {
                    Layout.fillWidth: true
                    subtitle: qsTr(
                                  "System, Light, and Dark modes use packaged IBM Plex fonts and an audited Lucide icon subset.")
                    title: qsTr("Consistent interface")
                }
            }

            Card {
                Layout.fillWidth: true
                title: qsTr("Next steps")

                RowLayout {
                    Layout.fillWidth: true
                    spacing: Theme.spacingMedium

                    StatusBadge {
                        label: "1"
                        tone: "information"
                    }

                    Label {
                        Layout.fillWidth: true
                        color: Theme.text
                        font.family: Theme.sansFamily
                        font.pixelSize: 13
                        text: qsTr("Establish or open a local workspace")
                        wrapMode: Text.Wrap
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: Theme.spacingMedium

                    StatusBadge {
                        label: "2"
                        tone: "neutral"
                    }

                    Label {
                        Layout.fillWidth: true
                        color: Theme.text
                        font.family: Theme.sansFamily
                        font.pixelSize: 13
                        text: qsTr("Configure the dataset through authoritative draft models")
                        wrapMode: Text.Wrap
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: Theme.spacingMedium

                    StatusBadge {
                        label: "3"
                        tone: "neutral"
                    }

                    Label {
                        Layout.fillWidth: true
                        color: Theme.text
                        font.family: Theme.sansFamily
                        font.pixelSize: 13
                        text: qsTr(
                                  "Review exact YAML and validate through the worker before saving")
                        wrapMode: Text.Wrap
                    }
                }
            }

            Label {
                Layout.fillWidth: true
                color: Theme.textSubtle
                font.family: Theme.monoFamily
                font.pixelSize: 11
                horizontalAlignment: Text.AlignRight
                text: qsTr("Responsive columns: %1").arg(overviewGrid.columnCount)
            }
        }
    }
}
