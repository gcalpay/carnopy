pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Carnopy

Flickable {
    id: root

    required property var inspectionController

    signal exploreRequested

    boundsBehavior: Flickable.StopAtBounds
    clip: true
    contentHeight: inspectionColumn.implicitHeight
    contentWidth: width
    flickableDirection: Flickable.VerticalFlick
    objectName: "inspectionContextInspector"

    ScrollBar.vertical: ScrollBar {
        policy: ScrollBar.AsNeeded
    }

    ColumnLayout {
        id: inspectionColumn

        spacing: Theme.spacingMedium
        width: parent.width

        Card {
            flat: true
            Layout.fillWidth: true
            subtitle: root.inspectionController.sourcePath.length > 0
                      ? root.inspectionController.sourcePath : qsTr(
                            "Choose a workspace output or an external source.")
            title: qsTr("Inspected source")

            StatusBadge {
                label: {
                    if (root.inspectionController.state === "loading")
                    return qsTr("Inspecting");
                    if (root.inspectionController.state === "ready")
                    return root.inspectionController.integrityLabel;
                    if (root.inspectionController.state === "stale")
                    return qsTr("Stale");
                    if (root.inspectionController.state === "failed")
                    return qsTr("Failed");
                    return qsTr("Not selected");
                }
                tone: root.inspectionController.state === "ready" ? "success" : (
                                                                        root.inspectionController.state
                                                                        === "failed"
                                                                        || root.inspectionController.state
                                                                        === "stale" ? "danger" : (
                                                                                          root.inspectionController.state
                                                                                          === "loading"
                                                                                          ? "information" :
                                                                                            "neutral"))
            }

            Label {
                Layout.fillWidth: true
                color: Theme.textMuted
                font.family: Theme.sansFamily
                font.pixelSize: 11
                text: root.inspectionController.issue
                visible: text.length > 0
                wrapMode: Text.Wrap
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            color: Theme.divider
        }

        Card {
            flat: true
            Layout.fillWidth: true
            title: qsTr("Inspection identity")

            RowLayout {
                Layout.fillWidth: true

                Label {
                    Layout.fillWidth: true
                    color: Theme.textMuted
                    font.family: Theme.sansFamily
                    font.pixelSize: 12
                    text: qsTr("Kind")
                }

                Label {
                    color: Theme.text
                    font.family: Theme.monoFamily
                    font.pixelSize: 11
                    text: root.inspectionController.sourceKind.length > 0
                          ? root.inspectionController.sourceKind : qsTr("Unavailable")
                }
            }

            Label {
                Layout.fillWidth: true
                color: Theme.textMuted
                elide: Text.ElideMiddle
                font.family: Theme.monoFamily
                font.pixelSize: 10
                text: root.inspectionController.revision
                visible: text.length > 0
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            color: Theme.divider
        }

        Card {
            flat: true
            Layout.fillWidth: true
            subtitle: root.inspectionController.previewState === "ready" ? qsTr(
                                                                               "Rows %1–%2 of %3 are loaded from a bounded worker block.").arg(
                                                                               root.inspectionController.previewFirstRow).arg(
                                                                               root.inspectionController.previewLastRow).arg(
                                                                               root.inspectionController.previewTotalRows) :
                                                                           qsTr("Select a reported table to request a bounded preview.")
            title: qsTr("Table preview")

            StatusBadge {
                label: root.inspectionController.previewState === "ready" ? qsTr("Ready") : (
                                                                                root.inspectionController.previewState
                                                                                === "loading" ? qsTr(
                                                                                                    "Loading") :
                                                                                                qsTr("Unavailable"))
                tone: root.inspectionController.previewState === "ready" ? "success" : (
                                                                               root.inspectionController.previewState
                                                                               === "loading"
                                                                               ? "information" :
                                                                                 "neutral")
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            color: Theme.divider
        }

        Card {
            flat: true
            Layout.fillWidth: true
            subtitle: root.inspectionController.canExplorePlots ? qsTr(
                                                                      "This exact inspected dataset is ready for session plotting.") :
                                                                  qsTr("Session plotting requires an inspected dataset source with compatible emitted fields.")
            title: qsTr("Visualization")

            AppButton {
                Layout.fillWidth: true
                enabled: root.inspectionController.canExplorePlots
                objectName: "inspectionExploreButton"
                onClicked: root.exploreRequested()
                text: qsTr("Explore in Visualization")
                tone: "primary"

                ToolTip.text: enabled ? qsTr(
                                            "Open session plotting for this exact inspected dataset without rendering automatically.") :
                                        qsTr("Inspect a compatible generated dataset before opening session plotting.")
                ToolTip.visible: hovered
            }
        }
    }
}
