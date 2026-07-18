pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Carnopy

Item {
    id: root

    required property var datasetDraft
    required property var desktopController
    property int expectedColumns: 1

    signal coordinateChangeRequested(string axis)
    signal fluidAddRequested(string value)
    signal fluidMoveRequested(int row, int offset)
    signal fluidRemoveRequested(int row)
    signal modelChangeRequested(string model)
    signal modeChangeRequested(string mode)
    signal outputSelectionRequested(string format, bool selected)
    signal propertyAddRequested(string value)
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

    function syncChoices() {
        modelChoice.currentIndex = indexForValue(modelChoice, root.datasetDraft.modelName);
        modeChoice.currentIndex = indexForValue(modeChoice, root.datasetDraft.modeName);
        coordinateChoice.currentIndex = indexForValue(coordinateChoice,
                                                      root.datasetDraft.coordinateName);
    }

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
            anchors.topMargin: 24
            spacing: Theme.spacingLarge

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
                                  "Declared units and raw sampler values remain authoritative in YAML.")
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
                Layout.fillWidth: true
                Layout.preferredHeight: implicitHeight
                maximumColumns: Math.min(3, root.expectedColumns)
                minimumCardWidth: 300
                objectName: "datasetPrimaryGrid"

                Card {
                    Layout.fillWidth: true
                    subtitle: qsTr(
                                  "Model changes retain incompatible properties and report them explicitly.")
                    title: qsTr("Scientific model")

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
                }

                Card {
                    Layout.fillWidth: true
                    subtitle: qsTr(
                                  "Property tables sample T-p states; saturation tables emit liquid and vapor boundaries; vapor-mass-fraction tables sample equilibrium quality from 0 to 1.")
                    title: qsTr("Dataset mode")

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
                    Layout.fillWidth: true
                    subtitle: qsTr(
                                  "Local checks are immediate; worker validation remains authoritative before Save.")
                    title: qsTr("Configuration state")

                    Label {
                        Layout.fillWidth: true
                        color: root.datasetDraft.locallyValid ? Theme.success : Theme.danger
                        font.family: Theme.sansFamily
                        font.pixelSize: 13
                        font.weight: Font.Medium
                        text: root.datasetDraft.locallyValid ? qsTr(
                                                                   "All Dataset fields are locally valid") :
                                                               root.datasetDraft.issue
                        wrapMode: Text.Wrap
                    }

                    Label {
                        Layout.fillWidth: true
                        color: Theme.textMuted
                        font.family: Theme.sansFamily
                        font.pixelSize: 11
                        text: root.datasetDraft.dirty ? qsTr("Unsaved Dataset changes") : qsTr(
                                                            "Dataset matches its saved baseline")
                    }
                }
            }

            Card {
                Layout.fillWidth: true
                subtitle: qsTr(
                              "Aliases remain visible while canonical fluid identity is checked by the draft.")
                title: qsTr("Fluids")

                ChoiceList {
                    Layout.fillWidth: true
                    choiceModel: root.datasetDraft.fluidChoices
                    emptyText: qsTr("Add at least one fluid")
                    noun: qsTr("fluid")
                    objectName: "datasetFluids"
                    onAddRequested: value => root.fluidAddRequested(value)
                    onMoveRequested: (row, offset) => root.fluidMoveRequested(row, offset)
                    onRemoveRequested: row => root.fluidRemoveRequested(row)
                    selectedModel: root.datasetDraft.selectedFluids
                }
            }

            Label {
                Layout.fillWidth: true
                color: Theme.text
                font.family: Theme.sansFamily
                font.pixelSize: 17
                font.weight: Font.DemiBold
                text: qsTr("Sampling grid")
            }

            ResponsiveCardGrid {
                Layout.fillWidth: true
                Layout.preferredHeight: implicitHeight
                maximumColumns: Math.min(2, root.expectedColumns)
                minimumCardWidth: 360
                objectName: "datasetSamplerGrid"

                Repeater {
                    model: root.datasetDraft.samplerDrafts

                    delegate: SamplerEditor {
                        Layout.fillWidth: true
                        onKindChangeRequested: (draft, kind) => root.samplerKindChangeRequested(
                                                                    draft, kind)
                        onTextChangeRequested: (draft, field, text)
                                               => root.samplerTextChangeRequested(draft, field,
                                                                                  text)
                        onUnitChangeRequested: (draft, unit) => root.samplerUnitChangeRequested(
                                                                    draft, unit)
                    }
                }
            }

            ResponsiveCardGrid {
                Layout.fillWidth: true
                Layout.preferredHeight: implicitHeight
                maximumColumns: Math.min(2, root.expectedColumns)
                minimumCardWidth: 360

                Card {
                    Layout.fillWidth: true
                    subtitle: qsTr(
                                  "Property order is preserved in deterministic YAML and generated columns.")
                    title: qsTr("Properties")

                    ChoiceList {
                        Layout.fillWidth: true
                        choiceModel: root.datasetDraft.propertyChoices
                        emptyText: qsTr("Add at least one property")
                        noun: qsTr("property")
                        objectName: "datasetProperties"
                        onAddRequested: value => root.propertyAddRequested(value)
                        onMoveRequested: (row, offset) => root.propertyMoveRequested(row, offset)
                        onRemoveRequested: row => root.propertyRemoveRequested(row)
                        selectedModel: root.datasetDraft.selectedProperties
                    }
                }

                Card {
                    Layout.fillWidth: true
                    subtitle: qsTr("At least one immutable dataset format is required.")
                    title: qsTr("Dataset outputs")

                    Repeater {
                        model: root.datasetDraft.outputFormats

                        delegate: Item {
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
                                onClicked: root.outputSelectionRequested(parent.value, checked)
                                text: parent.display
                            }
                        }
                    }

                    Label {
                        Layout.fillWidth: true
                        color: Theme.warning
                        font.family: Theme.sansFamily
                        font.pixelSize: 11
                        text: root.datasetDraft.referenceAdvisory
                        visible: text.length > 0
                        wrapMode: Text.Wrap
                    }
                }
            }
        }
    }
}
