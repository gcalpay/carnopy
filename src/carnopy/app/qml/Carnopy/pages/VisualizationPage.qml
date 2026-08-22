pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts
import Carnopy

Item {
    id: root

    required property var visualizationDraft
    required property var configuredResultsController
    required property var sessionPlotController
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
    signal configuredGenerationRequested(string requestId)
    signal configuredOutcomeRequested(int index)
    signal configuredExportRequested(string path)
    signal configuredExploreRunRequested
    signal configuredOpenPdfRequested
    signal configuredSessionEditRequested(int row)
    signal sessionBeginEditRequested(string format)
    signal sessionCancelEditRequested
    signal sessionRenderRequested
    signal sessionForceStopRequested
    signal sessionExportRequested(string path)
    signal sessionOpenPdfRequested
    signal plotExportCompleted(string imagePath, string sidecarPath)

    property string exportTarget: ""
    property string exportFormat: ""

    function showConfiguredPlots() {
        viewTabs.currentIndex = 0;
    }

    function showExploreInspectedData() {
        viewTabs.currentIndex = 1;
    }

    function openExportDialog(target, format) {
        exportTarget = target;
        exportFormat = format;
        exportDialog.nameFilters = format === "svg" ? [qsTr("SVG image (*.svg)")] : (format === "pdf"
                                                                                     ? [qsTr("PDF document (*.pdf)")] :
                                                                                       [qsTr("PNG image (*.png)")]);
        exportDialog.open();
    }

    TabBar {
        id: viewTabs

        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        height: 48
        objectName: "visualizationViewTabs"

        background: Rectangle {
            color: Theme.canvas

            Rectangle {
                anchors.bottom: parent.bottom
                color: Theme.divider
                height: 1
                width: parent.width
            }
        }

        TabButton {
            id: configuredTab

            objectName: "configuredPlotsTab"
            text: qsTr("Automate future plots")

            contentItem: Label {
                color: configuredTab.checked ? Theme.success : Theme.textMuted
                font.family: Theme.sansFamily
                font.pixelSize: 13
                font.weight: configuredTab.checked ? Font.DemiBold : Font.Medium
                horizontalAlignment: Text.AlignHCenter
                text: configuredTab.text
                verticalAlignment: Text.AlignVCenter
            }

            background: Rectangle {
                color: configuredTab.hovered ? Theme.hover : "transparent"

                Rectangle {
                    anchors.bottom: parent.bottom
                    color: Theme.focus
                    height: 2
                    visible: configuredTab.checked
                    width: parent.width
                }
            }
        }

        TabButton {
            id: exploreTab

            objectName: "exploreInspectedDataTab"
            text: qsTr("Plot generated data")

            contentItem: Label {
                color: exploreTab.checked ? Theme.success : Theme.textMuted
                font.family: Theme.sansFamily
                font.pixelSize: 13
                font.weight: exploreTab.checked ? Font.DemiBold : Font.Medium
                horizontalAlignment: Text.AlignHCenter
                text: exploreTab.text
                verticalAlignment: Text.AlignVCenter
            }

            background: Rectangle {
                color: exploreTab.hovered ? Theme.hover : "transparent"

                Rectangle {
                    anchors.bottom: parent.bottom
                    color: Theme.focus
                    height: 2
                    visible: exploreTab.checked
                    width: parent.width
                }
            }
        }
    }

    function focusField(field, row) {
        if (field.indexOf("plot.") === 0) {
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
        anchors.bottom: parent.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: viewTabs.bottom
        boundsBehavior: Flickable.StopAtBounds
        clip: true
        contentHeight: pageColumn.implicitHeight + 40
        contentWidth: width
        flickableDirection: Flickable.VerticalFlick
        objectName: "visualizationPageFlickable"
        pixelAligned: true
        visible: viewTabs.currentIndex === 0

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
                text: qsTr("Automate plots on future runs")
            }

            Label {
                Layout.fillWidth: true
                color: Theme.textMuted
                font.family: Theme.sansFamily
                font.pixelSize: 12
                text: qsTr(
                          "Define reproducible plots in YAML for later runs. They render only during the next Generate; existing runs are unaffected, and editing or opening this page never renders anything.")
                wrapMode: Text.Wrap
            }

            Card {
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                subtitle: root.visualizationDraft.hasActivePlotEdit ? qsTr(
                                                                          "Commit or cancel the temporary plot before changing shared settings.") :
                                                                      qsTr("These defaults apply to every configured plot unless that plot overrides them. Turn plotting off for dataset-only runs; the current edit-session definitions are then omitted from YAML and Generate.")
                title: qsTr("Defaults for configured plots")

                RowLayout {
                    Layout.fillWidth: true

                    Switch {
                        id: enabledSwitch

                        Accessible.name: qsTr("Enable configured visualization")
                        checked: root.visualizationDraft.enabled
                        enabled: !root.visualizationDraft.hasActivePlotEdit
                        objectName: "visualizationEnabledSwitch"
                        onToggled: root.enabledChangeRequested(checked)
                        text: checked ? qsTr("Include plots during Generate") : qsTr(
                                            "Dataset only — do not generate plots")
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
                            text: qsTr("Default output format")
                        }

                        AppComboBox {
                            id: formatBox

                            Accessible.name: qsTr("Default configured plot format")
                            Layout.fillWidth: true
                            currentIndex: indexForRoleValue(root.visualizationDraft.format)
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

                Label {
                    Layout.fillWidth: true
                    color: Theme.textMuted
                    font.family: Theme.sansFamily
                    font.pixelSize: 11
                    text: qsTr(
                              "These plots are saved in YAML and render during the next Generate. To try one with the currently inspected dataset, use Preview with inspected data.")
                    wrapMode: Text.Wrap
                }

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
                        height: issue.length > 0 ? 112 : 84
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

                            RowLayout {
                                Layout.fillWidth: true

                                Label {
                                    Layout.fillWidth: true
                                    color: Theme.textMuted
                                    elide: Text.ElideRight
                                    font.family: Theme.sansFamily
                                    font.pixelSize: 11
                                    text: root.sessionPlotController.canBeginEdit ? qsTr(
                                                                                        "Apply this saved definition to the inspected dataset without changing YAML.") :
                                                                                    qsTr("Inspect a dataset to preview this saved definition.")
                                }

                                AppButton {
                                    Accessible.name: qsTr(
                                                         "Preview configured plot with inspected data")
                                    enabled: root.visualizationDraft.enabled && plotRow.compatible
                                             && !root.visualizationDraft.hasActivePlotEdit
                                             && root.sessionPlotController.canBeginEdit
                                    objectName: "visualizationUsePlot-" + plotRow.index
                                    onClicked: root.configuredSessionEditRequested(plotRow.index)
                                    text: qsTr("Preview with inspected data")
                                    tone: "primary"
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

                Loader {
                    id: activePlotEditor

                    readonly property PlotEditor loadedEditor: item as PlotEditor

                    active: root.visualizationDraft.hasActivePlotEdit
                    Layout.fillWidth: true
                    Layout.preferredHeight: loadedEditor === null ? 0 : loadedEditor.implicitHeight
                    objectName: "activePlotEditor"
                    sourceComponent: PlotEditor {
                        attentionField: root.attentionField
                        attentionRow: root.attentionRow
                        attentionSerial: root.attentionSerial
                        draft: root.visualizationDraft.activePlotDraft
                        onCancelRequested: root.cancelPlotRequested()
                        onCommitRequested: root.commitPlotRequested()
                        onFieldChangeRequested: (draft, field, value)
                                                => root.plotFieldChangeRequested(draft, field,
                                                                                 value)
                        onFluidSelectionRequested: (draft, value, selected)
                                                   => root.plotFluidSelectionRequested(draft, value,
                                                                                       selected)
                        onMappingAddRequested: model => root.mappingAddRequested(model)
                        onMappingFieldChangeRequested: (model, row, field)
                                                       => root.mappingFieldChangeRequested(model,
                                                                                           row, field)
                        onMappingRemoveRequested: (model, row) => root.mappingRemoveRequested(model,
                                                                                              row)
                        onMappingValueChangeRequested: (model, row, value)
                                                       => root.mappingValueChangeRequested(model,
                                                                                           row, value)
                    }
                }
            }

            Card {
                Layout.fillWidth: true
                subtitle: qsTr(
                              "Select a successful generation record explicitly. Only its ordered report outcomes are verified and shown; directories are never scanned for plots.")
                title: qsTr("Generated configured results")

                GridLayout {
                    id: configuredResultsGrid

                    readonly property real listHeight: Math.max(72, Math.min(220, Math.max(
                                                                                 generationList.count,
                                                                                 outcomeList.count)
                                                                             * 44))

                    Layout.fillWidth: true
                    columnSpacing: Theme.spacingMedium
                    columns: root.width >= 1080 ? 3 : 1
                    objectName: "configuredResultsGrid"
                    rowSpacing: Theme.spacingMedium

                    ColumnLayout {
                        Layout.alignment: Qt.AlignTop
                        Layout.fillWidth: true
                        Layout.minimumWidth: 220
                        objectName: "configuredGenerationColumn"

                        Label {
                            color: Theme.text
                            font.family: Theme.sansFamily
                            font.weight: Font.Medium
                            text: qsTr("Generated runs")
                        }

                        ListView {
                            id: generationList

                            Layout.fillWidth: true
                            Layout.preferredHeight: configuredResultsGrid.listHeight
                            boundsBehavior: Flickable.StopAtBounds
                            clip: true
                            model: root.configuredResultsController.generationRecordsModel
                            objectName: "configuredPlotGenerationList"
                            spacing: Theme.spacingTiny

                            delegate: AppButton {
                                required property string configurationPath
                                required property string createdAtUtc
                                required property bool hasRecordedVisualization
                                required property string requestId
                                required property string runId

                                width: ListView.view.width
                                enabled: true
                                objectName: "configuredPlotGeneration-" + requestId
                                onClicked: root.configuredGenerationRequested(requestId)
                                text: (runId.length > 0 ? runId : requestId.substring(0, 12)) + (
                                          hasRecordedVisualization ? "" : qsTr(
                                                                         " · no configured plots"))
                                tone: root.configuredResultsController.selectedRecordId
                                      === requestId ? "primary" : "secondary"
                            }
                        }
                    }

                    ColumnLayout {
                        Layout.alignment: Qt.AlignTop
                        Layout.fillWidth: true
                        Layout.minimumWidth: 220
                        objectName: "configuredOutcomeColumn"

                        Label {
                            color: Theme.text
                            font.family: Theme.sansFamily
                            font.weight: Font.Medium
                            text: qsTr("Report outcomes")
                        }

                        ListView {
                            id: outcomeList

                            Layout.fillWidth: true
                            Layout.preferredHeight: configuredResultsGrid.listHeight
                            boundsBehavior: Flickable.StopAtBounds
                            clip: true
                            model: root.configuredResultsController.outcomesModel
                            objectName: "configuredPlotOutcomeList"
                            spacing: Theme.spacingTiny

                            delegate: AppButton {
                                required property string format
                                required property int index
                                required property string kind
                                required property string name
                                required property string status

                                width: ListView.view.width
                                enabled: status === "completed"
                                objectName: "configuredPlotOutcome-" + index
                                onClicked: root.configuredOutcomeRequested(index)
                                text: name + " · " + kind + (format.length > 0 ? " · "
                                                                                 + format.toUpperCase(
                                                                                     ) : "")
                                tone: root.configuredResultsController.selectedOutcomeIndex
                                      === index ? "primary" : "secondary"
                            }
                        }
                    }

                    ColumnLayout {
                        Layout.alignment: Qt.AlignTop
                        Layout.fillWidth: true
                        Layout.minimumWidth: 300
                        objectName: "configuredPreviewColumn"

                        Label {
                            color: Theme.text
                            font.family: Theme.sansFamily
                            font.weight: Font.Medium
                            text: qsTr("Selected result")
                        }

                        StatusBadge {
                            label: root.configuredResultsController.evidenceLabel.length > 0
                                   ? root.configuredResultsController.evidenceLabel : qsTr(
                                         "No evidence selected")
                            tone: root.configuredResultsController.state === "consistent"
                                  ? "success" : (root.configuredResultsController.state
                                                 === "mismatch" ? "danger" : "neutral")
                        }

                        Label {
                            Layout.fillWidth: true
                            color: Theme.textMuted
                            font.family: Theme.sansFamily
                            font.pixelSize: 12
                            text: root.configuredResultsController.issue
                            visible: text.length > 0
                            wrapMode: Text.Wrap
                        }

                        AppButton {
                            Layout.fillWidth: true
                            enabled: root.configuredResultsController.canExploreRun
                            objectName: "configuredExploreRunButton"
                            onClicked: root.configuredExploreRunRequested()
                            text: qsTr("Create plot from this run")
                            tone: "primary"
                            visible: root.configuredResultsController.selectedRecordId.length > 0
                                     && !root.configuredResultsController.canExport
                        }

                        VerifiedPlotView {
                            Layout.fillWidth: true
                            canExport: root.configuredResultsController.canExport
                            canOpenPdf: root.configuredResultsController.canOpenPdf
                            canPreview: root.configuredResultsController.canPreview
                            excludedSampleCount:
                            root.configuredResultsController.selectedExcludedSampleCount
                            format: root.configuredResultsController.selectedFormat
                            objectName: "configuredVerifiedPlotView"
                            plotKind: root.configuredResultsController.selectedKind
                            plotName: root.configuredResultsController.selectedName
                            previewSource: root.configuredResultsController.previewUrl
                            validSampleCount:
                            root.configuredResultsController.selectedValidSampleCount
                            visible: root.configuredResultsController.canExport
                            onExportRequested: root.openExportDialog("configured",
                                                                     root.configuredResultsController.selectedFormat)
                            onOpenPdfRequested: root.configuredOpenPdfRequested()
                        }
                    }
                }

                Label {
                    Layout.fillWidth: true
                    color: Theme.textMuted
                    font.family: Theme.sansFamily
                    font.pixelSize: 11
                    text: root.configuredResultsController.resultRelationIssue
                    visible: text.length > 0
                    wrapMode: Text.Wrap
                }
            }

            ValidationIssue {
                Layout.fillWidth: true
                field: root.visualizationDraft.firstInvalidField
                issue: root.visualizationDraft.issue
            }
        }
    }

    Flickable {
        id: exploreFlickable

        anchors.bottom: parent.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: viewTabs.bottom
        boundsBehavior: Flickable.StopAtBounds
        clip: true
        contentHeight: exploreColumn.implicitHeight + 40
        contentWidth: width
        flickableDirection: Flickable.VerticalFlick
        objectName: "sessionPlotPageFlickable"
        pixelAligned: true
        visible: viewTabs.currentIndex === 1

        ScrollBar.vertical: ScrollBar {
            policy: ScrollBar.AsNeeded
        }

        ColumnLayout {
            id: exploreColumn

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
                text: qsTr("Plot generated data")
            }

            Label {
                Layout.fillWidth: true
                color: Theme.textMuted
                font.family: Theme.sansFamily
                font.pixelSize: 12
                text: qsTr(
                          "Create an ad-hoc, session-only plot from the currently inspected dataset. Carnopy starts with a compatible editable request; review or change it, then render explicitly. This never changes the saved YAML.")
                wrapMode: Text.Wrap
            }

            Card {
                Layout.fillWidth: true
                subtitle: root.sessionPlotController.sourcePath.length > 0
                          ? root.sessionPlotController.sourcePath : qsTr(
                                "Inspect a generated dataset source before creating a session plot.")
                title: qsTr("Inspected source")

                RowLayout {
                    Layout.fillWidth: true

                    StatusBadge {
                        label: root.sessionPlotController.sourcePath.length > 0 ? qsTr(
                                                                                      "Source ready") :
                                                                                  qsTr("No dataset source")
                        tone: root.sessionPlotController.sourcePath.length > 0 ? "success" :
                                                                                 "neutral"
                    }

                    Item {
                        Layout.fillWidth: true
                    }

                    AppComboBox {
                        id: newSessionFormat

                        Accessible.name: qsTr("Session plot output format")
                        Layout.preferredWidth: 140
                        model: ["png", "svg", "pdf"]
                        objectName: "sessionPlotFormatBox"
                    }

                    AppButton {
                        enabled: root.sessionPlotController.canBeginEdit
                        objectName: "sessionPlotBeginButton"
                        onClicked: root.sessionBeginEditRequested(String(
                                                                      newSessionFormat.currentText))
                        text: root.sessionPlotController.hasResult ? qsTr(
                                                                         "Edit current session plot") :
                                                                     qsTr("Create plot from inspected data")
                        tone: "primary"
                    }
                }
            }

            Card {
                Layout.fillWidth: true
                subtitle: qsTr(
                              "This unresolved edit is session state, not YAML dirty state. Render commits one result; Cancel returns to the last committed result.")
                title: qsTr("Session plot editor")
                visible: root.sessionPlotController.hasActiveEdit

                Loader {
                    id: sessionPlotEditor

                    readonly property PlotEditor loadedEditor: item as PlotEditor

                    active: root.sessionPlotController.hasActiveEdit
                    Layout.fillWidth: true
                    Layout.preferredHeight: loadedEditor === null ? 0 : loadedEditor.implicitHeight
                    objectName: "sessionPlotEditor"
                    sourceComponent: PlotEditor {
                        attentionField: root.attentionField
                        attentionRow: root.attentionRow
                        attentionSerial: root.attentionSerial
                        draft: root.sessionPlotController.activePlotDraft
                        fluidEmptyText: qsTr("Select at least one inspected-source fluid.")
                        fluidSelectionHelp: qsTr(
                                                "All inspected-source fluids are selected by default. Remove any fluid you do not want to render.")
                        primaryActionText: qsTr("Render plot")
                        onCancelRequested: root.sessionCancelEditRequested()
                        onCommitRequested: root.sessionRenderRequested()
                        onFieldChangeRequested: (draft, field, value)
                                                => root.plotFieldChangeRequested(draft, field,
                                                                                 value)
                        onFluidSelectionRequested: (draft, value, selected)
                                                   => root.plotFluidSelectionRequested(draft, value,
                                                                                       selected)
                        onMappingAddRequested: model => root.mappingAddRequested(model)
                        onMappingFieldChangeRequested: (model, row, field)
                                                       => root.mappingFieldChangeRequested(model,
                                                                                           row, field)
                        onMappingRemoveRequested: (model, row) => root.mappingRemoveRequested(model,
                                                                                              row)
                        onMappingValueChangeRequested: (model, row, value)
                                                       => root.mappingValueChangeRequested(model,
                                                                                           row, value)
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    visible: root.sessionPlotController.isRendering

                    BusyIndicator {
                        running: visible
                        visible: root.sessionPlotController.isRendering
                    }

                    Label {
                        Layout.fillWidth: true
                        color: Theme.textMuted
                        font.family: Theme.sansFamily
                        text: root.sessionPlotController.phase
                    }

                    AppButton {
                        enabled: root.sessionPlotController.canForceStop
                        objectName: "sessionPlotForceStopButton"
                        onClicked: root.sessionForceStopRequested()
                        text: qsTr("Force stop")
                        tone: "danger"
                    }
                }
            }

            Card {
                Layout.fillWidth: true
                subtitle: qsTr(
                              "The preview is hash-verified against its worker result and provenance sidecar before exposure.")
                title: qsTr("Session result")
                visible: root.sessionPlotController.hasResult

                VerifiedPlotView {
                    Layout.fillWidth: true
                    canExport: root.sessionPlotController.canExport
                    canOpenPdf: root.sessionPlotController.canOpenPdf
                    canPreview: root.sessionPlotController.canPreview
                    excludedSampleCount: root.sessionPlotController.excludedSampleCount
                    format: root.sessionPlotController.resultFormat
                    objectName: "sessionVerifiedPlotView"
                    plotKind: root.sessionPlotController.resultKind
                    plotName: root.sessionPlotController.resultName
                    previewSource: root.sessionPlotController.previewUrl
                    validSampleCount: root.sessionPlotController.validSampleCount
                    onExportRequested: root.openExportDialog("session",
                                                             root.sessionPlotController.resultFormat)
                    onOpenPdfRequested: root.sessionOpenPdfRequested()
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: sessionAdvisory.implicitHeight + 20
                    border.color: Theme.warning
                    border.width: 1
                    color: Theme.warningSoft
                    radius: Theme.radiusSmall
                    visible: root.sessionPlotController.advisoryText.length > 0

                    Label {
                        id: sessionAdvisory

                        anchors.left: parent.left
                        anchors.leftMargin: 12
                        anchors.right: parent.right
                        anchors.rightMargin: 12
                        anchors.verticalCenter: parent.verticalCenter
                        color: Theme.text
                        font.family: Theme.sansFamily
                        font.pixelSize: 12
                        text: root.sessionPlotController.advisoryText
                        wrapMode: Text.Wrap
                    }
                }
            }

            ValidationIssue {
                Layout.fillWidth: true
                field: root.sessionPlotController.issueCode
                issue: root.sessionPlotController.issue
            }
        }
    }

    FileDialog {
        id: exportDialog

        acceptLabel: qsTr("Export")
        fileMode: FileDialog.SaveFile
        objectName: "plotExportDialog"
        title: qsTr("Export verified plot bundle")

        onAccepted: {
            const destination = String(selectedFile);
            Qt.callLater(function () {
                if (root.exportTarget === "configured")
                    root.configuredExportRequested(destination);
                else if (root.exportTarget === "session")
                    root.sessionExportRequested(destination);
                root.exportTarget = "";
            });
        }
        onRejected: root.exportTarget = ""
    }

    Connections {
        function onExportSucceeded(imagePath, sidecarPath) {
            root.plotExportCompleted(imagePath, sidecarPath);
        }

        target: root.configuredResultsController
    }

    Connections {
        function onExportSucceeded(imagePath, sidecarPath) {
            root.plotExportCompleted(imagePath, sidecarPath);
        }

        target: root.sessionPlotController
    }
}
