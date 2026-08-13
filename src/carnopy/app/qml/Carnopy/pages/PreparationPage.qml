pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Carnopy

Item {
    id: root

    required property var configController
    required property var desktopController
    required property var inspectionController
    required property var preparationDraft
    required property var workflowController
    property string actionMessage: ""
    property string attentionField: ""
    property int attentionRow: -1
    property int attentionSerial: 0
    property bool dialogsEnabled: true
    property int expectedColumns: 1
    property string pendingCategoryField: ""
    property string pendingCategoryMode: ""
    property string scenarioAttentionField: ""
    property int scenarioAttentionRow: -1
    property int scenarioAttentionSerial: 0
    readonly property bool documentActive: configController.documentKind === "preparation"
    readonly property bool locked: !documentActive || !configController.canEdit

    signal categoryModeDialogRequested
    signal inspectSourceRequested
    signal workspaceRequested

    function reveal(item) {
        if (item === null || item === undefined)
            return;
        const position = item.mapToItem(pageFlickable.contentItem, 0, 0);
        const maximum = Math.max(0, pageFlickable.contentHeight - pageFlickable.height);
        pageFlickable.contentY = Math.min(maximum, Math.max(0, position.y - 80));
    }

    function focusField(field, row) {
        let target = numericCard;
        if (field.indexOf("scenario") >= 0) {
            const editor = activeScenarioLoader.item;
            if (editor !== null) {
                root.scenarioAttentionField = field;
                root.scenarioAttentionRow = row;
                root.scenarioAttentionSerial += 1;
                root.reveal(editor);
                return;
            }
            scenarioList.currentIndex = row;
            target = scenariosCard;
        } else if (field.indexOf("source_policy") >= 0) {
            target = partialSweepCheck;
        } else if (field.indexOf("source") >= 0) {
            target = sourceCard;
        } else if (field.indexOf("categorical") >= 0) {
            target = categoricalCard;
        } else if (field.indexOf("targets") >= 0) {
            target = targetCard;
        } else if (field.indexOf("auxiliary") >= 0) {
            target = auxiliaryCard;
        } else if (field.indexOf("derived") >= 0) {
            target = derivedCard;
        } else if (field.indexOf("outputs") >= 0 || field.indexOf("dependency") >= 0) {
            target = outputsCard;
        } else if (field.indexOf("baseline") >= 0) {
            target = baselineCheck;
        } else if (field.indexOf("matrix") >= 0 || field.indexOf("correlation") >= 0 || field.indexOf(
                       "spread") >= 0) {
            target = matrixCheck;
        } else if (field.indexOf("numeric") >= 0 || field.indexOf("features") >= 0) {
            target = numericCard;
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

        target: root.preparationDraft
    }

    Flickable {
        id: pageFlickable

        anchors.fill: parent
        boundsBehavior: Flickable.StopAtBounds
        clip: true
        contentHeight: pageColumn.implicitHeight + 48
        contentWidth: width
        flickableDirection: Flickable.VerticalFlick
        objectName: "preparationPageFlickable"
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
                        text: qsTr("ML Preparation configuration")
                    }

                    Label {
                        Layout.fillWidth: true
                        color: Theme.textMuted
                        font.family: Theme.sansFamily
                        font.pixelSize: 12
                        text: qsTr(
                                  "Define portable preparation policy while keeping the immutable source as explicit execution context.")
                        wrapMode: Text.Wrap
                    }
                }

                StatusBadge {
                    label: !root.documentActive ? qsTr("No Preparation document") : (
                                                      root.preparationDraft.hasActiveScenarioEdit
                                                      ? qsTr("Scenario edit open") : (
                                                            root.preparationDraft.locallyValid
                                                            ? qsTr("Locally complete") : qsTr(
                                                                  "Needs attention")))
                    objectName: "preparationLocalState"
                    tone: !root.documentActive ? "neutral" : (
                                                     root.preparationDraft.hasActiveScenarioEdit
                                                     ? "warning" : (
                                                           root.preparationDraft.locallyValid
                                                           ? "success" : "danger"))
                }
            }

            Card {
                Layout.fillWidth: true
                objectName: "preparationNoDocumentCard"
                subtitle: qsTr(
                              "Create or open an ML Preparation configuration. A retained finalized result remains inspectable below.")
                title: qsTr("No ML Preparation configuration is active")
                visible: !root.documentActive

                AppButton {
                    objectName: "preparationOpenWorkspaceButton"
                    onClicked: root.workspaceRequested()
                    text: qsTr("Open Workspace")
                    tone: "primary"
                }
            }

            BlockingBanner {
                Layout.fillWidth: true
                field: root.preparationDraft.firstInvalidField
                message: root.preparationDraft.issue
                row: root.preparationDraft.firstInvalidRow
                section: "preparation"
                title: qsTr("Preparation configuration needs attention")
                visible: root.documentActive && !root.preparationDraft.locallyValid
                onActionRequested: (section, field, row) => root.focusField(field, row)
            }

            ValidationIssue {
                Layout.fillWidth: true
                field: root.preparationDraft.firstInvalidField
                issue: root.actionMessage
                objectName: "preparationActionMessage"
            }

            Card {
                id: sourceCard

                Layout.fillWidth: true
                activeFocusOnTab: true
                meta: root.workflowController.hasBoundSource ? qsTr("Bound") : qsTr("Required")
                metaColor: root.workflowController.hasBoundSource ? Theme.success : Theme.warning
                objectName: "preparationBoundSourceCard"
                sectionNumber: "1"
                subtitle: root.workflowController.hasBoundSource
                          ? root.workflowController.boundSourcePath : qsTr(
                                "Inspect an eligible finalized Dataset or Model Sweep, then bind that exact verified revision explicitly.")
                title: qsTr("Explicit source context")
                visible: root.documentActive

                Flow {
                    Layout.fillWidth: true
                    spacing: Theme.spacingSmall

                    StatusBadge {
                        label: root.workflowController.boundSourceRefreshAvailable ? qsTr(
                                                                                         "Refresh available") :
                                                                                     (root.workflowController.hasBoundSource
                                                                                      ? root.workflowController.boundSourceKind :
                                                                                        qsTr("Unbound"))
                        objectName: "preparationBoundSourceState"
                        tone: root.workflowController.boundSourceRefreshAvailable ? "warning" : (
                                                                                        root.workflowController.hasBoundSource
                                                                                        ? "success" :
                                                                                          "warning")
                    }

                    Label {
                        color: Theme.textMuted
                        elide: Text.ElideMiddle
                        font.family: Theme.monoFamily
                        font.pixelSize: 10
                        text: root.workflowController.hasBoundSource
                              ? root.workflowController.boundSourceRevision : ""
                        visible: text.length > 0
                    }
                }

                Label {
                    Layout.fillWidth: true
                    color: Theme.warning
                    font.family: Theme.sansFamily
                    font.pixelSize: 11
                    text: qsTr(
                              "A refreshed inspection is available. Rebinding is explicit and will stale the current plan without changing YAML.")
                    visible: root.workflowController.boundSourceRefreshAvailable
                    wrapMode: Text.Wrap
                }

                Label {
                    Layout.fillWidth: true
                    color: Theme.warning
                    font.family: Theme.sansFamily
                    font.pixelSize: 11
                    text: root.workflowController.sourceBindingIssue.length > 0
                          ? root.workflowController.sourceBindingIssue :
                            root.preparationDraft.sourceIssue
                    visible: text.length > 0
                    wrapMode: Text.Wrap
                }

                Flow {
                    Layout.fillWidth: true
                    spacing: Theme.spacingSmall

                    AppButton {
                        enabled: root.workflowController.inspectedSourceAvailable
                                 && root.inspectionController.canInspect &&
                                 !root.workflowController.operationActive
                        objectName: "preparationUseInspectedSource"
                        onClicked: root.desktopController.requestBindInspectedPreparationSource()
                        text: root.workflowController.boundSourceRefreshAvailable ? qsTr(
                                                                                        "Use refreshed source") :
                                                                                    qsTr("Use inspected source")
                        visible: root.inspectionController.preparationEligible
                    }

                    AppButton {
                        objectName: "preparationChangeSource"
                        onClicked: root.inspectSourceRequested()
                        text: root.workflowController.hasBoundSource ? qsTr(
                                                                           "Inspect or change source") :
                                                                       qsTr("Choose source in Inspect")
                        tone: root.workflowController.hasBoundSource ? "quiet" : "primary"
                    }

                    AppButton {
                        enabled: root.workflowController.hasBoundSource &&
                                 !root.workflowController.operationActive
                        objectName: "preparationClearSource"
                        onClicked: root.desktopController.requestClearPreparationSource(false)
                        text: qsTr("Clear source")
                        tone: "danger"
                        visible: root.workflowController.hasBoundSource
                    }
                }
            }

            ResponsiveCardGrid {
                Layout.fillWidth: true
                Layout.preferredHeight: implicitHeight
                maximumColumns: Math.min(3, root.expectedColumns)
                minimumCardWidth: 300
                objectName: "preparationRolesGrid"
                uniformHeights: false
                visible: root.documentActive

                Card {
                    id: numericCard

                    Layout.fillWidth: true
                    activeFocusOnTab: true
                    objectName: "preparationNumericFeaturesCard"
                    sectionNumber: "2"
                    subtitle: qsTr(
                                  "Unavailable imported selections remain visible and blocking until resolved explicitly.")
                    title: qsTr("Numeric features")

                    Repeater {
                        model: root.preparationDraft.numericChoices

                        delegate: Item {
                            required property bool compatible
                            required property string display
                            required property int index
                            required property string issue
                            required property bool selected
                            required property string value

                            implicitHeight: numericCheck.implicitHeight
                            implicitWidth: numericCheck.implicitWidth

                            CheckBox {
                                id: numericCheck

                                Accessible.description: parent.issue
                                Accessible.name: qsTr("Use %1 as a numeric feature").arg(
                                                     parent.display)
                                checked: parent.selected
                                enabled: !root.locked && (parent.compatible || parent.selected)
                                objectName: "preparationNumeric-" + parent.value
                                onClicked: root.desktopController.requestPreparationRoleSelection(
                                               "numeric", parent.value, checked)
                                text: parent.display

                                ToolTip.text: parent.issue
                                ToolTip.visible: hovered && parent.issue.length > 0
                            }
                        }
                    }
                }

                Card {
                    id: derivedCard

                    Layout.fillWidth: true
                    activeFocusOnTab: true
                    objectName: "preparationDerivedFeaturesCard"
                    sectionNumber: "3"
                    subtitle: qsTr(
                                  "Critical-property prerequisites come from the bound worker profile.")
                    title: qsTr("Derived features")

                    Repeater {
                        model: root.preparationDraft.derivedChoices

                        delegate: Item {
                            required property bool compatible
                            required property string display
                            required property int index
                            required property string issue
                            required property bool selected
                            required property string value

                            implicitHeight: derivedCheck.implicitHeight
                            implicitWidth: derivedCheck.implicitWidth

                            CheckBox {
                                id: derivedCheck

                                Accessible.description: parent.issue
                                Accessible.name: qsTr("Use %1 as a derived feature").arg(
                                                     parent.display)
                                checked: parent.selected
                                enabled: !root.locked && (parent.compatible || parent.selected)
                                objectName: "preparationDerived-" + parent.value
                                onClicked: root.desktopController.requestPreparationRoleSelection(
                                               "derived", parent.value, checked)
                                text: parent.display

                                ToolTip.text: parent.issue
                                ToolTip.visible: hovered && parent.issue.length > 0
                            }
                        }
                    }
                }

                Card {
                    id: targetCard

                    Layout.fillWidth: true
                    activeFocusOnTab: true
                    objectName: "preparationTargetsCard"
                    sectionNumber: "4"
                    subtitle: qsTr(
                                  "At least one target is required by the unchanged public schema.")
                    title: qsTr("Targets")

                    Repeater {
                        model: root.preparationDraft.targetChoices

                        delegate: Item {
                            required property bool compatible
                            required property string display
                            required property int index
                            required property string issue
                            required property bool selected
                            required property string value

                            implicitHeight: targetCheck.implicitHeight
                            implicitWidth: targetCheck.implicitWidth

                            CheckBox {
                                id: targetCheck

                                Accessible.description: parent.issue
                                Accessible.name: qsTr("Use %1 as a target").arg(parent.display)
                                checked: parent.selected
                                enabled: !root.locked && (parent.compatible || parent.selected)
                                objectName: "preparationTarget-" + parent.value
                                onClicked: root.desktopController.requestPreparationRoleSelection(
                                               "target", parent.value, checked)
                                text: parent.display

                                ToolTip.text: parent.issue
                                ToolTip.visible: hovered && parent.issue.length > 0
                            }
                        }
                    }
                }

                Card {
                    id: auxiliaryCard

                    Layout.fillWidth: true
                    activeFocusOnTab: true
                    objectName: "preparationAuxiliaryCard"
                    sectionNumber: "5"
                    subtitle: qsTr(
                                  "Auxiliary fields retain source context without becoming model features.")
                    title: qsTr("Auxiliary fields")

                    Repeater {
                        model: root.preparationDraft.auxiliaryChoices

                        delegate: Item {
                            required property bool compatible
                            required property string display
                            required property int index
                            required property string issue
                            required property bool selected
                            required property string value

                            implicitHeight: auxiliaryCheck.implicitHeight
                            implicitWidth: auxiliaryCheck.implicitWidth

                            CheckBox {
                                id: auxiliaryCheck

                                Accessible.description: parent.issue
                                Accessible.name: qsTr("Use %1 as an auxiliary field").arg(
                                                     parent.display)
                                checked: parent.selected
                                enabled: !root.locked && (parent.compatible || parent.selected)
                                objectName: "preparationAuxiliary-" + parent.value
                                onClicked: root.desktopController.requestPreparationRoleSelection(
                                               "auxiliary", parent.value, checked)
                                text: parent.display

                                ToolTip.text: parent.issue
                                ToolTip.visible: hovered && parent.issue.length > 0
                            }
                        }
                    }
                }

                Card {
                    id: categoricalCard

                    Layout.fillWidth: true
                    activeFocusOnTab: true
                    objectName: "preparationCategoricalCard"
                    sectionNumber: "6"
                    subtitle: qsTr(
                                  "Observed values come from the bound profile; explicit category order is serialized exactly.")
                    title: qsTr("Categorical features")

                    Repeater {
                        id: categoricalRepeater

                        model: root.preparationDraft.categoricalChoices

                        delegate: ColumnLayout {
                            id: categoryRow

                            required property bool compatible
                            required property string display
                            required property int index
                            required property string issue
                            required property bool selected
                            required property string value

                            Layout.fillWidth: true
                            objectName: "preparationCategoricalRow-" + categoryRow.index

                            CheckBox {
                                id: categoryCheck

                                Accessible.description: categoryRow.issue
                                Accessible.name: qsTr("Use %1 as a categorical feature").arg(
                                                     categoryRow.display)
                                checked: categoryRow.selected
                                enabled: !root.locked && (categoryRow.compatible
                                                          || categoryRow.selected)
                                objectName: "preparationCategorical-" + categoryRow.value
                                onClicked:
                                root.desktopController.requestPreparationCategoricalSelection(
                                    categoryRow.value, checked)
                                text: categoryRow.display

                                ToolTip.text: categoryRow.issue
                                ToolTip.visible: hovered && categoryRow.issue.length > 0
                            }

                            AppComboBox {
                                id: categoryMode

                                Accessible.name: qsTr("Category source for %1").arg(
                                                     categoryRow.display)
                                Layout.fillWidth: true
                                currentIndex: indexForRoleValue(root.preparationDraft.category_mode(
                                                                    categoryRow.value))
                                enabled: !root.locked && categoryRow.selected
                                model: ["observed", "explicit"]
                                objectName: "preparationCategoryMode-" + categoryRow.value
                                onActivated: {
                                    const selectedMode = String(currentValue);
                                    if (selectedMode === root.preparationDraft.category_mode(
                                            categoryRow.value))
                                    return;
                                    if (selectedMode === "observed"
                                        && root.preparationDraft.explicit_categories_text(
                                            categoryRow.value).length > 0) {
                                        root.pendingCategoryField = categoryRow.value;
                                        root.pendingCategoryMode = selectedMode;
                                        root.categoryModeDialogRequested();
                                    } else {
                                        root.desktopController.requestPreparationCategoryMode(
                                            categoryRow.value, selectedMode, false);
                                    }
                                }
                                visible: categoryRow.selected
                            }

                            TextField {
                                Accessible.name: qsTr("Explicit categories for %1").arg(
                                                     categoryRow.display)
                                Layout.fillWidth: true
                                enabled: !root.locked && categoryRow.selected
                                objectName: "preparationExplicitCategories-" + categoryRow.value
                                onEditingFinished:
                                root.desktopController.requestPreparationExplicitCategories(
                                    categoryRow.value, text)
                                placeholderText: qsTr("Comma-separated categories")
                                selectByMouse: true
                                text: root.preparationDraft.explicit_categories_text(
                                          categoryRow.value)
                                visible: categoryRow.selected && categoryMode.currentValue
                                         === "explicit"
                            }

                            Label {
                                Layout.fillWidth: true
                                color: Theme.textMuted
                                font.family: Theme.sansFamily
                                font.pixelSize: 10
                                text: qsTr("Observed: %1").arg(
                                          root.preparationDraft.observed_categories(
                                              categoryRow.value).join(", "))
                                visible: categoryRow.selected && categoryMode.currentValue
                                         === "observed"
                                wrapMode: Text.Wrap
                            }
                        }
                    }
                }
            }

            Card {
                id: scenariosCard

                Layout.fillWidth: true
                activeFocusOnTab: true
                objectName: "preparationScenariosCard"
                subtitle: qsTr(
                              "All eight public scenario kinds are available. Committed order is exact and deterministic.")
                title: qsTr("Scenarios")
                visible: root.documentActive

                RowLayout {
                    Layout.fillWidth: true

                    CheckBox {
                        id: partialSweepCheck

                        Accessible.description: qsTr(
                                                    "This policy never changes the bound source or Preparation YAML roles")
                        Accessible.name: qsTr("Allow an eligible partial Model Sweep source")
                        checked: root.preparationDraft.allowPartialSweep
                        enabled: !root.locked && root.workflowController.boundSourceKind
                                 === "model_sweep"
                        objectName: "preparationAllowPartialSweep"
                        onClicked: root.desktopController.requestPreparationBooleanField(
                                       "allow_partial_sweep", checked)
                        text: qsTr("Allow eligible partial Sweep sources")
                    }

                    Item {
                        Layout.fillWidth: true
                    }

                    AppButton {
                        Accessible.description: qsTr("Open a temporary Preparation scenario editor")
                        enabled: !root.locked && !root.preparationDraft.hasActiveScenarioEdit
                        objectName: "preparationAddScenario"
                        onClicked: root.desktopController.requestPreparationAddScenario()
                        text: qsTr("Add scenario")
                        tone: "primary"
                    }
                }

                ListView {
                    id: scenarioList

                    Accessible.name: qsTr("Committed Preparation scenarios")
                    Layout.fillWidth: true
                    Layout.preferredHeight: Math.max(52, Math.min(280, contentHeight))
                    boundsBehavior: Flickable.StopAtBounds
                    clip: true
                    interactive: contentHeight > height
                    model: root.preparationDraft.scenarios
                    objectName: "preparationScenarioList"
                    pixelAligned: true
                    spacing: Theme.spacingTiny

                    delegate: RowLayout {
                        id: scenarioRow

                        required property int index
                        required property string name
                        required property string summary

                        width: ListView.view.width

                        Label {
                            Layout.fillWidth: true
                            color: Theme.text
                            font.family: Theme.sansFamily
                            font.pixelSize: 12
                            text: scenarioRow.name + " · " + scenarioRow.summary
                            wrapMode: Text.Wrap
                        }

                        AppButton {
                            Accessible.description: qsTr("Edit scenario %1").arg(scenarioRow.name)
                            compact: true
                            enabled: !root.locked && !root.preparationDraft.hasActiveScenarioEdit
                            objectName: "preparationScenarioEdit-" + scenarioRow.index
                            onClicked: root.desktopController.requestPreparationEditScenario(
                                           scenarioRow.index)
                            text: qsTr("Edit")
                        }

                        AppButton {
                            Accessible.description: qsTr("Move scenario %1 earlier").arg(
                                                        scenarioRow.name)
                            compact: true
                            enabled: !root.locked && !root.preparationDraft.hasActiveScenarioEdit
                                     && scenarioRow.index > 0
                            objectName: "preparationScenarioUp-" + scenarioRow.index
                            onClicked: root.desktopController.requestPreparationMoveScenario(
                                           scenarioRow.index, scenarioRow.index - 1)
                            text: qsTr("Up")
                        }

                        AppButton {
                            Accessible.description: qsTr("Move scenario %1 later").arg(
                                                        scenarioRow.name)
                            compact: true
                            enabled: !root.locked && !root.preparationDraft.hasActiveScenarioEdit
                                     && scenarioRow.index + 1 < scenarioList.count
                            objectName: "preparationScenarioDown-" + scenarioRow.index
                            onClicked: root.desktopController.requestPreparationMoveScenario(
                                           scenarioRow.index, scenarioRow.index + 1)
                            text: qsTr("Down")
                        }

                        AppButton {
                            Accessible.description: qsTr("Remove scenario %1").arg(scenarioRow.name)
                            compact: true
                            enabled: !root.locked && !root.preparationDraft.hasActiveScenarioEdit
                            objectName: "preparationScenarioRemove-" + scenarioRow.index
                            onClicked: root.desktopController.requestPreparationRemoveScenario(
                                           scenarioRow.index)
                            text: qsTr("Remove")
                        }
                    }

                    Label {
                        anchors.centerIn: parent
                        color: Theme.textMuted
                        font.family: Theme.sansFamily
                        font.pixelSize: 12
                        text: qsTr("No scenarios configured")
                        visible: scenarioList.count === 0
                    }
                }
            }

            Loader {
                id: activeScenarioLoader

                Layout.fillWidth: true
                active: root.preparationDraft.activeScenarioDraft !== null
                objectName: "preparationActiveScenarioEditor"
                sourceComponent: Component {
                    PreparationScenarioEditor {
                        attentionField: root.scenarioAttentionField
                        attentionRow: root.scenarioAttentionRow
                        attentionSerial: root.scenarioAttentionSerial
                        desktopController: root.desktopController
                        dialogsEnabled: root.dialogsEnabled
                        draft: root.preparationDraft.activeScenarioDraft
                        locked: root.locked
                        onCancelRequested: root.desktopController.requestPreparationCancelScenario()
                        onCommitRequested: root.desktopController.requestPreparationCommitScenario()
                    }
                }
            }

            ResponsiveCardGrid {
                Layout.fillWidth: true
                Layout.preferredHeight: implicitHeight
                maximumColumns: Math.min(2, root.expectedColumns)
                minimumCardWidth: 360
                objectName: "preparationOutputQualityGrid"
                uniformHeights: false
                visible: root.documentActive

                Card {
                    id: outputsCard

                    Layout.fillWidth: true
                    activeFocusOnTab: true
                    objectName: "preparationOutputsCard"
                    subtitle: qsTr(
                                  "Parquet is always emitted. Optional array requests remain visible when the current installation cannot execute them.")
                    title: qsTr("Outputs")

                    CheckBox {
                        Accessible.description: qsTr(
                                                    "Parquet is the authoritative Preparation output")
                        Accessible.name: qsTr("Emit Parquet Preparation table")
                        checked: true
                        enabled: false
                        objectName: "preparationParquetOutput"
                        text: qsTr("Parquet table")
                    }

                    CheckBox {
                        Accessible.name: qsTr("Emit array artifacts")
                        checked: root.preparationDraft.arrayOutputsEnabled
                        enabled: !root.locked
                        objectName: "preparationArrayOutputs"
                        onClicked: root.desktopController.requestPreparationBooleanField(
                                       "array_outputs", checked)
                        text: qsTr("Array artifacts")
                    }

                    Flow {
                        Layout.fillWidth: true
                        spacing: Theme.spacingSmall
                        visible: root.preparationDraft.arrayOutputsEnabled

                        Repeater {
                            model: root.preparationDraft.arrayFormatChoices

                            delegate: Item {
                                required property bool compatible
                                required property string display
                                required property string issue
                                required property bool selected
                                required property string value

                                implicitHeight: arrayFormatCheck.implicitHeight
                                implicitWidth: arrayFormatCheck.implicitWidth

                                CheckBox {
                                    id: arrayFormatCheck

                                    Accessible.description: parent.issue
                                    Accessible.name: qsTr("Emit %1 arrays").arg(parent.display)
                                    checked: parent.selected
                                    enabled: !root.locked && (parent.compatible || parent.selected)
                                    objectName: "preparationArrayFormat-" + parent.value
                                    onClicked:
                                    root.desktopController.requestPreparationArrayFormatSelection(
                                        parent.value, checked)
                                    text: parent.display

                                    ToolTip.text: parent.issue
                                    ToolTip.visible: hovered && parent.issue.length > 0
                                }
                            }
                        }
                    }

                    AppComboBox {
                        Accessible.name: qsTr("Array data type")
                        Layout.fillWidth: true
                        currentIndex: indexForRoleValue(root.preparationDraft.arrayDtype)
                        enabled: !root.locked && root.preparationDraft.arrayOutputsEnabled
                        model: ["float32", "float64"]
                        objectName: "preparationArrayDtype"
                        onActivated: root.desktopController.requestPreparationTextField(
                                         "array_dtype", String(currentValue))
                        visible: root.preparationDraft.arrayOutputsEnabled
                    }

                    CheckBox {
                        Accessible.name: qsTr("Include auxiliary fields in arrays")
                        checked: root.preparationDraft.includeAuxiliary
                        enabled: !root.locked && root.preparationDraft.arrayOutputsEnabled
                        objectName: "preparationArrayIncludeAuxiliary"
                        onClicked: root.desktopController.requestPreparationBooleanField(
                                       "include_auxiliary", checked)
                        text: qsTr("Include auxiliary fields in arrays")
                        visible: root.preparationDraft.arrayOutputsEnabled
                    }
                }

                Card {
                    Layout.fillWidth: true
                    activeFocusOnTab: true
                    objectName: "preparationQualityCard"
                    subtitle: qsTr(
                                  "Diagnostics do not alter prepared rows. Optional baseline dependencies are explicit.")
                    title: qsTr("Quality diagnostics")

                    CheckBox {
                        id: matrixCheck

                        Accessible.name: qsTr("Enable matrix diagnostics")
                        checked: root.preparationDraft.matrixDiagnosticsEnabled
                        enabled: !root.locked
                        objectName: "preparationMatrixDiagnostics"
                        onClicked: root.desktopController.requestPreparationBooleanField(
                                       "matrix_diagnostics", checked)
                        text: qsTr("Matrix diagnostics")
                    }

                    GridLayout {
                        Layout.fillWidth: true
                        columns: width >= 520 ? 2 : 1
                        objectName: "preparationMatrixSettingsGrid"
                        visible: root.preparationDraft.matrixDiagnosticsEnabled

                        TextField {
                            Accessible.name: qsTr("Correlation threshold")
                            Layout.fillWidth: true
                            enabled: !root.locked
                            objectName: "preparationCorrelationThreshold"
                            onEditingFinished: root.desktopController.requestPreparationTextField(
                                                   "correlation_threshold", text)
                            placeholderText: qsTr("Correlation threshold")
                            selectByMouse: true
                            text: root.preparationDraft.correlationThreshold
                        }

                        TextField {
                            Accessible.name: qsTr("Near-constant relative spread")
                            Layout.fillWidth: true
                            enabled: !root.locked
                            objectName: "preparationNearConstantSpread"
                            onEditingFinished: root.desktopController.requestPreparationTextField(
                                                   "near_constant_relative_spread", text)
                            placeholderText: qsTr("Near-constant spread")
                            selectByMouse: true
                            text: root.preparationDraft.nearConstantRelativeSpread
                        }
                    }

                    CheckBox {
                        id: baselineCheck

                        Accessible.description: root.preparationDraft.baselineDiagnosticsAvailable
                                                ? "" : root.preparationDraft.baselineDiagnosticsGuidance
                        Accessible.name: qsTr("Enable baseline diagnostics")
                        checked: root.preparationDraft.baselineDiagnosticsEnabled
                        enabled: !root.locked && (
                                     root.preparationDraft.baselineDiagnosticsAvailable
                                     || root.preparationDraft.baselineDiagnosticsEnabled)
                        objectName: "preparationBaselineDiagnostics"
                        onClicked: root.desktopController.requestPreparationBooleanField(
                                       "baseline_diagnostics", checked)
                        text: qsTr("Baseline diagnostics")
                    }

                    Label {
                        Accessible.name: text
                        Layout.fillWidth: true
                        color: Theme.warning
                        font.family: Theme.sansFamily
                        font.pixelSize: 11
                        objectName: "preparationBaselineDependencyGuidance"
                        text: root.preparationDraft.baselineDiagnosticsGuidance
                        visible: text.length > 0
                        wrapMode: Text.Wrap
                    }

                    Flow {
                        Layout.fillWidth: true
                        spacing: Theme.spacingSmall
                        visible: root.preparationDraft.baselineDiagnosticsEnabled

                        Repeater {
                            model: root.preparationDraft.baselineModelChoices

                            delegate: Item {
                                required property bool compatible
                                required property string display
                                required property string issue
                                required property bool selected
                                required property string value

                                implicitHeight: baselineModelCheck.implicitHeight
                                implicitWidth: baselineModelCheck.implicitWidth

                                CheckBox {
                                    id: baselineModelCheck

                                    Accessible.description: parent.issue
                                    Accessible.name: qsTr("Run %1 baseline").arg(parent.display)
                                    checked: parent.selected
                                    enabled: !root.locked && (parent.compatible || parent.selected)
                                    objectName: "preparationBaselineModel-" + parent.value
                                    onClicked:
                                    root.desktopController.requestPreparationBaselineModelSelection(
                                        parent.value, checked)
                                    text: parent.display

                                    ToolTip.text: parent.issue
                                    ToolTip.visible: hovered && parent.issue.length > 0
                                }
                            }
                        }
                    }

                    GridLayout {
                        Layout.fillWidth: true
                        columns: width >= 620 ? 3 : 1
                        objectName: "preparationBaselineSettingsGrid"
                        visible: root.preparationDraft.baselineDiagnosticsEnabled

                        TextField {
                            Accessible.name: qsTr("Baseline random seed")
                            Layout.fillWidth: true
                            enabled: !root.locked
                            objectName: "preparationBaselineSeed"
                            onEditingFinished: root.desktopController.requestPreparationTextField(
                                                   "baseline_random_seed", text)
                            placeholderText: qsTr("Random seed")
                            selectByMouse: true
                            text: root.preparationDraft.baselineRandomSeed
                        }

                        TextField {
                            Accessible.name: qsTr("Ridge alpha")
                            Layout.fillWidth: true
                            enabled: !root.locked
                            objectName: "preparationRidgeAlpha"
                            onEditingFinished: root.desktopController.requestPreparationTextField(
                                                   "ridge_alpha", text)
                            placeholderText: qsTr("Ridge alpha")
                            selectByMouse: true
                            text: root.preparationDraft.ridgeAlpha
                        }

                        TextField {
                            Accessible.name: qsTr("Histogram maximum iterations")
                            Layout.fillWidth: true
                            enabled: !root.locked
                            objectName: "preparationHistogramIterations"
                            onEditingFinished: root.desktopController.requestPreparationTextField(
                                                   "histogram_max_iterations", text)
                            placeholderText: qsTr("Maximum iterations")
                            selectByMouse: true
                            text: root.preparationDraft.histogramMaxIterations
                        }
                    }
                }
            }

            WorkflowRunPanel {
                Layout.fillWidth: true
                workflowController: root.workflowController
                workflowKind: "preparation"
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
        active: root.dialogsEnabled
        objectName: "preparationCategoryModeDialogLoader"
        sourceComponent: Component {
            DecisionDialog {
                id: categoryModeDialog

                acceptText: qsTr("Use observed categories")
                bodyText: qsTr(
                              "Using source-observed categories discards the temporary explicit category list for this field.")
                objectName: "preparationCategoryModeDialog"
                onAccepted: {
                    root.desktopController.requestPreparationCategoryMode(root.pendingCategoryField,
                                                                          root.pendingCategoryMode,
                                                                          true);
                    root.pendingCategoryField = "";
                    root.pendingCategoryMode = "";
                }
                onRejected: {
                    root.pendingCategoryField = "";
                    root.pendingCategoryMode = "";
                }
                title: qsTr("Replace explicit categories?")

                Connections {
                    function onCategoryModeDialogRequested() {
                        categoryModeDialog.open();
                    }

                    target: root
                }
            }
        }
    }
}
