pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Carnopy

Card {
    id: root

    required property var desktopController
    required property var draft
    property string attentionField: ""
    property int attentionRow: -1
    property int attentionSerial: 0
    property bool locked: false

    signal cancelRequested
    signal commitRequested

    function focusField(field, row) {
        let target = nameField;
        if (field.endsWith(".kind"))
            target = kindChoice;
        else if (field.endsWith(".fluid"))
            target = fluidChoice;
        else if (field.endsWith(".property"))
            target = propertyChoice;
        else if (field.endsWith(".x"))
            target = xChoice;
        else if (field.endsWith(".group_by"))
            target = groupChoice;
        else if (field.endsWith(".models"))
            target = explicitModels;
        else if (field.endsWith(".delta_metric"))
            target = deltaMetricChoice;
        else if (field.endsWith(".value_scale"))
            target = valueScaleChoice;
        else if (field.endsWith(".format"))
            target = formatChoice;
        else if (field.endsWith(".filters")) {
            filtersEditor.focusRow(row);
            return;
        }
        target.forceActiveFocus();
    }

    onAttentionSerialChanged: Qt.callLater(function () {
        root.focusField(root.attentionField, root.attentionRow);
    })

    Layout.fillWidth: true
    meta: root.draft.locallyValid ? qsTr("Ready to commit") : qsTr("Needs attention")
    metaColor: root.draft.locallyValid ? Theme.success : Theme.danger
    objectName: "comparisonPlotEditor"
    subtitle: qsTr(
                  "Edits stay temporary until Commit. Save, Plan, and Execute never include this draft implicitly.")
    title: qsTr("Comparison plot draft")

    ValidationIssue {
        Layout.fillWidth: true
        field: root.draft.firstInvalidField
        issue: root.draft.issue
        objectName: "comparisonPlotEditorIssue"
    }

    GridLayout {
        Layout.fillWidth: true
        columnSpacing: Theme.spacingMedium
        columns: width >= 680 ? 2 : 1
        rowSpacing: Theme.spacingSmall

        ColumnLayout {
            Layout.fillWidth: true

            Label {
                color: Theme.textMuted
                font.family: Theme.sansFamily
                font.pixelSize: 11
                text: qsTr("Unique name")
            }

            TextField {
                id: nameField

                Accessible.name: qsTr("Comparison plot name")
                Layout.fillWidth: true
                enabled: !root.locked
                objectName: "comparisonPlotName"
                onEditingFinished: root.desktopController.requestSweepComparisonFieldChange(
                                       root.draft, "name", text)
                selectByMouse: true
                text: root.draft.name
            }
        }

        ColumnLayout {
            Layout.fillWidth: true

            Label {
                color: Theme.textMuted
                font.family: Theme.sansFamily
                font.pixelSize: 11
                text: qsTr("Kind")
            }

            AppComboBox {
                id: kindChoice

                Accessible.name: qsTr("Comparison plot kind")
                Layout.fillWidth: true
                currentIndex: indexForRoleValue(root.draft.kind)
                enabled: !root.locked
                model: root.draft.kindChoices
                objectName: "comparisonPlotKind"
                onActivated: root.desktopController.requestSweepComparisonFieldChange(root.draft,
                                                                                      "kind", String(
                                                                                          currentValue))
            }
        }

        ColumnLayout {
            Layout.fillWidth: true

            Label {
                color: Theme.textMuted
                font.family: Theme.sansFamily
                font.pixelSize: 11
                text: qsTr("Fluid")
            }

            AppComboBox {
                id: fluidChoice

                Accessible.name: qsTr("Comparison plot fluid")
                Layout.fillWidth: true
                currentIndex: indexForRoleValue(root.draft.fluid)
                enabled: !root.locked
                model: root.draft.fluidChoices
                objectName: "comparisonPlotFluid"
                onActivated: root.desktopController.requestSweepComparisonFieldChange(root.draft,
                                                                                      "fluid", String(
                                                                                          currentValue))
            }
        }

        ColumnLayout {
            Layout.fillWidth: true

            Label {
                color: Theme.textMuted
                font.family: Theme.sansFamily
                font.pixelSize: 11
                text: qsTr("Property")
            }

            AppComboBox {
                id: propertyChoice

                Accessible.name: qsTr("Comparison plot property")
                Layout.fillWidth: true
                currentIndex: indexForRoleValue(root.draft.propertyName)
                enabled: !root.locked
                model: root.draft.propertyChoices
                objectName: "comparisonPlotProperty"
                onActivated: root.desktopController.requestSweepComparisonFieldChange(root.draft,
                                                                                      "property",
                                                                                      String(currentValue))
            }
        }

        ColumnLayout {
            Layout.fillWidth: true

            Label {
                color: Theme.textMuted
                font.family: Theme.sansFamily
                font.pixelSize: 11
                text: qsTr("X coordinate")
            }

            AppComboBox {
                id: xChoice

                Accessible.name: qsTr("Comparison plot X coordinate")
                Layout.fillWidth: true
                currentIndex: indexForRoleValue(root.draft.xField)
                enabled: !root.locked
                model: root.draft.xChoices
                objectName: "comparisonPlotX"
                onActivated: root.desktopController.requestSweepComparisonFieldChange(root.draft,
                                                                                      "x", String(
                                                                                          currentValue))
            }
        }

        ColumnLayout {
            Layout.fillWidth: true

            Label {
                color: Theme.textMuted
                font.family: Theme.sansFamily
                font.pixelSize: 11
                text: qsTr("Group by")
            }

            AppComboBox {
                id: groupChoice

                Accessible.name: qsTr("Comparison plot grouping")
                Layout.fillWidth: true
                currentIndex: indexForRoleValue(root.draft.groupBy)
                enabled: !root.locked
                model: root.draft.groupByChoices
                objectName: "comparisonPlotGroupBy"
                onActivated: root.desktopController.requestSweepComparisonFieldChange(root.draft,
                                                                                      "group_by",
                                                                                      String(currentValue))
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            visible: root.draft.kind === "property_delta"

            Label {
                color: Theme.textMuted
                font.family: Theme.sansFamily
                font.pixelSize: 11
                text: qsTr("Delta metric")
            }

            AppComboBox {
                id: deltaMetricChoice

                Accessible.name: qsTr("Comparison delta metric")
                Layout.fillWidth: true
                currentIndex: indexForRoleValue(root.draft.deltaMetric)
                enabled: !root.locked
                model: root.draft.deltaMetricChoices
                objectName: "comparisonPlotDeltaMetric"
                onActivated: root.desktopController.requestSweepComparisonFieldChange(root.draft,
                                                                                      "delta_metric",
                                                                                      String(currentValue))
            }
        }

        ColumnLayout {
            Layout.fillWidth: true

            Label {
                color: Theme.textMuted
                font.family: Theme.sansFamily
                font.pixelSize: 11
                text: qsTr("Value scale")
            }

            AppComboBox {
                id: valueScaleChoice

                Accessible.name: qsTr("Comparison value scale")
                Layout.fillWidth: true
                currentIndex: indexForRoleValue(root.draft.valueScale)
                enabled: !root.locked
                model: root.draft.scaleChoices
                objectName: "comparisonPlotValueScale"
                onActivated: root.desktopController.requestSweepComparisonFieldChange(root.draft,
                                                                                      "value_scale",
                                                                                      String(currentValue))
            }
        }

        ColumnLayout {
            Layout.fillWidth: true

            Label {
                color: Theme.textMuted
                font.family: Theme.sansFamily
                font.pixelSize: 11
                text: qsTr("Per-plot format override")
            }

            AppComboBox {
                id: formatChoice

                Accessible.name: qsTr("Comparison plot format override")
                Layout.fillWidth: true
                currentIndex: indexForRoleValue(root.draft.outputFormat)
                enabled: !root.locked
                model: root.draft.formatChoices
                objectName: "comparisonPlotFormat"
                onActivated: root.desktopController.requestSweepComparisonFieldChange(root.draft,
                                                                                      "format", String(
                                                                                          currentValue))
            }
        }
    }

    CheckBox {
        id: explicitModels

        Accessible.description: qsTr("Otherwise every selected non-reference model is included")
        Accessible.name: qsTr("Choose an explicit comparison model subset")
        checked: root.draft.explicitModels
        enabled: !root.locked
        objectName: "comparisonPlotExplicitModels"
        onClicked: root.desktopController.requestSweepComparisonExplicitModels(root.draft, checked)
        text: qsTr("Use an explicit model subset")
    }

    Flow {
        Layout.fillWidth: true
        spacing: Theme.spacingSmall
        visible: root.draft.explicitModels

        Repeater {
            model: root.draft.modelChoices

            delegate: Item {
                required property bool compatible
                required property string display
                required property string issue
                required property bool selected
                required property string value

                implicitHeight: modelCheck.implicitHeight
                implicitWidth: modelCheck.implicitWidth

                CheckBox {
                    id: modelCheck

                    Accessible.description: parent.issue
                    Accessible.name: qsTr("Include %1 in comparison").arg(parent.display)
                    checked: parent.selected
                    enabled: !root.locked && parent.compatible
                    objectName: "comparisonPlotModel-" + parent.value
                    onClicked: root.desktopController.requestSweepComparisonModelSelection(
                                   root.draft, parent.value, checked)
                    text: parent.display
                }
            }
        }
    }

    MappingEditor {
        id: filtersEditor

        Layout.fillWidth: true
        emptyText: qsTr("No row filters configured")
        locked: root.locked
        mappingModel: root.draft.filtersModel
        noun: qsTr("comparison filter")
        objectName: "comparisonPlotFilters"
        onAddRequested: model => root.desktopController.requestSweepComparisonFilterAdd(model)
        onFieldChangeRequested: (model, row, field)
                                => root.desktopController.requestSweepComparisonFilterFieldChange(
                                       model, row, field)
        onRemoveRequested: (model, row) => root.desktopController.requestSweepComparisonFilterRemove(
                                               model, row)
        onValueChangeRequested: (model, row, value)
                                => root.desktopController.requestSweepComparisonFilterValueChange(
                                       model, row, value)
    }

    RowLayout {
        Layout.fillWidth: true

        Item {
            Layout.fillWidth: true
        }

        AppButton {
            enabled: !root.locked
            objectName: "comparisonPlotCancelButton"
            onClicked: root.cancelRequested()
            text: qsTr("Cancel")
        }

        AppButton {
            enabled: !root.locked && root.draft.locallyValid
            objectName: "comparisonPlotCommitButton"
            onClicked: root.commitRequested()
            text: qsTr("Commit")
            tone: "primary"
        }
    }
}
