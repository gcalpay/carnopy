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
    property bool dialogsEnabled: true
    property bool locked: false
    property string pendingKind: ""
    readonly property bool ratioKind: draft.kind === "shuffle" || draft.kind === "stratified_hash"
    readonly property bool holdoutKind: ["coordinate_block", "range_holdout", "leave_fluid_out",
        "phase_holdout", "model_holdout"].indexOf(draft.kind) >= 0
    readonly property bool categoricalHoldoutKind: ["leave_fluid_out", "phase_holdout",
        "model_holdout"].indexOf(draft.kind) >= 0

    signal cancelRequested
    signal commitRequested
    signal kindChangeDialogRequested
    signal scenarioCategoricalHoldoutRequested(var draft, string partition, string values)
    signal scenarioCoordinateHoldoutRequested(var draft, string partition, string field,
                                              string minimum, string maximum)
    signal scenarioFieldChangeRequested(var draft, string field, string value)
    signal scenarioKindChangeRequested(var draft, string kind, bool confirmed)
    signal scenarioNumericBinsRequested(var draft, string field, string boundaries)
    signal scenarioPartitionRequested(var draft, string partition, string ratio)
    signal scenarioRangeHoldoutRequested(var draft, string partition, string minimum,
                                         string maximum)
    signal scenarioRemoveHoldoutRequested(var draft, string partition)
    signal scenarioRemoveNumericBinsRequested(var draft, string field)
    signal scenarioRemovePartitionRequested(var draft, string partition)
    signal scenarioStrataRequested(var draft, string fields)
    signal scenarioTransformationAddRequested(var draft, string field, string methods)
    signal scenarioTransformationMoveRequested(var draft, int source, int destination)
    signal scenarioTransformationRemoveRequested(var draft, int row)

    function focusField(field, row) {
        let target = nameField;
        if (field.endsWith(".kind"))
            target = kindChoice;
        else if (field.endsWith(".seed"))
            target = seedField;
        else if (field.endsWith(".field"))
            target = rangeFieldChoice;
        else if (field.endsWith(".partitions")) {
            partitionsList.currentIndex = row;
            partitionsList.forceActiveFocus();
            return;
        } else if (field.endsWith(".holdouts")) {
            holdoutsList.currentIndex = row;
            holdoutsList.forceActiveFocus();
            return;
        } else if (field.endsWith(".strata"))
            target = strataFields;
        else if (field.endsWith(".transformations")) {
            transformationsList.currentIndex = row;
            transformationsList.forceActiveFocus();
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
    objectName: "preparationScenarioEditor"
    subtitle: qsTr(
                  "Edits stay temporary until Commit. Save, Plan, and Execute never include this draft implicitly.")
    title: qsTr("Preparation scenario draft")

    ValidationIssue {
        Layout.fillWidth: true
        field: root.draft.firstInvalidField
        issue: root.draft.issue
        objectName: "preparationScenarioEditorIssue"
    }

    GridLayout {
        Layout.fillWidth: true
        columnSpacing: Theme.spacingMedium
        columns: width >= 680 ? 2 : 1
        objectName: "preparationScenarioBasicsGrid"
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

                Accessible.name: qsTr("Scenario name")
                Layout.fillWidth: true
                enabled: !root.locked
                objectName: "preparationScenarioName"
                onEditingFinished: root.scenarioFieldChangeRequested(root.draft, "name", text)
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
                text: qsTr("Scenario kind")
            }

            AppComboBox {
                id: kindChoice

                Accessible.name: qsTr("Scenario kind")
                Layout.fillWidth: true
                currentIndex: indexForRoleValue(root.draft.kind)
                enabled: !root.locked
                model: root.draft.kindChoices
                objectName: "preparationScenarioKind"
                onActivated: {
                    const selected = String(currentValue);
                    if (selected === root.draft.kind)
                    return;
                    root.pendingKind = selected;
                    root.kindChangeDialogRequested();
                }
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            visible: root.ratioKind

            Label {
                color: Theme.textMuted
                font.family: Theme.sansFamily
                font.pixelSize: 11
                text: qsTr("Seed")
            }

            TextField {
                id: seedField

                Accessible.name: qsTr("Scenario random seed")
                Layout.fillWidth: true
                enabled: !root.locked
                inputMethodHints: Qt.ImhDigitsOnly
                objectName: "preparationScenarioSeed"
                onEditingFinished: root.scenarioFieldChangeRequested(root.draft, "seed", text)
                selectByMouse: true
                text: root.draft.seedText
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            visible: root.draft.kind === "range_holdout"

            Label {
                color: Theme.textMuted
                font.family: Theme.sansFamily
                font.pixelSize: 11
                text: qsTr("Range field")
            }

            AppComboBox {
                id: rangeFieldChoice

                Accessible.name: qsTr("Range holdout field")
                Layout.fillWidth: true
                currentIndex: indexForRoleValue(root.draft.field)
                enabled: !root.locked
                model: root.draft.fieldChoices
                objectName: "preparationScenarioField"
                onActivated: root.scenarioFieldChangeRequested(root.draft, "field", String(
                                                                   currentValue))
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            visible: root.holdoutKind

            Label {
                color: Theme.textMuted
                font.family: Theme.sansFamily
                font.pixelSize: 11
                text: qsTr("Remainder partition")
            }

            AppComboBox {
                id: remainderChoice

                Accessible.name: qsTr("Scenario remainder partition")
                Layout.fillWidth: true
                currentIndex: indexForRoleValue(root.draft.remainder)
                enabled: !root.locked
                model: ["train", "validation", "test"]
                objectName: "preparationScenarioRemainder"
                onActivated: root.scenarioFieldChangeRequested(root.draft, "remainder", String(
                                                                   currentValue))
            }
        }
    }

    Label {
        Layout.fillWidth: true
        color: Theme.information
        font.family: Theme.sansFamily
        font.pixelSize: 11
        text: qsTr(
                  "Unsplit uses the implied ‘all’ partition and has no held-out partition for fitting transformations.")
        visible: root.draft.kind === "unsplit"
        wrapMode: Text.Wrap
    }

    Card {
        Layout.fillWidth: true
        flat: true
        objectName: "preparationScenarioPartitionsCard"
        subtitle: qsTr(
                      "Partition ratios are deterministic configuration values validated by Carnopy’s public schema.")
        title: qsTr("Partitions")
        visible: root.ratioKind

        ListView {
            id: partitionsList

            Accessible.name: qsTr("Scenario partitions")
            Layout.fillWidth: true
            Layout.preferredHeight: Math.max(44, Math.min(176, contentHeight))
            boundsBehavior: Flickable.StopAtBounds
            clip: true
            model: root.draft.partitionsModel
            objectName: "preparationScenarioPartitions"
            spacing: Theme.spacingTiny

            delegate: RowLayout {
                id: partitionRow

                required property int index
                required property string partition
                required property real ratio

                width: ListView.view.width

                Label {
                    Layout.preferredWidth: 110
                    color: Theme.text
                    font.family: Theme.sansFamily
                    font.pixelSize: 12
                    text: partitionRow.partition
                }

                TextField {
                    Layout.fillWidth: true
                    Accessible.name: qsTr("Ratio for %1 partition").arg(partitionRow.partition)
                    enabled: !root.locked
                    objectName: "preparationScenarioPartitionRatio-" + partitionRow.index
                    onEditingFinished: root.scenarioPartitionRequested(root.draft,
                                                                       partitionRow.partition, text)
                    selectByMouse: true
                    text: String(partitionRow.ratio)
                }

                AppButton {
                    compact: true
                    enabled: !root.locked
                    onClicked: root.scenarioRemovePartitionRequested(root.draft,
                                                                     partitionRow.partition)
                    text: qsTr("Remove")
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true

            AppComboBox {
                id: partitionName

                Accessible.name: qsTr("Partition to add")
                Layout.fillWidth: true
                model: ["train", "validation", "test"]
                objectName: "preparationScenarioPartitionName"
            }

            TextField {
                id: partitionRatio

                Accessible.name: qsTr("Partition ratio")
                Layout.fillWidth: true
                objectName: "preparationScenarioPartitionRatio"
                placeholderText: qsTr("0.2")
                selectByMouse: true
            }

            AppButton {
                enabled: !root.locked
                onClicked: root.scenarioPartitionRequested(root.draft, String(
                                                               partitionName.currentValue),
                                                           partitionRatio.text)
                text: qsTr("Set")
            }
        }
    }

    Card {
        Layout.fillWidth: true
        flat: true
        objectName: "preparationScenarioHoldoutsCard"
        subtitle: root.categoricalHoldoutKind ? qsTr(
                                                    "Enter exact source categories or backend models as comma-separated values.") :
                                                qsTr("Range and coordinate bounds are inclusive scientific configuration values.")
        title: qsTr("Holdouts")
        visible: root.holdoutKind

        ListView {
            id: holdoutsList

            Accessible.name: qsTr("Scenario holdouts")
            Layout.fillWidth: true
            Layout.preferredHeight: Math.max(44, Math.min(176, contentHeight))
            boundsBehavior: Flickable.StopAtBounds
            clip: true
            model: root.draft.holdoutsModel
            objectName: "preparationScenarioHoldouts"
            spacing: Theme.spacingTiny

            delegate: RowLayout {
                id: holdoutRow

                required property int index
                required property string partition
                required property string summary

                width: ListView.view.width

                Label {
                    Layout.preferredWidth: 100
                    color: Theme.text
                    font.family: Theme.sansFamily
                    font.pixelSize: 12
                    text: holdoutRow.partition
                }

                Label {
                    Layout.fillWidth: true
                    color: Theme.textMuted
                    font.family: Theme.monoFamily
                    font.pixelSize: 11
                    text: holdoutRow.summary
                    wrapMode: Text.WrapAnywhere
                }

                AppButton {
                    compact: true
                    enabled: !root.locked
                    onClicked: root.scenarioRemoveHoldoutRequested(root.draft, holdoutRow.partition)
                    text: qsTr("Remove")
                }
            }
        }

        GridLayout {
            Layout.fillWidth: true
            columns: width >= 680 ? 3 : 1

            AppComboBox {
                id: holdoutPartition

                Accessible.name: qsTr("Holdout partition")
                Layout.fillWidth: true
                model: ["validation", "test"]
                objectName: "preparationScenarioHoldoutPartition"
            }

            AppComboBox {
                id: holdoutField

                Accessible.name: qsTr("Coordinate holdout field")
                Layout.fillWidth: true
                model: root.draft.fieldChoices
                objectName: "preparationScenarioHoldoutField"
                visible: root.draft.kind === "coordinate_block"
            }

            TextField {
                id: categoricalValues

                Accessible.name: qsTr("Categorical holdout values")
                Layout.fillWidth: true
                objectName: "preparationScenarioHoldoutValues"
                placeholderText: qsTr("value-a, value-b")
                selectByMouse: true
                visible: root.categoricalHoldoutKind
            }

            TextField {
                id: minimumValue

                Accessible.name: qsTr("Holdout minimum")
                Layout.fillWidth: true
                objectName: "preparationScenarioHoldoutMinimum"
                placeholderText: qsTr("Minimum")
                selectByMouse: true
                visible: !root.categoricalHoldoutKind
            }

            TextField {
                id: maximumValue

                Accessible.name: qsTr("Holdout maximum")
                Layout.fillWidth: true
                objectName: "preparationScenarioHoldoutMaximum"
                placeholderText: qsTr("Maximum")
                selectByMouse: true
                visible: !root.categoricalHoldoutKind
            }

            AppButton {
                enabled: !root.locked
                objectName: "preparationScenarioSetHoldoutButton"
                onClicked: {
                    const partition = String(holdoutPartition.currentValue);
                    if (root.categoricalHoldoutKind)
                    root.scenarioCategoricalHoldoutRequested(root.draft, partition,
                                                             categoricalValues.text);
                    else if (root.draft.kind === "range_holdout")
                    root.scenarioRangeHoldoutRequested(root.draft, partition, minimumValue.text,
                                                       maximumValue.text);
                    else
                    root.scenarioCoordinateHoldoutRequested(root.draft, partition, String(
                                                                holdoutField.currentValue),
                                                            minimumValue.text, maximumValue.text);
                }
                text: qsTr("Set holdout")
            }
        }
    }

    Card {
        Layout.fillWidth: true
        flat: true
        objectName: "preparationScenarioStratificationCard"
        subtitle: qsTr(
                      "Categorical fields and numeric bin boundaries form the deterministic hash key.")
        title: qsTr("Stratification")
        visible: root.draft.kind === "stratified_hash"

        TextField {
            id: strataFields

            Accessible.name: qsTr("Categorical strata fields")
            Layout.fillWidth: true
            enabled: !root.locked
            objectName: "preparationScenarioStrataFields"
            onEditingFinished: root.scenarioStrataRequested(root.draft, text)
            placeholderText: qsTr("fluid, phase")
            selectByMouse: true
            text: root.draft.strataCategoricalText
        }

        RowLayout {
            Layout.fillWidth: true

            AppComboBox {
                id: binField

                Accessible.name: qsTr("Numeric bin field")
                Layout.fillWidth: true
                model: root.draft.fieldChoices
                objectName: "preparationScenarioBinField"
            }

            TextField {
                id: binBoundaries

                Accessible.name: qsTr("Numeric bin boundaries")
                Layout.fillWidth: true
                objectName: "preparationScenarioBinBoundaries"
                placeholderText: qsTr("250, 300, 350")
                selectByMouse: true
            }

            AppButton {
                enabled: !root.locked
                onClicked: root.scenarioNumericBinsRequested(root.draft, String(
                                                                 binField.currentValue),
                                                             binBoundaries.text)
                text: qsTr("Set bins")
            }
        }

        ListView {
            Accessible.name: qsTr("Scenario numeric bins")
            Layout.fillWidth: true
            Layout.preferredHeight: Math.max(36, Math.min(144, contentHeight))
            boundsBehavior: Flickable.StopAtBounds
            clip: true
            model: root.draft.numericBinsModel
            objectName: "preparationScenarioNumericBins"

            delegate: RowLayout {
                id: numericBinRow

                required property string field
                required property string summary

                width: ListView.view.width

                Label {
                    Layout.fillWidth: true
                    color: Theme.textMuted
                    font.family: Theme.monoFamily
                    font.pixelSize: 11
                    text: numericBinRow.field + ": " + numericBinRow.summary
                }

                AppButton {
                    compact: true
                    enabled: !root.locked
                    onClicked: root.scenarioRemoveNumericBinsRequested(root.draft,
                                                                       numericBinRow.field)
                    text: qsTr("Remove")
                }
            }
        }
    }

    Card {
        Layout.fillWidth: true
        flat: true
        objectName: "preparationScenarioTransformationsCard"
        subtitle: qsTr(
                      "Order is preserved. Every transformation is fitted on the training partition only and then applied to validation and test rows.")
        title: qsTr("Transformations")

        ListView {
            id: transformationsList

            Accessible.name: qsTr("Scenario transformations")
            Layout.fillWidth: true
            Layout.preferredHeight: Math.max(44, Math.min(176, contentHeight))
            boundsBehavior: Flickable.StopAtBounds
            clip: true
            model: root.draft.transformationsModel
            objectName: "preparationScenarioTransformations"
            spacing: Theme.spacingTiny

            delegate: RowLayout {
                id: transformationRow

                required property int index
                required property string summary

                width: ListView.view.width

                Label {
                    Layout.fillWidth: true
                    color: Theme.textMuted
                    font.family: Theme.monoFamily
                    font.pixelSize: 11
                    text: transformationRow.summary
                    wrapMode: Text.WrapAnywhere
                }

                AppButton {
                    compact: true
                    enabled: !root.locked && transformationRow.index > 0
                    onClicked: root.scenarioTransformationMoveRequested(root.draft,
                                                                        transformationRow.index,
                                                                        transformationRow.index - 1)
                    text: qsTr("Up")
                }

                AppButton {
                    compact: true
                    enabled: !root.locked && transformationRow.index + 1 < transformationsList.count
                    onClicked: root.scenarioTransformationMoveRequested(root.draft,
                                                                        transformationRow.index,
                                                                        transformationRow.index + 1)
                    text: qsTr("Down")
                }

                AppButton {
                    compact: true
                    enabled: !root.locked
                    onClicked: root.scenarioTransformationRemoveRequested(root.draft,
                                                                          transformationRow.index)
                    text: qsTr("Remove")
                }
            }
        }

        Label {
            Layout.fillWidth: true
            color: Theme.textMuted
            font.family: Theme.sansFamily
            font.pixelSize: 11
            text: qsTr("Methods: %1").arg(root.draft.transformationMethodChoices.join(", "))
            wrapMode: Text.Wrap
        }

        RowLayout {
            Layout.fillWidth: true

            AppComboBox {
                id: transformField

                Accessible.name: qsTr("Transformation field")
                Layout.fillWidth: true
                model: root.draft.fieldChoices
                objectName: "preparationScenarioTransformationField"
            }

            TextField {
                id: transformMethods

                Accessible.name: qsTr("Ordered transformation methods")
                Layout.fillWidth: true
                objectName: "preparationScenarioTransformationMethods"
                placeholderText: qsTr("log10, standard")
                selectByMouse: true
            }

            AppButton {
                enabled: !root.locked
                onClicked: root.scenarioTransformationAddRequested(root.draft, String(
                                                                       transformField.currentValue),
                                                                   transformMethods.text)
                text: qsTr("Add")
            }
        }
    }

    RowLayout {
        Layout.fillWidth: true

        Item {
            Layout.fillWidth: true
        }

        AppButton {
            enabled: !root.locked
            objectName: "preparationScenarioCancelButton"
            onClicked: root.cancelRequested()
            text: qsTr("Cancel")
        }

        AppButton {
            enabled: !root.locked && root.draft.locallyValid
            objectName: "preparationScenarioCommitButton"
            onClicked: root.commitRequested()
            text: qsTr("Commit")
            tone: "primary"
        }
    }

    Loader {
        id: kindChangeDialogLoader

        active: root.dialogsEnabled && root.Window.window !== null
        objectName: "preparationScenarioKindChangeDialogLoader"
        sourceComponent: Component {
            DecisionDialog {
                id: scenarioKindDialog

                acceptText: qsTr("Change kind")
                bodyText: qsTr(
                              "Changing scenario kind discards temporary partitions, holdouts, strata, field, and remainder values that do not belong to the new shape. The seed and transformations are retained.")
                objectName: "preparationScenarioKindChangeDialog"
                onAccepted: {
                    root.scenarioKindChangeRequested(root.draft, root.pendingKind, true);
                    root.pendingKind = "";
                }
                onRejected: root.pendingKind = ""
                title: qsTr("Replace scenario shape?")

                Connections {
                    function onKindChangeDialogRequested() {
                        scenarioKindDialog.open();
                    }

                    target: root
                }
            }
        }
    }
}
