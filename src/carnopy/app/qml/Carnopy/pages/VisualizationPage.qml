pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Carnopy

Item {
    id: root

    required property var visualizationDraft
    property string attentionField: ""
    property int attentionRow: -1
    property int attentionSerial: 0
    property int expectedColumns: 1

    signal addPlotRequested
    signal cancelPlotRequested
    signal commitPlotRequested
    signal editPlotRequested(int row)
    signal enabledChangeRequested(bool enabled)
    signal fluidSelectionRequested(string value, bool selected)
    signal formatChangeRequested(string format)
    signal mappingAddRequested(var model)
    signal mappingFieldChangeRequested(var model, int row, string field)
    signal mappingRemoveRequested(var model, int row)
    signal mappingValueChangeRequested(var model, int row, string value)
    signal movePlotRequested(int row, int offset)
    signal plotFieldChangeRequested(var draft, string field, string value)
    signal plotFluidSelectionRequested(var draft, string value, bool selected)
    signal removePlotRequested(int row)

    function focusField(field, row) {
        if (field.indexOf("plot.") === 0 && activePlotEditor.visible) {
            activePlotEditor.focusField(field, row);
            return;
        }
        if (field === "visualization.enabled")
            enabledSwitch.forceActiveFocus();
        else if (field === "visualization.format")
            formatBox.forceActiveFocus();
        else if (field === "visualization.filters")
            sharedFilterEditor.focusRow(row);
        else if (field === "visualization.display_units")
            sharedDisplayUnitEditor.focusRow(row);
        else if (field === "visualization.plots") {
            if (row >= 0)
                plotList.positionViewAtIndex(row, ListView.Contain);
            addPlotButton.forceActiveFocus();
        } else
            enabledSwitch.forceActiveFocus();
    }

    onAttentionSerialChanged: Qt.callLater(function () {
        root.focusField(root.attentionField, root.attentionRow);
    })

    Flickable {
        anchors.fill: parent
        boundsBehavior: Flickable.StopAtBounds
        clip: true
        contentHeight: pageColumn.implicitHeight + 40
        contentWidth: width
        flickableDirection: Flickable.VerticalFlick
        objectName: "visualizationPageFlickable"
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
            spacing: Theme.spacingMedium

            Label {
                Layout.fillWidth: true
                color: Theme.text
                font.family: Theme.sansFamily
                font.pixelSize: 22
                font.weight: Font.DemiBold
                text: qsTr("Configured visualization")
            }

            Label {
                Layout.fillWidth: true
                color: Theme.textMuted
                font.family: Theme.sansFamily
                font.pixelSize: 12
                text: qsTr(
                          "Define reproducible views of emitted dataset columns. Rendering remains worker-owned and does not run in this QML process.")
                wrapMode: Text.Wrap
            }

            Card {
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                subtitle: root.visualizationDraft.hasActivePlotEdit ? qsTr(
                                                                          "Commit or cancel the temporary plot before changing shared settings.") :
                                                                      qsTr("Disabled visualization keeps its latent settings and plot requests without affecting dataset validity.")
                title: qsTr("Shared visualization settings")

                RowLayout {
                    Layout.fillWidth: true

                    Switch {
                        id: enabledSwitch

                        Accessible.name: qsTr("Enable configured visualization")
                        checked: root.visualizationDraft.enabled
                        enabled: !root.visualizationDraft.hasActivePlotEdit
                        objectName: "visualizationEnabledSwitch"
                        onToggled: root.enabledChangeRequested(checked)
                        text: checked ? qsTr("Enabled") : qsTr("Disabled")
                    }

                    Item {
                        Layout.fillWidth: true
                    }

                    StatusBadge {
                        label: !root.visualizationDraft.enabled ? qsTr("Latent") : (
                                                                      root.visualizationDraft.locallyValid
                                                                      ? qsTr("Locally complete") :
                                                                        qsTr("Needs attention"))
                        tone: !root.visualizationDraft.enabled ? "neutral" : (
                                                                     root.visualizationDraft.locallyValid
                                                                     ? "success" : "danger")
                    }
                }

                GridLayout {
                    id: sharedSettingsGrid

                    Layout.fillWidth: true
                    columnSpacing: Theme.spacingMedium
                    columns: root.expectedColumns >= 3 && width >= 980 ? 2 : 1
                    enabled: root.visualizationDraft.enabled &&
                             !root.visualizationDraft.hasActivePlotEdit
                    objectName: "visualizationSharedSettingsGrid"
                    rowSpacing: Theme.spacingMedium
                    uniformCellWidths: true

                    ColumnLayout {
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0
                        objectName: "visualizationSharedPrimaryColumn"
                        spacing: Theme.spacingSmall

                        Label {
                            color: Theme.textMuted
                            font.family: Theme.sansFamily
                            font.pixelSize: 12
                            text: qsTr("Shared output format")
                        }

                        AppComboBox {
                            id: formatBox

                            Accessible.name: qsTr("Shared visualization format")
                            Layout.fillWidth: true
                            currentIndex: indexOfValue(root.visualizationDraft.format)
                            model: root.visualizationDraft.formatChoices
                            objectName: "visualizationFormatBox"
                            onActivated: root.formatChangeRequested(String(currentValue))
                            textRole: "display"
                            valueRole: "value"
                        }

                        ChoiceList {
                            Layout.fillWidth: true
                            allowMove: false
                            choiceModel: root.visualizationDraft.fluidChoices
                            emptyText: qsTr(
                                           "No shared fluid override; every dataset fluid is eligible.")
                            noun: qsTr("shared fluid")
                            objectName: "visualizationFluidList"
                            onAddRequested: value => root.fluidSelectionRequested(value, true)
                            onRemoveValueRequested: (row, value) => root.fluidSelectionRequested(
                                                                        value, false)
                            selectedModel: root.visualizationDraft.selectedFluids
                        }
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0
                        objectName: "visualizationSharedMappingsColumn"
                        spacing: Theme.spacingMedium

                        MappingEditor {
                            id: sharedFilterEditor

                            Layout.fillWidth: true
                            Layout.minimumWidth: 0
                            emptyText: qsTr("No shared filters.")
                            mappingModel: root.visualizationDraft.filterRows
                            noun: qsTr("shared filter")
                            objectName: "visualizationFilterEditor"
                            onAddRequested: model => root.mappingAddRequested(model)
                            onFieldChangeRequested: (model, row, field)
                                                    => root.mappingFieldChangeRequested(model, row,
                                                                                        field)
                            onRemoveRequested: (model, row) => root.mappingRemoveRequested(model,
                                                                                           row)
                            onValueChangeRequested: (model, row, value)
                                                    => root.mappingValueChangeRequested(model, row,
                                                                                        value)
                        }

                        MappingEditor {
                            id: sharedDisplayUnitEditor

                            Layout.fillWidth: true
                            Layout.minimumWidth: 0
                            emptyText: qsTr("No shared display-unit overrides.")
                            mappingModel: root.visualizationDraft.displayUnitRows
                            noun: qsTr("shared display unit")
                            objectName: "visualizationDisplayUnitEditor"
                            onAddRequested: model => root.mappingAddRequested(model)
                            onFieldChangeRequested: (model, row, field)
                                                    => root.mappingFieldChangeRequested(model, row,
                                                                                        field)
                            onRemoveRequested: (model, row) => root.mappingRemoveRequested(model,
                                                                                           row)
                            onValueChangeRequested: (model, row, value)
                                                    => root.mappingValueChangeRequested(model, row,
                                                                                        value)
                        }
                    }
                }
            }

            Card {
                Layout.fillWidth: true
                subtitle: qsTr(
                              "Plot order is deterministic. Each durable row is a payload snapshot; only the open editor owns a temporary PlotDraft.")
                title: qsTr("Plot requests")

                ListView {
                    id: plotList

                    Accessible.name: qsTr("Configured plot requests")
                    Layout.fillWidth: true
                    Layout.preferredHeight: Math.max(56, Math.min(280, contentHeight))
                    boundsBehavior: Flickable.StopAtBounds
                    clip: true
                    interactive: contentHeight > height
                    model: root.visualizationDraft.plots
                    objectName: "visualizationPlotList"
                    pixelAligned: true
                    spacing: Theme.spacingTiny

                    ScrollBar.vertical: ScrollBar {
                        policy: ScrollBar.AsNeeded
                    }

                    delegate: Rectangle {
                        id: plotRow

                        required property bool compatible
                        required property string display
                        required property int index
                        required property string issue
                        required property string kind
                        required property string name

                        border.color: compatible ? Theme.border : Theme.danger
                        border.width: 1
                        color: Theme.surfaceRaised
                        height: issue.length > 0 ? 82 : 52
                        radius: Theme.radiusSmall
                        width: ListView.view.width

                        ColumnLayout {
                            anchors.fill: parent
                            anchors.leftMargin: 10
                            anchors.rightMargin: 6
                            anchors.topMargin: 6
                            anchors.bottomMargin: 6
                            spacing: Theme.spacingTiny

                            RowLayout {
                                Layout.fillWidth: true

                                Label {
                                    Layout.fillWidth: true
                                    color: Theme.text
                                    elide: Text.ElideRight
                                    font.family: Theme.sansFamily
                                    font.pixelSize: 12
                                    font.weight: Font.Medium
                                    text: plotRow.display
                                }

                                AppButton {
                                    enabled: root.visualizationDraft.enabled &&
                                             !root.visualizationDraft.hasActivePlotEdit
                                    objectName: "visualizationEditPlot-" + plotRow.index
                                    onClicked: root.editPlotRequested(plotRow.index)
                                    text: qsTr("Edit")
                                }

                                AppButton {
                                    enabled: root.visualizationDraft.enabled &&
                                             !root.visualizationDraft.hasActivePlotEdit
                                             && plotRow.index > 0
                                    objectName: "visualizationMoveUpPlot-" + plotRow.index
                                    onClicked: root.movePlotRequested(plotRow.index, -1)
                                    text: qsTr("Up")
                                }

                                AppButton {
                                    enabled: root.visualizationDraft.enabled &&
                                             !root.visualizationDraft.hasActivePlotEdit
                                             && plotRow.index + 1 < plotList.count
                                    objectName: "visualizationMoveDownPlot-" + plotRow.index
                                    onClicked: root.movePlotRequested(plotRow.index, 1)
                                    text: qsTr("Down")
                                }

                                AppButton {
                                    enabled: root.visualizationDraft.enabled &&
                                             !root.visualizationDraft.hasActivePlotEdit
                                    objectName: "visualizationRemovePlot-" + plotRow.index
                                    onClicked: root.removePlotRequested(plotRow.index)
                                    text: qsTr("Remove")
                                }
                            }

                            Label {
                                Layout.fillWidth: true
                                color: Theme.danger
                                font.family: Theme.sansFamily
                                font.pixelSize: 11
                                text: plotRow.issue
                                visible: plotRow.issue.length > 0
                                wrapMode: Text.Wrap
                            }
                        }
                    }

                    Label {
                        anchors.centerIn: parent
                        color: Theme.textMuted
                        font.family: Theme.sansFamily
                        font.pixelSize: 12
                        text: qsTr("No configured plots")
                        visible: plotList.count === 0
                    }
                }

                AppButton {
                    id: addPlotButton

                    enabled: root.visualizationDraft.enabled &&
                             !root.visualizationDraft.hasActivePlotEdit
                    objectName: "visualizationAddPlotButton"
                    onClicked: root.addPlotRequested()
                    text: qsTr("Add plot")
                    tone: "primary"
                }
            }

            Card {
                Layout.fillWidth: true
                subtitle: qsTr(
                              "Commit replaces or appends one durable snapshot. Cancel discards only this unresolved temporary edit.")
                title: qsTr("Plot editor")
                visible: root.visualizationDraft.hasActivePlotEdit

                PlotEditor {
                    id: activePlotEditor

                    Layout.fillWidth: true
                    draft: root.visualizationDraft.activePlotDraft
                    objectName: "activePlotEditor"
                    onCancelRequested: root.cancelPlotRequested()
                    onCommitRequested: root.commitPlotRequested()
                    onFieldChangeRequested: (draft, field, value) => root.plotFieldChangeRequested(
                                                                         draft, field, value)
                    onFluidSelectionRequested: (draft, value, selected)
                                               => root.plotFluidSelectionRequested(draft, value,
                                                                                   selected)
                    onMappingAddRequested: model => root.mappingAddRequested(model)
                    onMappingFieldChangeRequested: (model, row, field)
                                                   => root.mappingFieldChangeRequested(model, row,
                                                                                       field)
                    onMappingRemoveRequested: (model, row) => root.mappingRemoveRequested(model,
                                                                                          row)
                    onMappingValueChangeRequested: (model, row, value)
                                                   => root.mappingValueChangeRequested(model, row,
                                                                                       value)
                }
            }

            ValidationIssue {
                Layout.fillWidth: true
                field: root.visualizationDraft.firstInvalidField
                issue: root.visualizationDraft.issue
            }
        }
    }
}
