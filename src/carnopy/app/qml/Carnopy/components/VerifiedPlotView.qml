pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Carnopy

Item {
    id: root

    property bool canExport: false
    property bool canOpenPdf: false
    property bool canPreview: false
    property int excludedSampleCount: 0
    property string format: ""
    property string plotKind: ""
    property string plotName: ""
    property url previewSource: ""
    property int validSampleCount: 0

    signal exportRequested
    signal openPdfRequested

    function openFocusMode() {
        if (!canPreview)
            return;
        focusMode.returnTarget = root.Window.window === null ? null :
                                                               root.Window.window.activeFocusItem;


        focusMode.zoom = 1.0;
        focusMode.open();
    }

    implicitHeight: content.implicitHeight

    ColumnLayout {
        id: content

        anchors.left: parent.left
        anchors.right: parent.right
        spacing: Theme.spacingMedium

        RowLayout {
            Layout.fillWidth: true

            ColumnLayout {
                Layout.fillWidth: true
                spacing: Theme.spacingTiny

                Label {
                    Layout.fillWidth: true
                    color: Theme.text
                    elide: Text.ElideRight
                    font.family: Theme.sansFamily
                    font.pixelSize: 15
                    font.weight: Font.DemiBold
                    text: root.plotName.length > 0 ? root.plotName : qsTr("Plot result")
                }

                Label {
                    Layout.fillWidth: true
                    color: Theme.textMuted
                    font.family: Theme.monoFamily
                    font.pixelSize: 11
                    text: root.plotKind + (root.format.length > 0 ? " · " + root.format.toUpperCase(
                                                                        ) : "")
                    visible: text.length > 0
                }
            }

            StatusBadge {
                label: qsTr("%1 valid · %2 excluded").arg(root.validSampleCount).arg(
                           root.excludedSampleCount)
                tone: root.excludedSampleCount > 0 ? "warning" : "success"
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 360
            border.color: Theme.border
            border.width: 1
            color: Theme.canvas
            radius: Theme.radiusSmall

            Image {
                anchors.fill: parent
                anchors.margins: Theme.spacingSmall
                asynchronous: true
                cache: false
                fillMode: Image.PreserveAspectFit
                source: root.canPreview ? root.previewSource : ""
                visible: root.canPreview
            }

            ColumnLayout {
                anchors.centerIn: parent
                spacing: Theme.spacingSmall
                visible: !root.canPreview

                Label {
                    Layout.alignment: Qt.AlignHCenter
                    color: Theme.text
                    font.family: Theme.sansFamily
                    font.pixelSize: 14
                    text: root.canOpenPdf ? qsTr("PDF preview opens in the system viewer") : qsTr(
                                                "No in-app preview is available")
                }

                AppButton {
                    Layout.alignment: Qt.AlignHCenter
                    enabled: root.canOpenPdf
                    onClicked: root.openPdfRequested()
                    text: qsTr("Open PDF")
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true

            AppButton {
                enabled: root.canPreview
                objectName: "plotFocusModeButton"
                onClicked: root.openFocusMode()
                text: qsTr("Focus mode")
            }

            AppButton {
                enabled: root.canExport
                objectName: "plotExportButton"
                onClicked: root.exportRequested()
                text: qsTr("Export image + sidecar")
            }

            AppButton {
                enabled: root.canOpenPdf
                objectName: "plotOpenPdfButton"
                onClicked: root.openPdfRequested()
                text: qsTr("Open PDF")
                visible: root.canOpenPdf
            }

            Item {
                Layout.fillWidth: true
            }
        }
    }

    Dialog {
        id: focusMode

        property Item returnTarget: null
        property real zoom: 1.0

        anchors.centerIn: Overlay.overlay
        closePolicy: Popup.CloseOnEscape
        focus: true
        height: Math.max(480, Math.min(Overlay.overlay.height - 40, 900))
        modal: true
        objectName: "plotFocusModeDialog"
        padding: Theme.spacingMedium
        title: root.plotName
        width: Math.max(640, Math.min(Overlay.overlay.width - 40, 1440))

        onClosed: {
            const target = returnTarget;
            returnTarget = null;
            if (target !== null)
            Qt.callLater(function () {
                target.forceActiveFocus();
            });
        }

        contentItem: ColumnLayout {
            spacing: Theme.spacingSmall

            Flickable {
                Layout.fillHeight: true
                Layout.fillWidth: true
                boundsBehavior: Flickable.StopAtBounds
                clip: true
                contentHeight: Math.max(height, focusImage.implicitHeight * focusMode.zoom)
                contentWidth: Math.max(width, focusImage.implicitWidth * focusMode.zoom)

                Image {
                    id: focusImage

                    anchors.centerIn: parent
                    asynchronous: true
                    cache: false
                    fillMode: Image.PreserveAspectFit
                    height: Math.min(implicitHeight * focusMode.zoom, parent.height
                                     * focusMode.zoom)
                    source: root.previewSource
                    width: Math.min(implicitWidth * focusMode.zoom, parent.width * focusMode.zoom)
                }
            }

            RowLayout {
                Layout.fillWidth: true

                AppButton {
                    onClicked: focusMode.zoom = 1.0
                    text: qsTr("Fit")
                }

                AppButton {
                    enabled: focusMode.zoom > 0.25
                    onClicked: focusMode.zoom = Math.max(0.25, focusMode.zoom - 0.25)
                    text: qsTr("−")
                }

                AppButton {
                    enabled: focusMode.zoom < 4.0
                    onClicked: focusMode.zoom = Math.min(4.0, focusMode.zoom + 0.25)
                    text: qsTr("+")
                }

                AppButton {
                    onClicked: focusMode.zoom = 1.0
                    text: qsTr("100%")
                }

                Item {
                    Layout.fillWidth: true
                }

                AppButton {
                    objectName: "plotFocusModeCloseButton"
                    onClicked: focusMode.close()
                    text: qsTr("Close")
                }
            }
        }
    }
}
