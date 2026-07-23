pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Carnopy

Item {
    id: root

    required property var configController

    signal attentionRequested(string section, string field, int row)
    signal copyCompleted

    ColumnLayout {
        anchors.fill: parent
        anchors.leftMargin: 24
        anchors.rightMargin: 24
        anchors.topMargin: 24
        anchors.bottomMargin: 24
        spacing: Theme.spacingMedium

        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.spacingMedium

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 3

                Label {
                    Layout.fillWidth: true
                    color: Theme.text
                    font.family: Theme.sansFamily
                    font.pixelSize: 23
                    font.weight: Font.DemiBold
                    text: qsTr("YAML preview")
                }

                Label {
                    Layout.fillWidth: true
                    color: Theme.textMuted
                    elide: Text.ElideMiddle
                    font.family: Theme.monoFamily
                    font.pixelSize: 11
                    text: root.configController.fileDisplay
                }
            }

            StatusBadge {
                label: !root.configController.yamlAvailable ? qsTr("Unavailable") : (
                                                                  root.configController.dirty ? qsTr(
                                                                                                    "Unsaved") :
                                                                                                qsTr("Saved"))
                tone: !root.configController.yamlAvailable ? "danger" : (
                                                                 root.configController.dirty
                                                                 ? "warning" : "success")
            }
        }

        Label {
            Layout.fillWidth: true
            color: Theme.textMuted
            font.family: Theme.sansFamily
            font.pixelSize: 12
            text: qsTr(
                      "This read-only document is the exact deterministic YAML sent to the worker before Save.")
            wrapMode: Text.Wrap
        }

        BlockingBanner {
            Layout.fillWidth: true
            field: root.configController.blockingField
            message: root.configController.blockingIssue.length > 0
                     ? root.configController.blockingIssue : qsTr(
                           "Create or import a dataset configuration to make YAML available.")
            objectName: "yamlBlockingBanner"
            onActionRequested: (section, field, row) => root.attentionRequested(section, field, row)
            row: root.configController.blockingRow
            section: root.configController.blockingSection
            title: root.configController.hasDocument ? qsTr("YAML is unavailable") : qsTr(
                                                           "No configuration is open")
            visible: !root.configController.yamlAvailable
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.spacingSmall
            visible: root.configController.yamlAvailable

            TextField {
                id: searchField

                Accessible.name: qsTr("Search YAML")
                Layout.fillWidth: true
                objectName: "yamlSearchField"
                onAccepted: yamlViewer.findNext(text)
                placeholderText: qsTr("Search YAML")
            }

            AppButton {
                objectName: "yamlFindNextButton"
                onClicked: yamlViewer.findNext(searchField.text)
                text: qsTr("Find next")
            }

            AppButton {
                objectName: "yamlCopyButton"
                onClicked: {
                    yamlViewer.copyAll();
                    root.copyCompleted();
                }
                text: qsTr("Copy all")
            }
        }

        LineNumberedTextArea {
            id: yamlViewer

            Layout.fillHeight: true
            Layout.fillWidth: true
            Layout.minimumHeight: 240
            objectName: "yamlLineNumberedText"
            text: root.configController.yamlPreview
            visible: root.configController.yamlAvailable
        }

        Item {
            Layout.fillHeight: true
            visible: !root.configController.yamlAvailable
        }
    }
}
