pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Carnopy

Item {
    id: root

    required property var draft
    property string attentionField: ""
    property int attentionRow: -1
    property int attentionSerial: 0
    property string cancelActionText: qsTr("Cancel")
    property string primaryActionText: qsTr("Commit plot")

    signal cancelRequested
    signal commitRequested
    signal fieldChangeRequested(var draft, string field, string value)
    signal fluidSelectionRequested(var draft, string value, bool selected)
    signal mappingAddRequested(var model)
    signal mappingFieldChangeRequested(var model, int row, string field)
    signal mappingRemoveRequested(var model, int row)
    signal mappingValueChangeRequested(var model, int row, string value)

    function applicable(field) {
        return draft !== null && draft !== undefined && draft.applicableFields.indexOf(field) >= 0;
    }

    function focusField(field, row) {
        if (field === "plot.name")
            nameField.forceActiveFocus();
        else if (field === "plot.kind")
            kindBox.forceActiveFocus();
        else if (field === "plot.property")
            propertyBox.forceActiveFocus();
        else if (field === "plot.x")
            xBox.forceActiveFocus();
        else if (field === "plot.y")
            yBox.forceActiveFocus();
        else if (field === "plot.group_by")
            groupBox.forceActiveFocus();
        else if (field === "plot.filters")
            filterEditor.focusRow(row);
        else if (field === "plot.series")
            seriesEditor.focusRow(row);
        else if (field === "plot.display_units")
            displayUnitEditor.focusRow(row);
        else
            commitButton.forceActiveFocus();
    }

    onAttentionSerialChanged: Qt.callLater(function () {
        root.focusField(root.attentionField, root.attentionRow);
    })

    implicitHeight: content.implicitHeight

    ColumnLayout {
        id: content

        anchors.left: parent.left
        anchors.right: parent.right
        spacing: Theme.spacingMedium

        GridLayout {
            Layout.fillWidth: true
            columns: root.width >= 760 ? 4 : 2
            columnSpacing: Theme.spacingMedium
            rowSpacing: Theme.spacingSmall

            Label {
                color: Theme.textMuted
                font.family: Theme.sansFamily
                font.pixelSize: 12
                text: qsTr("Name")
            }

            TextField {
                id: nameField

                Accessible.name: qsTr("Plot name")
                Layout.fillWidth: true
                color: Theme.text
                font.family: Theme.monoFamily
                font.pixelSize: 12
                objectName: "plotNameField"
                onEditingFinished: root.fieldChangeRequested(root.draft, "name", text)
                selectByMouse: true
                text: root.draft === null ? "" : root.draft.name
            }

            Label {
                color: Theme.textMuted
                font.family: Theme.sansFamily
                font.pixelSize: 12
                text: qsTr("Kind")
            }

            AppComboBox {
                id: kindBox

                Accessible.name: qsTr("Plot kind")
                Layout.fillWidth: true
                currentIndex: root.draft === null ? -1 : indexOfValue(root.draft.kind)
                model: root.draft === null ? null : root.draft.kindChoices
                objectName: "plotKindBox"
                onActivated: root.fieldChangeRequested(root.draft, "kind", String(currentValue))
                textRole: "display"
                valueRole: "value"
            }

            Label {
                color: Theme.textMuted
                font.family: Theme.sansFamily
                font.pixelSize: 12
                text: qsTr("Property")
                visible: root.applicable("property")
            }

            AppComboBox {
                id: propertyBox

                Accessible.name: qsTr("Plot property")
                Layout.fillWidth: true
                currentIndex: root.draft === null ? -1 : indexOfValue(root.draft.propertyName)
                model: root.draft === null ? null : root.draft.propertyChoices
                objectName: "plotPropertyBox"
                onActivated: root.fieldChangeRequested(root.draft, "property", String(currentValue))
                textRole: "display"
                valueRole: "value"
                visible: root.applicable("property")
            }

            Label {
                color: Theme.textMuted
                font.family: Theme.sansFamily
                font.pixelSize: 12
                text: qsTr("X axis")
                visible: root.applicable("x")
            }

            AppComboBox {
                id: xBox

                Accessible.name: qsTr("Plot X axis")
                Layout.fillWidth: true
                currentIndex: root.draft === null ? -1 : indexOfValue(root.draft.xField)
                model: root.draft === null ? null : root.draft.axisChoices
                objectName: "plotXFieldBox"
                onActivated: root.fieldChangeRequested(root.draft, "x", String(currentValue))
                textRole: "display"
                valueRole: "value"
                visible: root.applicable("x")
            }

            Label {
                color: Theme.textMuted
                font.family: Theme.sansFamily
                font.pixelSize: 12
                text: qsTr("Y axis")
                visible: root.applicable("y")
            }

            AppComboBox {
                id: yBox

                Accessible.name: qsTr("Plot Y axis")
                Layout.fillWidth: true
                currentIndex: root.draft === null ? -1 : indexOfValue(root.draft.yField)
                model: root.draft === null ? null : root.draft.axisChoices
                objectName: "plotYFieldBox"
                onActivated: root.fieldChangeRequested(root.draft, "y", String(currentValue))
                textRole: "display"
                valueRole: "value"
                visible: root.applicable("y")
            }

            Label {
                color: Theme.textMuted
                font.family: Theme.sansFamily
                font.pixelSize: 12
                text: qsTr("Group by")
                visible: root.applicable("group_by")
            }

            AppComboBox {
                id: groupBox

                Accessible.name: qsTr("Plot group field")
                Layout.fillWidth: true
                currentIndex: root.draft === null ? -1 : indexOfValue(root.draft.groupBy)
                model: root.draft === null ? null : root.draft.groupChoices
                objectName: "plotGroupFieldBox"
                onActivated: root.fieldChangeRequested(root.draft, "group_by", String(currentValue))
                textRole: "display"
                valueRole: "value"
                visible: root.applicable("group_by")
            }

            Label {
                color: Theme.textMuted
                font.family: Theme.sansFamily
                font.pixelSize: 12
                text: qsTr("Value scale")
                visible: root.applicable("value_scale")
            }

            AppComboBox {
                Accessible.name: qsTr("Plot value scale")
                Layout.fillWidth: true
                currentIndex: root.draft === null ? -1 : indexOfValue(root.draft.valueScale)
                model: root.draft === null ? null : root.draft.scaleChoices
                onActivated: root.fieldChangeRequested(root.draft, "value_scale", String(
                                                           currentValue))
                textRole: "display"
                valueRole: "value"
                visible: root.applicable("value_scale")
            }

            Label {
                color: Theme.textMuted
                font.family: Theme.sansFamily
                font.pixelSize: 12
                text: qsTr("Color scale")
                visible: root.applicable("color_scale")
            }

            AppComboBox {
                Accessible.name: qsTr("Plot color scale")
                Layout.fillWidth: true
                currentIndex: root.draft === null ? -1 : indexOfValue(root.draft.colorScale)
                model: root.draft === null ? null : root.draft.scaleChoices
                onActivated: root.fieldChangeRequested(root.draft, "color_scale", String(
                                                           currentValue))
                textRole: "display"
                valueRole: "value"
                visible: root.applicable("color_scale")
            }

            Label {
                color: Theme.textMuted
                font.family: Theme.sansFamily
                font.pixelSize: 12
                text: qsTr("X scale")
                visible: root.applicable("x_scale")
            }

            AppComboBox {
                Accessible.name: qsTr("Plot X scale")
                Layout.fillWidth: true
                currentIndex: root.draft === null ? -1 : indexOfValue(root.draft.xScale)
                model: root.draft === null ? null : root.draft.scaleChoices
                onActivated: root.fieldChangeRequested(root.draft, "x_scale", String(currentValue))
                textRole: "display"
                valueRole: "value"
                visible: root.applicable("x_scale")
            }

            Label {
                color: Theme.textMuted
                font.family: Theme.sansFamily
                font.pixelSize: 12
                text: qsTr("Y scale")
                visible: root.applicable("y_scale")
            }

            AppComboBox {
                Accessible.name: qsTr("Plot Y scale")
                Layout.fillWidth: true
                currentIndex: root.draft === null ? -1 : indexOfValue(root.draft.yScale)
                model: root.draft === null ? null : root.draft.scaleChoices
                onActivated: root.fieldChangeRequested(root.draft, "y_scale", String(currentValue))
                textRole: "display"
                valueRole: "value"
                visible: root.applicable("y_scale")
            }

            Label {
                color: Theme.textMuted
                font.family: Theme.sansFamily
                font.pixelSize: 12
                text: qsTr("Format override")
                visible: root.applicable("format")
            }

            RowLayout {
                Layout.fillWidth: true
                visible: root.applicable("format")

                AppComboBox {
                    Accessible.name: qsTr("Plot format override")
                    Layout.fillWidth: true
                    currentIndex: root.draft === null ? -1 : indexOfValue(root.draft.outputFormat)
                    model: root.draft === null ? null : root.draft.formatChoices
                    onActivated: root.fieldChangeRequested(root.draft, "format", String(
                                                               currentValue))
                    textRole: "display"
                    valueRole: "value"
                }

                AppButton {
                    Accessible.description: qsTr("Remove the per-plot format override")
                    compact: true
                    enabled: root.draft !== null && root.draft.outputFormat.length > 0
                    objectName: "plotFormatInheritButton"
                    onClicked: root.fieldChangeRequested(root.draft, "format", "")
                    text: qsTr("Inherit")
                }
            }
        }

        ChoiceList {
            Layout.fillWidth: true
            allowMove: false
            choiceModel: root.draft === null ? null : root.draft.fluidChoices
            emptyText: qsTr("No per-plot fluid override; shared fluids are inherited.")
            noun: qsTr("plot fluid")
            objectName: "plotFluidList"
            onAddRequested: value => root.fluidSelectionRequested(root.draft, value, true)
            onRemoveValueRequested: (row, value) => root.fluidSelectionRequested(root.draft, value,
                                                                                 false)
            selectedModel: root.draft === null ? null : root.draft.selectedFluids
            visible: root.applicable("fluids")
        }

        MappingEditor {
            id: filterEditor

            Layout.fillWidth: true
            emptyText: qsTr("No per-plot filters; shared filters are inherited.")
            mappingModel: root.draft === null || root.draft === undefined ? null :
                                                                            root.draft.filters

            noun: qsTr("plot filter")
            objectName: "plotFilterEditor"
            onAddRequested: model => root.mappingAddRequested(model)
            onFieldChangeRequested: (model, row, field) => root.mappingFieldChangeRequested(model,
                                                                                            row, field)
            onRemoveRequested: (model, row) => root.mappingRemoveRequested(model, row)
            onValueChangeRequested: (model, row, value) => root.mappingValueChangeRequested(model,
                                                                                            row, value)
            visible: root.applicable("filters")
        }

        MappingEditor {
            id: seriesEditor

            Layout.fillWidth: true
            emptyText: qsTr("No explicit series selections.")
            mappingModel: root.draft === null || root.draft === undefined ? null : root.draft.series
            noun: qsTr("series")
            objectName: "plotSeriesEditor"
            onAddRequested: model => root.mappingAddRequested(model)
            onFieldChangeRequested: (model, row, field) => root.mappingFieldChangeRequested(model,
                                                                                            row, field)
            onRemoveRequested: (model, row) => root.mappingRemoveRequested(model, row)
            onValueChangeRequested: (model, row, value) => root.mappingValueChangeRequested(model,
                                                                                            row, value)
            visible: root.applicable("series")
        }

        MappingEditor {
            id: displayUnitEditor

            Layout.fillWidth: true
            emptyText: qsTr("No per-plot display-unit overrides.")
            mappingModel: root.draft === null || root.draft === undefined ? null :
                                                                            root.draft.displayUnitRows

            noun: qsTr("display unit")
            objectName: "plotDisplayUnitEditor"
            onAddRequested: model => root.mappingAddRequested(model)
            onFieldChangeRequested: (model, row, field) => root.mappingFieldChangeRequested(model,
                                                                                            row, field)
            onRemoveRequested: (model, row) => root.mappingRemoveRequested(model, row)
            onValueChangeRequested: (model, row, value) => root.mappingValueChangeRequested(model,
                                                                                            row, value)
            visible: root.applicable("display_units")
        }

        ValidationIssue {
            Layout.fillWidth: true
            field: root.draft === null ? "" : root.draft.firstInvalidField
            issue: root.draft === null ? "" : root.draft.issue
        }

        RowLayout {
            Layout.fillWidth: true

            Item {
                Layout.fillWidth: true
            }

            AppButton {
                objectName: "plotCancelButton"
                onClicked: root.cancelRequested()
                text: root.cancelActionText
            }

            AppButton {
                id: commitButton

                objectName: "plotCommitButton"
                onClicked: root.commitRequested()
                text: root.primaryActionText
                tone: "primary"
            }
        }
    }
}
