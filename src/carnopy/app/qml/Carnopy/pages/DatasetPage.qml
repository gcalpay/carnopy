pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Carnopy

Item {
    id: root

    required property var configController
    required property var datasetDraft
    required property var desktopController
    property string attentionField: ""
    property int attentionRow: -1
    property int attentionSerial: 0
    property int expectedColumns: 1
    property var outputFocusControl: null
    property string samplerAttentionAxis: ""
    property string samplerAttentionField: ""
    property int samplerAttentionSerial: 0

    signal coordinateChangeRequested(string axis)
    signal fluidSelectionRequested(string value, bool selected)
    signal fluidMoveRequested(int row, int offset)
    signal fluidRemoveRequested(int row)
    signal modelChangeRequested(string model)
    signal modeChangeRequested(string mode)
    signal outputSelectionRequested(string format, bool selected)
    signal propertySelectionRequested(string value, bool selected)
    signal propertyMoveRequested(int row, int offset)
    signal propertyRemoveRequested(int row)
    signal samplerKindChangeRequested(var draft, string kind)
    signal samplerTextChangeRequested(var draft, string field, string text)
    signal samplerUnitChangeRequested(var draft, string unit)

    function indexForValue(combo, value) {
        for (let row = 0; row < combo.count; ++row) {
            if (String(combo.valueAt(row)) === value)
                return row;
        }
        return -1;
    }

    function formatCount(value) {
        return Number(value).toLocaleString(Qt.locale("en_US"), "f", 0);
    }

    function modelLabel(value) {
        if (value === "heos")
            return qsTr("Helmholtz Equation of State (HEOS)");
        if (value === "pr")
            return qsTr("Peng–Robinson (PR)");
        if (value === "srk")
            return qsTr("Soave–Redlich–Kwong (SRK)");
        return value;
    }

    function modeLabel(value) {
        if (value === "property_table")
            return qsTr("Property table");
        if (value === "saturation_table")
            return qsTr("Saturation table");
        if (value === "vapor_mass_fraction_table")
            return qsTr("Vapor-mass-fraction table");
        return value;
    }

    function syncChoices() {
        modelChoice.currentIndex = indexForValue(modelChoice, root.datasetDraft.modelName);
        modeChoice.currentIndex = indexForValue(modeChoice, root.datasetDraft.modeName);
        coordinateChoice.currentIndex = indexForValue(coordinateChoice,
                                                      root.datasetDraft.coordinateName);
    }

    function reveal(item) {
        if (item === null || item === undefined)
            return;
        const position = item.mapToItem(pageFlickable.contentItem, 0, 0);
        const maximum = Math.max(0, pageFlickable.contentHeight - pageFlickable.height);
        pageFlickable.contentY = Math.min(maximum, Math.max(0, position.y - 80));
    }

    function focusField(field, row) {
        let target = null;
        if (field === "dataset.model") {
            target = modelChoice;
            target.forceActiveFocus();
        } else if (field === "dataset.mode") {
            target = modeChoice;
            target.forceActiveFocus();
        } else if (field === "dataset.fluids") {
            target = fluidChoices.focusRow(row);
        } else if (field === "dataset.properties") {
            target = propertyChoices.focusRow(row);
        } else if (field === "dataset.outputs.dataset_formats") {
            target = root.outputFocusControl;
            if (target !== null)
                target.forceActiveFocus();
        } else if (field.indexOf("dataset.grid.") === 0) {
            const parts = field.split(".");
            root.samplerAttentionAxis = parts.length > 2 ? parts[2] : "";
            root.samplerAttentionField = parts.length > 3 ? parts[3] : "unit";
            root.samplerAttentionSerial += 1;
            root.reveal(workbenchGrid);
            return;
        }
        if (target === null) {
            target = modeChoice;
            target.forceActiveFocus();
        }
        root.reveal(target);
    }

    onAttentionSerialChanged: Qt.callLater(function () {
        root.focusField(root.attentionField, root.attentionRow);
    })

    Connections {
        function onCoordinateNameChanged() {
            root.syncChoices();
        }

        function onModeNameChanged() {
            root.syncChoices();
        }

        function onModelNameChanged() {
            root.syncChoices();
        }

        target: root.datasetDraft
    }

    Connections {
        function onDatasetDecisionChanged() {
            root.syncChoices();
        }

        target: root.desktopController
    }

    Component.onCompleted: syncChoices()

    Flickable {
        id: pageFlickable

        anchors.fill: parent
        boundsBehavior: Flickable.StopAtBounds
        clip: true
        contentHeight: pageColumn.implicitHeight + 48
        contentWidth: width
        flickableDirection: Flickable.VerticalFlick
        objectName: "datasetPageFlickable"
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
                        text: qsTr("Dataset configuration")
                    }

                    Label {
                        Layout.fillWidth: true
                        color: Theme.textMuted
                        font.family: Theme.sansFamily
                        font.pixelSize: 12
                        text: qsTr(
                                  "Define reproducible thermophysical sampling and emitted columns.")
                        wrapMode: Text.Wrap
                    }
                }

                StatusBadge {
                    label: root.datasetDraft.locallyValid ? qsTr("Locally complete") : qsTr(
                                                                "Needs attention")
                    tone: root.datasetDraft.locallyValid ? "success" : "danger"
                }
            }

            ValidationIssue {
                Layout.fillWidth: true
                field: root.datasetDraft.firstInvalidField
                issue: root.datasetDraft.issue
                objectName: "datasetBlockingIssue"
            }

            ResponsiveCardGrid {
                id: workbenchGrid

                Layout.fillWidth: true
                Layout.preferredHeight: implicitHeight
                maximumColumns: Math.min(3, root.expectedColumns)
                minimumCardWidth: 300
                objectName: "datasetSamplerGrid"

                Card {
                    Layout.fillHeight: true
                    Layout.fillWidth: true
                    objectName: "datasetBackendModeCard"
                    sectionNumber: "1"
                    subtitle: qsTr(
                                  "Backend capabilities define the available models and properties.")
                    title: qsTr("Backend and mode")

                    Label {
                        color: Theme.textMuted
                        font.family: Theme.sansFamily
                        font.pixelSize: 11
                        text: qsTr("Backend")
                    }

                    Label {
                        Layout.fillWidth: true
                        color: Theme.text
                        font.family: Theme.sansFamily
                        font.pixelSize: 12
                        text: qsTr("CoolProp")
                    }

                    Label {
                        color: Theme.textMuted
                        font.family: Theme.sansFamily
                        font.pixelSize: 11
                        text: qsTr("Model")
                    }

                    AppComboBox {
                        id: modelChoice

                        Accessible.name: qsTr("Thermodynamic model")
                        Layout.fillWidth: true
                        model: root.datasetDraft.modelChoices
                        objectName: "datasetModelChoice"
                        onActivated: root.modelChangeRequested(String(currentValue))
                        textRole: "display"
                        valueRole: "value"
                    }

                    Label {
                        color: Theme.textMuted
                        font.family: Theme.sansFamily
                        font.pixelSize: 11
                        text: qsTr("Mode")
                    }

                    AppComboBox {
                        id: modeChoice

                        Accessible.name: qsTr("Dataset mode")
                        Layout.fillWidth: true
                        model: root.datasetDraft.modeChoices
                        objectName: "datasetModeChoice"
                        onActivated: root.modeChangeRequested(String(currentValue))
                        textRole: "display"
                        valueRole: "value"
                    }

                    AppComboBox {
                        id: coordinateChoice

                        Accessible.name: qsTr("Independent coordinate")
                        Layout.fillWidth: true
                        model: root.datasetDraft.coordinateChoices
                        objectName: "datasetCoordinateChoice"
                        onActivated: root.coordinateChangeRequested(String(currentValue))
                        textRole: "display"
                        valueRole: "value"
                        visible: root.datasetDraft.modeName !== "property_table"
                    }
                }

                Card {
                    Layout.fillHeight: true
                    Layout.fillWidth: true
                    meta: qsTr("%1 selected").arg(fluidChoices.selectedCount)
                    objectName: "datasetFluidsCard"
                    sectionNumber: "2"
                    subtitle: qsTr(
                                  "Requested aliases stay visible; canonical identities remain explicit.")
                    title: qsTr("Fluids")

                    SearchableChoiceList {
                        id: fluidChoices

                        Layout.fillWidth: true
                        choiceModel: root.datasetDraft.fluidSelectorChoices
                        emptyText: qsTr("Add at least one fluid")
                        noun: qsTr("fluid")
                        objectName: "datasetFluids"
                        onMoveRequested: (row, offset) => root.fluidMoveRequested(row, offset)
                        onRemoveRequested: row => root.fluidRemoveRequested(row)
                        onSelectionRequested: (value, selected) => root.fluidSelectionRequested(
                                                                       value, selected)
                        selectorText: qsTr("Add fluid")
                        selectedModel: root.datasetDraft.selectedFluids
                        showCanonicalIdentities: true
                        summaryLimit: 4
                    }
                }

                Card {
                    Layout.fillHeight: true
                    Layout.fillWidth: true
                    meta: qsTr("%1 selected").arg(propertyChoices.selectedCount)
                    objectName: "datasetPropertiesCard"
                    sectionNumber: "3"
                    subtitle: qsTr(
                                  "Order is preserved in deterministic YAML and generated columns.")
                    title: qsTr("Properties")

                    SearchableChoiceList {
                        id: propertyChoices

                        Layout.fillWidth: true
                        choiceModel: root.datasetDraft.propertySelectorChoices
                        emptyText: qsTr("Add at least one property")
                        noun: qsTr("property")
                        objectName: "datasetProperties"
                        onMoveRequested: (row, offset) => root.propertyMoveRequested(row, offset)
                        onRemoveRequested: row => root.propertyRemoveRequested(row)
                        onSelectionRequested: (value, selected) => root.propertySelectionRequested(
                                                                       value, selected)
                        selectorText: qsTr("Edit properties")
                        selectedModel: root.datasetDraft.selectedProperties
                        showPropertyPresentation: true
                        summaryLimit: 6
                    }
                }

                Repeater {
                    id: samplerRepeater

                    model: root.datasetDraft.samplerDrafts

                    delegate: SamplerEditor {
                        attentionField: root.samplerAttentionAxis === String(draft.axis)
                                        ? root.samplerAttentionField : ""
                        attentionSerial: root.samplerAttentionAxis === String(draft.axis)
                                         ? root.samplerAttentionSerial : 0
                        Layout.fillHeight: true
                        Layout.fillWidth: true
                        sectionNumber: String(4 + index)
                        onKindChangeRequested: (draft, kind) => root.samplerKindChangeRequested(
                                                                    draft, kind)
                        onTextChangeRequested: (draft, field, text)
                                               => root.samplerTextChangeRequested(draft, field,
                                                                                  text)
                        onUnitChangeRequested: (draft, unit) => root.samplerUnitChangeRequested(
                                                                    draft, unit)
                    }
                }

                Card {
                    Layout.fillHeight: true
                    Layout.fillWidth: true
                    objectName: "datasetOutputsCard"
                    sectionNumber: String(4 + samplerRepeater.count)
                    subtitle: qsTr("At least one immutable dataset format is required.")
                    title: qsTr("Dataset outputs")

                    Repeater {
                        id: outputRepeater

                        model: root.datasetDraft.outputFormats

                        delegate: Item {
                            required property int index
                            required property bool selected
                            required property string display
                            required property string value

                            Layout.fillWidth: true
                            implicitHeight: outputCheck.implicitHeight

                            CheckBox {
                                id: outputCheck

                                Accessible.name: parent.display + qsTr(" dataset output")
                                anchors.left: parent.left
                                anchors.right: parent.right
                                checked: parent.selected
                                objectName: "datasetOutput-" + parent.value
                                Component.onCompleted: {
                                    if (parent.index === 0)
                                    root.outputFocusControl = outputCheck;
                                }
                                onClicked: root.outputSelectionRequested(parent.value, checked)
                                text: parent.display
                            }
                        }
                    }

                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 1
                        color: Theme.divider
                    }

                    Label {
                        Layout.fillWidth: true
                        color: Theme.textMuted
                        font.family: Theme.sansFamily
                        font.pixelSize: 11
                        objectName: "datasetGridCombinationsPerFluid"
                        text: qsTr("%1 grid combinations per fluid").arg(root.formatCount(
                                                                             root.datasetDraft.gridCombinationsPerFluid))
                    }

                    Label {
                        Layout.fillWidth: true
                        color: Theme.textMuted
                        font.family: Theme.sansFamily
                        font.pixelSize: 11
                        objectName: "datasetProjectedRowsPerFluid"
                        text: qsTr("%1 projected rows per fluid").arg(root.formatCount(
                                                                          root.datasetDraft.projectedRowsPerFluid))
                    }

                    Label {
                        Layout.fillWidth: true
                        color: root.datasetDraft.projectionIssue.length > 0 ? Theme.red :
                                                                              Theme.success
                        font.family: Theme.sansFamily
                        font.pixelSize: 12
                        font.weight: Font.Medium
                        objectName: "datasetProjectedRows"
                        text: root.datasetDraft.projectionAvailable ? qsTr(
                                                                          "%1 projected rows across selected fluids").arg(
                                                                          root.formatCount(
                                                                              root.datasetDraft.projectedRows)) :
                                                                      qsTr("Projected rows unavailable")
                        wrapMode: Text.Wrap
                    }

                    Label {
                        Layout.fillWidth: true
                        color: Theme.red
                        font.family: Theme.sansFamily
                        font.pixelSize: 11
                        objectName: "datasetProjectionIssue"
                        text: root.datasetDraft.projectionIssue
                        visible: text.length > 0
                        wrapMode: Text.Wrap
                    }

                    Label {
                        Layout.fillWidth: true
                        color: Theme.amber
                        font.family: Theme.sansFamily
                        font.pixelSize: 11
                        text: root.datasetDraft.referenceAdvisory
                        visible: text.length > 0
                        wrapMode: Text.Wrap
                    }
                }
            }

            ResponsiveCardGrid {
                Layout.fillWidth: true
                Layout.preferredHeight: implicitHeight
                maximumColumns: Math.min(2, root.expectedColumns)
                minimumCardWidth: 360
                objectName: "datasetSummaryGrid"

                Card {
                    Layout.fillWidth: true
                    objectName: "datasetConfigurationSummary"
                    title: qsTr("Configuration summary")

                    Label {
                        Layout.fillWidth: true
                        color: Theme.textMuted
                        font.family: Theme.sansFamily
                        font.pixelSize: 12
                        text: qsTr("CoolProp  ·  %1  ·  %2").arg(root.modelLabel(
                                                                     root.datasetDraft.modelName)).arg(
                                  root.modeLabel(root.datasetDraft.modeName))
                        wrapMode: Text.Wrap
                    }

                    Label {
                        Layout.fillWidth: true
                        color: root.datasetDraft.projectionAvailable ? Theme.success :
                                                                       Theme.textMuted
                        font.family: Theme.sansFamily
                        font.pixelSize: 13
                        font.weight: Font.Medium
                        text: root.datasetDraft.projectionAvailable ? qsTr("%1 projected rows").arg(
                                                                          root.formatCount(
                                                                              root.datasetDraft.projectedRows)) :
                                                                      qsTr("Projection unavailable")
                    }
                }

                Card {
                    Layout.fillWidth: true
                    meta: root.configController.dirty ? qsTr("Unsaved changes") : qsTr("Saved")
                    metaColor: root.configController.dirty ? Theme.amber : Theme.success
                    objectName: "datasetDocumentSummary"
                    title: qsTr("Document")

                    Label {
                        Layout.fillWidth: true
                        color: Theme.text
                        elide: Text.ElideMiddle
                        font.family: Theme.monoFamily
                        font.pixelSize: 11
                        text: root.configController.fileDisplay.length > 0
                              ? root.configController.fileDisplay : qsTr("New configuration")
                    }

                    Label {
                        Layout.fillWidth: true
                        color: Theme.textMuted
                        font.family: Theme.sansFamily
                        font.pixelSize: 12
                        text: qsTr(
                                  "Worker validation runs again on the exact YAML before every Save.")
                        wrapMode: Text.Wrap
                    }
                }
            }
        }
    }
}
