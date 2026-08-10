pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Carnopy

Item {
    id: root

    required property var configController
    required property var desktopController
    required property var sweepDraft
    required property var workflowController
    property string actionMessage: ""
    property string attentionField: ""
    property int attentionRow: -1
    property int attentionSerial: 0
    property string comparisonAttentionField: ""
    property int comparisonAttentionRow: -1
    property int comparisonAttentionSerial: 0
    property bool dialogsEnabled: true
    property int expectedColumns: 1
    property string pendingDatasetChange: ""
    property string pendingDatasetValue: ""
    property string samplerAttentionAxis: ""
    property string samplerAttentionField: ""
    property int samplerAttentionSerial: 0
    readonly property var datasetDraft: sweepDraft.datasetDraft
    readonly property bool locked: !configController.canEdit

    signal shapeDialogRequested

    function reveal(item) {
        if (item === null || item === undefined)
            return;
        const position = item.mapToItem(pageFlickable.contentItem, 0, 0);
        const maximum = Math.max(0, pageFlickable.contentHeight - pageFlickable.height);
        pageFlickable.contentY = Math.min(maximum, Math.max(0, position.y - 80));
    }

    function focusField(field, row) {
        let target = modelCard;
        if (field === "sweep.backend.reference_model")
            target = referenceChoice;
        else if (field === "sweep.mode")
            target = modeChoice;
        else if (field.indexOf("sweep.grid.") === 0) {
            const parts = field.split(".");
            root.samplerAttentionAxis = parts.length > 2 ? parts[2] : "";
            root.samplerAttentionField = parts.length > 3 ? parts[3] : "unit";
            root.samplerAttentionSerial += 1;
            root.reveal(definitionGrid);
            return;
        } else if (field.indexOf("comparison") >= 0) {
            if (root.sweepDraft.activeComparisonDraft !== null) {
                const editor = activeComparisonLoader.item;
                if (editor !== null) {
                    root.comparisonAttentionField = field;
                    root.comparisonAttentionRow = row;
                    root.comparisonAttentionSerial += 1;
                    root.reveal(editor);
                    return;
                }
            }
            target = comparisonCard;
        } else if (field.indexOf("properties") >= 0) {
            target = propertyChoices.focusRow(row);
        } else if (field.indexOf("fluids") >= 0) {
            target = fluidChoices.focusRow(row);
        } else if (field.indexOf("outputs") >= 0) {
            target = outputCard;
        }
        target.forceActiveFocus();
        root.reveal(target);
    }

    onAttentionSerialChanged: Qt.callLater(function () {
        root.focusField(root.attentionField, root.attentionRow);
    })

    Connections {
        function onMessage(message) {
            root.actionMessage = message;
        }

        target: root.sweepDraft
    }

    Flickable {
        id: pageFlickable

        anchors.fill: parent
        boundsBehavior: Flickable.StopAtBounds
        clip: true
        contentHeight: pageColumn.implicitHeight + 48
        contentWidth: width
        flickableDirection: Flickable.VerticalFlick
        objectName: "modelSweepPageFlickable"
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
            anchors.topMargin: 22
            spacing: Theme.spacingMedium

            RowLayout {
                Layout.fillWidth: true

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 3

                    Label {
                        Accessible.name: text
                        Layout.fillWidth: true
                        color: Theme.text
                        font.family: Theme.sansFamily
                        font.pixelSize: 23
                        font.weight: Font.DemiBold
                        text: qsTr("Model Sweep configuration")
                    }

                    Label {
                        Layout.fillWidth: true
                        color: Theme.textMuted
                        font.family: Theme.sansFamily
                        font.pixelSize: 12
                        text: qsTr(
                                  "Compare two or more CoolProp models over one exact, reproducible dataset specification.")
                        wrapMode: Text.Wrap
                    }
                }

                StatusBadge {
                    label: root.sweepDraft.hasActiveComparisonEdit ? qsTr("Comparison edit open") : (
                                                                         root.sweepDraft.locallyValid
                                                                         ? qsTr("Locally complete") :
                                                                           qsTr("Needs attention"))
                    objectName: "modelSweepLocalState"
                    tone: root.sweepDraft.hasActiveComparisonEdit ? "warning" : (
                                                                        root.sweepDraft.locallyValid
                                                                        ? "success" : "danger")
                }
            }

            BlockingBanner {
                Layout.fillWidth: true
                field: root.sweepDraft.firstInvalidField
                message: root.sweepDraft.issue
                row: root.sweepDraft.firstInvalidRow
                section: "sweep"
                title: qsTr("Sweep configuration needs attention")
                visible: !root.sweepDraft.locallyValid
                onActionRequested: (section, field, row) => root.focusField(field, row)
            }

            ValidationIssue {
                Layout.fillWidth: true
                field: root.sweepDraft.firstInvalidField
                issue: root.actionMessage
                objectName: "modelSweepActionMessage"
            }

            ResponsiveCardGrid {
                id: definitionGrid

                Layout.fillWidth: true
                Layout.preferredHeight: implicitHeight
                maximumColumns: Math.min(3, root.expectedColumns)
                minimumCardWidth: 300
                objectName: "modelSweepDefinitionGrid"
                uniformHeights: false

                Card {
                    id: modelCard

                    Layout.fillWidth: true
                    activeFocusOnTab: true
                    objectName: "modelSweepModelsCard"
                    sectionNumber: "1"
                    subtitle: qsTr(
                                  "The reference model is implicit in deltas and cannot be removed until another selected model becomes reference.")
                    title: qsTr("Models and reference")

                    Flow {
                        Layout.fillWidth: true
                        spacing: Theme.spacingSmall

                        Repeater {
                            model: root.sweepDraft.modelChoices

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
                                    Accessible.name: qsTr("Include %1 in model sweep").arg(
                                                         parent.display)
                                    checked: parent.selected
                                    enabled: !root.locked && (parent.compatible || parent.selected)
                                    objectName: "modelSweepModel-" + parent.value
                                    onClicked: root.desktopController.requestSweepModelSelection(
                                                   parent.value, checked)
                                    text: parent.display
                                }
                            }
                        }
                    }

                    Label {
                        color: Theme.textMuted
                        font.family: Theme.sansFamily
                        font.pixelSize: 11
                        text: qsTr("Reference model")
                    }

                    AppComboBox {
                        id: referenceChoice

                        Accessible.description: qsTr(
                                                    "Delta plots compare against this selected model")
                        Accessible.name: qsTr("Sweep reference model")
                        Layout.fillWidth: true
                        currentIndex: indexForRoleValue(root.sweepDraft.referenceModel)
                        enabled: !root.locked
                        model: root.sweepDraft.selectedModels
                        objectName: "modelSweepReferenceModel"
                        onActivated: root.desktopController.requestSweepReferenceModel(String(
                                                                                           currentValue))
                    }
                }

                Card {
                    Layout.fillWidth: true
                    objectName: "modelSweepModeCard"
                    sectionNumber: "2"
                    subtitle: qsTr(
                                  "Changing mode or independent coordinate replaces only the incompatible sampler shape after confirmation.")
                    title: qsTr("Dataset mode")

                    Label {
                        color: Theme.textMuted
                        font.family: Theme.sansFamily
                        font.pixelSize: 11
                        text: qsTr("Mode")
                    }

                    AppComboBox {
                        id: modeChoice

                        Accessible.name: qsTr("Sweep dataset mode")
                        Layout.fillWidth: true
                        currentIndex: indexForRoleValue(root.datasetDraft.modeName)
                        enabled: !root.locked
                        model: root.datasetDraft.modeChoices
                        objectName: "modelSweepMode"
                        onActivated: {
                            root.pendingDatasetChange = "mode";
                            root.pendingDatasetValue = String(currentValue);
                            root.shapeDialogRequested();
                        }
                        textRole: "display"
                        valueRole: "value"
                    }

                    Label {
                        color: Theme.textMuted
                        font.family: Theme.sansFamily
                        font.pixelSize: 11
                        text: qsTr("Independent coordinate")
                        visible: root.datasetDraft.modeName !== "property_table"
                    }

                    AppComboBox {
                        Accessible.name: qsTr("Sweep independent coordinate")
                        Layout.fillWidth: true
                        currentIndex: indexForRoleValue(root.datasetDraft.coordinateName)
                        enabled: !root.locked
                        model: root.datasetDraft.coordinateChoices
                        objectName: "modelSweepCoordinate"
                        onActivated: {
                            root.pendingDatasetChange = "coordinate";
                            root.pendingDatasetValue = String(currentValue);
                            root.shapeDialogRequested();
                        }
                        textRole: "display"
                        valueRole: "value"
                        visible: root.datasetDraft.modeName !== "property_table"
                    }
                }

                Card {
                    id: fluidsCard

                    Layout.fillWidth: true
                    activeFocusOnTab: true
                    objectName: "modelSweepFluidsCard"
                    sectionNumber: "3"
                    subtitle: qsTr(
                                  "Aliases and canonical backend identities follow the Dataset contract.")
                    title: qsTr("Fluids")

                    SearchableChoiceList {
                        id: fluidChoices

                        Layout.fillWidth: true
                        choiceModel: root.datasetDraft.fluidSelectorChoices
                        locked: root.locked
                        noun: qsTr("fluid")
                        objectName: "modelSweepFluids"
                        onMoveRequested: (row, offset)
                                         => root.desktopController.requestSweepFluidMove(row,
                                                                                         offset)
                        onRemoveRequested: row => root.desktopController.requestSweepFluidRemove(
                                                      row)
                        onSelectionRequested: (value, selected)
                                              => root.desktopController.requestSweepFluidSelection(
                                                     value, selected)
                        selectedModel: root.datasetDraft.selectedFluids
                        showCanonicalIdentities: true
                        summaryLimit: 4
                    }
                }

                Card {
                    id: propertiesCard

                    Layout.fillWidth: true
                    activeFocusOnTab: true
                    objectName: "modelSweepPropertiesCard"
                    sectionNumber: "4"
                    subtitle: qsTr(
                                  "Unsupported imported selections remain visible and block planning until resolved.")
                    title: qsTr("Properties")

                    SearchableChoiceList {
                        id: propertyChoices

                        Layout.fillWidth: true
                        choiceModel: root.datasetDraft.propertySelectorChoices
                        locked: root.locked
                        noun: qsTr("property")
                        objectName: "modelSweepProperties"
                        onMoveRequested: (row, offset)
                                         => root.desktopController.requestSweepPropertyMove(row,
                                                                                            offset)
                        onRemoveRequested: row => root.desktopController.requestSweepPropertyRemove(
                                                      row)
                        onSelectionRequested: (value, selected)
                                              => root.desktopController.requestSweepPropertySelection(
                                                     value, selected)
                        selectedModel: root.datasetDraft.selectedProperties
                        showPropertyPresentation: true
                        summaryLimit: 6
                    }
                }

                Repeater {
                    id: samplerRepeater

                    model: root.datasetDraft.samplerDrafts

                    delegate: SamplerEditor {
                        Layout.fillWidth: true
                        attentionField: root.samplerAttentionAxis === String(draft.axis)
                                        ? root.samplerAttentionField : ""
                        attentionSerial: root.samplerAttentionAxis === String(draft.axis)
                                         ? root.samplerAttentionSerial : 0
                        enabled: !root.locked
                        onKindChangeRequested: (draft, kind)
                                               => root.desktopController.requestSweepSamplerKindChange(
                                                      draft, kind)
                        onTextChangeRequested: (draft, field, text)
                                               => root.desktopController.requestSweepSamplerTextChange(
                                                      draft, field, text)
                        onUnitChangeRequested: (draft, unit)
                                               => root.desktopController.requestSweepSamplerUnitChange(
                                                      draft, unit)
                        sectionNumber: String(5 + index)
                    }
                }

                Card {
                    id: outputCard

                    Layout.fillWidth: true
                    activeFocusOnTab: true
                    objectName: "modelSweepOutputsCard"
                    sectionNumber: String(5 + samplerRepeater.count)
                    subtitle: qsTr("CSV and Parquet outputs use the complete public Sweep schema.")
                    title: qsTr("Dataset outputs")

                    Repeater {
                        model: root.datasetDraft.outputFormats

                        delegate: Item {
                            required property string display
                            required property int index
                            required property bool selected
                            required property string value

                            Layout.fillWidth: true
                            implicitHeight: outputCheck.implicitHeight

                            CheckBox {
                                id: outputCheck

                                Accessible.name: qsTr("Emit %1 Sweep datasets").arg(parent.display)
                                anchors.left: parent.left
                                anchors.right: parent.right
                                checked: parent.selected
                                enabled: !root.locked
                                objectName: "modelSweepOutput-" + parent.value
                                onClicked: root.desktopController.requestSweepOutputSelection(
                                               parent.value, checked)
                                text: parent.display
                            }
                        }
                    }
                }
            }

            Card {
                id: comparisonCard

                Layout.fillWidth: true
                activeFocusOnTab: true
                objectName: "modelSweepComparisonsCard"
                subtitle: qsTr(
                              "Committed order is serialized deterministically and participates in plan identity.")
                title: qsTr("Comparison plots")

                RowLayout {
                    Layout.fillWidth: true

                    Label {
                        color: Theme.textMuted
                        font.family: Theme.sansFamily
                        font.pixelSize: 11
                        text: qsTr("Shared format")
                    }

                    AppComboBox {
                        Accessible.name: qsTr("Shared comparison plot format")
                        Layout.preferredWidth: 160
                        currentIndex: indexForRoleValue(root.sweepDraft.comparisonFormat)
                        enabled: !root.locked && !root.sweepDraft.hasActiveComparisonEdit
                        model: ["png", "svg", "pdf"]
                        objectName: "modelSweepComparisonFormat"
                        onActivated: root.desktopController.requestSweepComparisonFormat(String(
                                                                                             currentValue))
                    }

                    Item {
                        Layout.fillWidth: true
                    }

                    AppButton {
                        Accessible.description: qsTr("Open a temporary comparison plot editor")
                        enabled: !root.locked && !root.sweepDraft.hasActiveComparisonEdit
                        objectName: "modelSweepAddComparison"
                        onClicked: root.desktopController.requestSweepAddComparison()
                        text: qsTr("Add comparison")
                        tone: "primary"
                    }
                }

                ListView {
                    id: comparisonList

                    Accessible.name: qsTr("Committed comparison plots")
                    Layout.fillWidth: true
                    Layout.preferredHeight: Math.max(52, Math.min(260, contentHeight))
                    boundsBehavior: Flickable.StopAtBounds
                    clip: true
                    interactive: contentHeight > height
                    model: root.sweepDraft.comparisonPlots
                    objectName: "modelSweepComparisonList"
                    pixelAligned: true
                    spacing: Theme.spacingTiny

                    delegate: RowLayout {
                        id: comparisonRow

                        required property string display
                        required property int index

                        width: ListView.view.width

                        Label {
                            Layout.fillWidth: true
                            color: Theme.text
                            font.family: Theme.sansFamily
                            font.pixelSize: 12
                            text: comparisonRow.display
                            wrapMode: Text.Wrap
                        }

                        AppButton {
                            Accessible.description: qsTr("Edit comparison %1").arg(
                                                        comparisonRow.display)
                            compact: true
                            enabled: !root.locked && !root.sweepDraft.hasActiveComparisonEdit
                            objectName: "modelSweepComparisonEdit-" + comparisonRow.index
                            onClicked: root.desktopController.requestSweepEditComparison(
                                           comparisonRow.index)
                            text: qsTr("Edit")
                        }

                        AppButton {
                            Accessible.description: qsTr("Move comparison %1 earlier").arg(
                                                        comparisonRow.display)
                            compact: true
                            enabled: !root.locked && !root.sweepDraft.hasActiveComparisonEdit
                                     && comparisonRow.index > 0
                            objectName: "modelSweepComparisonUp-" + comparisonRow.index
                            onClicked: root.desktopController.requestSweepMoveComparison(
                                           comparisonRow.index, comparisonRow.index - 1)
                            text: qsTr("Up")
                        }

                        AppButton {
                            Accessible.description: qsTr("Move comparison %1 later").arg(
                                                        comparisonRow.display)
                            compact: true
                            enabled: !root.locked && !root.sweepDraft.hasActiveComparisonEdit
                                     && comparisonRow.index + 1 < comparisonList.count
                            objectName: "modelSweepComparisonDown-" + comparisonRow.index
                            onClicked: root.desktopController.requestSweepMoveComparison(
                                           comparisonRow.index, comparisonRow.index + 1)
                            text: qsTr("Down")
                        }

                        AppButton {
                            Accessible.description: qsTr("Remove comparison %1").arg(
                                                        comparisonRow.display)
                            compact: true
                            enabled: !root.locked && !root.sweepDraft.hasActiveComparisonEdit
                            objectName: "modelSweepComparisonRemove-" + comparisonRow.index
                            onClicked: root.desktopController.requestSweepRemoveComparison(
                                           comparisonRow.index)
                            text: qsTr("Remove")
                        }
                    }

                    Label {
                        anchors.centerIn: parent
                        color: Theme.textMuted
                        font.family: Theme.sansFamily
                        font.pixelSize: 12
                        text: qsTr("No comparison plots configured")
                        visible: comparisonList.count === 0
                    }
                }
            }

            Loader {
                id: activeComparisonLoader

                Layout.fillWidth: true
                active: root.sweepDraft.activeComparisonDraft !== null
                objectName: "modelSweepActiveComparisonEditor"
                sourceComponent: Component {
                    ComparisonPlotEditor {
                        attentionField: root.comparisonAttentionField
                        attentionRow: root.comparisonAttentionRow
                        attentionSerial: root.comparisonAttentionSerial
                        desktopController: root.desktopController
                        draft: root.sweepDraft.activeComparisonDraft
                        locked: root.locked
                        onCancelRequested: root.desktopController.requestSweepCancelComparison()
                        onCommitRequested: root.desktopController.requestSweepCommitComparison()
                    }
                }
            }

            WorkflowRunPanel {
                Layout.fillWidth: true
                workflowController: root.workflowController
                workflowKind: "sweep"
                onCancelRequested: workflow => root.desktopController.requestWorkflowCancel(
                                                   workflow)
                onExecuteRequested: workflow => root.desktopController.requestWorkflowExecute(
                                                    workflow)
                onForceStopRequested: workflow => root.desktopController.requestWorkflowForceStop(
                                                      workflow)
                onInspectResultRequested: workflow
                                          => root.desktopController.requestWorkflowInspectResult(
                                                 workflow)
                onIssueFocusRequested: (section, field, row) => root.focusField(field, row)
                onPlanRequested: workflow => root.desktopController.requestWorkflowPlan(workflow)
            }
        }
    }

    Loader {
        id: datasetShapeDialog

        active: root.dialogsEnabled
        objectName: "modelSweepDatasetShapeDialog"
        sourceComponent: Component {
            DecisionDialog {
                id: shapeDialog

                acceptText: qsTr("Replace sampler shape")
                bodyText: qsTr(
                              "Changing this Dataset shape may replace incompatible sampler values. Other compatible Sweep selections remain unchanged.")
                onAccepted: {
                    if (root.pendingDatasetChange === "mode")
                    root.desktopController.requestSweepModeChange(root.pendingDatasetValue, true);
                    else if (root.pendingDatasetChange === "coordinate")
                    root.desktopController.requestSweepCoordinateChange(root.pendingDatasetValue,
                                                                        true);
                    root.pendingDatasetChange = "";
                    root.pendingDatasetValue = "";
                }
                onRejected: {
                    root.pendingDatasetChange = "";
                    root.pendingDatasetValue = "";
                }
                title: qsTr("Change Sweep dataset shape?")

                Connections {
                    function onShapeDialogRequested() {
                        shapeDialog.open();
                    }

                    target: root
                }
            }
        }
    }
}
