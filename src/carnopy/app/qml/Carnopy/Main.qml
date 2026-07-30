pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts
import QtQuick.Window
import Carnopy

ApplicationWindow {
    id: root

    required property var desktopController
    required property var qmlSettings
    required property string startupWorkspace

    signal workspaceCancelRequested
    signal workspaceCommitRequested(bool confirmed)
    signal workspaceCreatePathRequested(string path)
    signal workspaceCreateRequested(string parentPath, string childName)
    signal workspaceInitializeRequested(string path)
    signal workspaceOpenRequested(string path)
    signal datasetDecisionCommitRequested(bool confirmed)
    signal datasetDecisionCancelRequested
    signal datasetFluidSelectionRequested(string value, bool selected)
    signal datasetFluidMoveRequested(int row, int offset)
    signal datasetFluidRemoveRequested(int row)
    signal configurationAttentionRequested(string section, string field, int row)
    signal datasetCloseRequested(bool discardConfirmed)
    signal datasetConfirmReformatRequested(string action)
    signal datasetImportRequested(string path, bool discardConfirmed)
    signal datasetModelChangeRequested(string model)
    signal datasetModeChangeRequested(string mode)
    signal datasetCoordinateChangeRequested(string axis)
    signal datasetNewRequested(string mode, bool discardConfirmed)
    signal datasetOutputSelectionRequested(string format, bool selected)
    signal datasetPropertySelectionRequested(string value, bool selected)
    signal datasetPropertyMoveRequested(int row, int offset)
    signal datasetPropertyRemoveRequested(int row)
    signal datasetSamplerKindChangeRequested(var draft, string kind)
    signal datasetSamplerTextChangeRequested(var draft, string field, string text)
    signal datasetSamplerUnitChangeRequested(var draft, string unit)
    signal datasetSaveAsRequested(bool allowReformat)
    signal datasetSavePathCancelled
    signal datasetSavePathSelected(string path)
    signal datasetSaveRequested(bool allowReformat)
    signal datasetValidateRequested
    signal datasetReloadRequested(bool discardConfirmed)
    signal runCancelRequested
    signal runForceStopRequested
    signal runGenerateRequested
    signal runInspectRunRequested
    signal runValidateRequested
    signal runViewPlotsRequested
    signal inspectionExploreRequested
    signal inspectionInspectRequested(string path)
    signal inspectionMoreSourcesRequested
    signal inspectionPreviewPageRequested(int pageOffset)
    signal inspectionRefreshRequested
    signal inspectionSourcesRefreshRequested
    signal inspectionTableRequested(string tableId)
    signal activityInspectRunRequested
    signal activityRecordSelectionRequested(string recordId)
    signal activityRecordsRefreshRequested
    signal activityRecordRemovalRequested
    signal activityRecoveryRefreshRequested
    signal activityRecoveryRemovalRequested
    signal activityRecoverySelectionRequested(int row, bool selected)
    signal activityViewPlotsRequested
    signal plotFieldChangeRequested(var draft, string field, string value)
    signal plotFluidSelectionRequested(var draft, string value, bool selected)
    signal visualizationAddPlotRequested
    signal visualizationCancelPlotRequested
    signal visualizationCommitPlotRequested
    signal visualizationEditPlotRequested(int row)
    signal visualizationEnabledRequested(bool enabled)
    signal visualizationFluidSelectionRequested(string value, bool selected)
    signal visualizationFormatRequested(string format)
    signal visualizationMappingAddRequested(var model)
    signal visualizationMappingFieldChangeRequested(var model, int row, string field)
    signal visualizationMappingRemoveRequested(var model, int row)
    signal visualizationMappingValueChangeRequested(var model, int row, string value)
    signal visualizationMovePlotRequested(int row, int offset)
    signal visualizationRemovePlotRequested(int row)
    signal configuredPlotGenerationRequested(string requestId)
    signal configuredPlotOutcomeRequested(int index)
    signal configuredPlotExportRequested(string path)
    signal configuredPlotExploreRunRequested
    signal configuredPlotOpenPdfRequested
    signal configuredPlotSessionEditRequested(int row)
    signal sessionPlotBeginEditRequested(string format)
    signal sessionPlotCancelEditRequested
    signal sessionPlotRenderRequested
    signal sessionPlotForceStopRequested
    signal sessionPlotExportRequested(string path)
    signal sessionPlotOpenPdfRequested
    signal normalGeometryRememberRequested(int x, int y, int width, int height)
    signal settingsLayoutResetRequested
    signal shutdownConfirmed(bool discardConfirmed)
    signal busyShutdownConfirmed(bool confirmed)
    signal transientEditShutdownConfirmed(bool discardConfirmed)

    readonly property bool runtimeReady: true
    readonly property string shellMode: width >= 1280 ? "wide" : (width >= 800 ? "compact" :
                                                                                 "narrow")

    readonly property bool railEffectiveCollapsed: shellMode !== "wide" || qmlSettings.railCollapsed
    readonly property bool inspectorWideVisible: shellMode === "wide" &&
                                                 !qmlSettings.inspectorCollapsed
    readonly property bool inspectorDrawerOpen: inspectorDrawer.visible
    readonly property bool navigationDrawerOpen: navigationDrawer.visible
    readonly property int railWidth: shellMode === "narrow" ? 0 : (railEffectiveCollapsed ? 76 :
                                                                                            224)

    readonly property int inspectorWidth: inspectorWideVisible ? 304 : 0
    readonly property int availableCentralWidth: Math.max(1, width - railWidth - inspectorWidth)
    readonly property int cardColumnCount: Math.max(1, Math.min(3, Math.floor((
                                                                                  availableCentralWidth
                                                                                  - 48 + 12)
                                                                              / 312)))
    readonly property bool controllerAvailable: desktopController !== null
    readonly property var configController: controllerAvailable
                                            ? desktopController.datasetConfigController : null
    readonly property var executionController: controllerAvailable
                                               ? desktopController.executionController : null
    readonly property var inspectionController: controllerAvailable
                                                ? desktopController.inspectionController : null
    readonly property var activityController: controllerAvailable
                                              ? desktopController.activityController : null
    readonly property var configuredPlotResultsController: controllerAvailable
                                                           ? desktopController.configuredPlotResultsController :
                                                             null
    readonly property var sessionPlotController: controllerAvailable
                                                 ? desktopController.sessionPlotController : null
    readonly property bool hasFake3dViewport: false
    readonly property string effectiveTheme: qmlSettings.effectiveTheme
    readonly property int motionDuration: Theme.durationStandard
    property string currentPage: "workspace"
    property bool geometryTrackingReady: false
    property var inspectorFocusReturnTarget: null
    property var navigationFocusReturnTarget: null
    property string operationFailureMessage: ""
    property string operationFailureOperation: ""
    property string operationFailureTitle: ""
    property var operationFailureIssues: []
    property string pendingAttentionField: ""
    property int pendingAttentionRow: -1
    property int pendingAttentionSerial: 0
    property string pendingReplacementAction: ""
    property string pendingReplacementMode: ""
    property string pendingReplacementPath: ""
    property string pendingReformatAction: ""
    property bool saveSelectionAccepted: false
    property string saveSelectionPath: ""

    function pageTitle(pageKey) {
        if (pageKey === "settings")
            return qsTr("Settings");
        if (pageKey === "help")
            return qsTr("Help");
        if (pageKey === "dataset")
            return qsTr("Dataset");
        if (pageKey === "visualization")
            return qsTr("Visualization");
        if (pageKey === "yaml")
            return qsTr("YAML Preview");
        if (pageKey === "run")
            return qsTr("Run");
        if (pageKey === "inspect")
            return qsTr("Inspect");
        if (pageKey === "activity")
            return qsTr("Activity");
        return qsTr("Workspace");
    }

    function clearOperationFailure() {
        operationFailureOperation = "";
        operationFailureTitle = "";
        operationFailureMessage = "";
        operationFailureIssues = [];
    }

    function localFileUrl(path) {
        let normalized = String(path).replace(/\\/g, "/");
        if (/^[A-Za-z]:\//.test(normalized))
            return "file:///" + encodeURI(normalized);
        return "file://" + encodeURI(normalized);
    }

    function completeSaveSelection() {
        if (!saveSelectionAccepted || saveConfigurationDialog.visible)
            return;
        const path = saveSelectionPath;
        saveSelectionAccepted = false;
        saveSelectionPath = "";
        Qt.callLater(() => root.datasetSavePathSelected(path));
    }

    function requestConfigurationClose() {
        if (controllerAvailable && desktopController.hasActivePlotEdit) {
            root.datasetCloseRequested(false);
            return;
        }
        if (configController !== null && configController.dirty) {
            pendingReplacementAction = "close";
            configurationDiscardDialog.open();
            return;
        }
        root.datasetCloseRequested(false);
    }

    function requestDatasetImport(path) {
        if (controllerAvailable && desktopController.hasActivePlotEdit) {
            root.datasetImportRequested(path, false);
            return;
        }
        if (configController !== null && configController.dirty) {
            pendingReplacementAction = "import";
            pendingReplacementPath = path;
            configurationDiscardDialog.open();
            return;
        }
        root.datasetImportRequested(path, false);
    }

    function requestDatasetNew(mode) {
        if (controllerAvailable && desktopController.hasActivePlotEdit) {
            root.datasetNewRequested(mode, false);
            return;
        }
        if (configController !== null && configController.dirty) {
            pendingReplacementAction = "new";
            pendingReplacementMode = mode;
            configurationDiscardDialog.open();
            return;
        }
        root.datasetNewRequested(mode, false);
    }

    function requestCommandImport() {
        routeTo("workspace");
        Qt.callLater(function () {
            if (workspacePageLoader.item !== null && workspacePageLoader.item.openImportDialog
                    !== undefined)
                workspacePageLoader.item.openImportDialog();
        });
    }

    function routeTo(pageKey) {
        currentPage = pageKey;
        if (navigationDrawer.visible)
            navigationDrawer.close();
    }

    function focusControlSoon(preferred, fallback) {
        Qt.callLater(() => {
            let target = preferred;
            if (target === null || !target.visible || !target.enabled)
                target = fallback;
            if (target !== null && target.visible && target.enabled)
                target.forceActiveFocus(Qt.OtherFocusReason);
        });
    }

    function restoreNavigationFocus() {
        const preferred = navigationFocusReturnTarget;
        navigationFocusReturnTarget = null;
        if (shellMode === "narrow") {
            focusControlSoon(preferred, commandBar.railMenuControl);
            return;
        }
        persistentRail.restoreCurrentPageFocus();
    }

    function restoreInspectorFocus() {
        const preferred = inspectorFocusReturnTarget;
        inspectorFocusReturnTarget = null;
        Qt.callLater(() => {
            let target = root.shellMode === "wide" ? (root.inspectorWideVisible
                                                      ? persistentInspector.closeControl :
                                                        commandBar.inspectorToggleControl) :
                                                     preferred;
            if (target === null || !target.visible || !target.enabled)
                target = commandBar.inspectorToggleControl;
            if (target !== null && target.visible && target.enabled)
                target.forceActiveFocus(Qt.OtherFocusReason);
        });
    }

    function requestRailToggle(opener) {
        if (shellMode === "compact")
            return;
        if (!navigationDrawer.visible && opener !== null)
            navigationFocusReturnTarget = opener;
        railToggleAction.trigger();
    }

    function requestInspectorToggle(opener) {
        if (shellMode === "wide" || !inspectorDrawer.visible) {
            if (opener !== null)
                inspectorFocusReturnTarget = opener;
        }
        inspectorToggleAction.trigger();
    }

    function applyRailToggle() {
        if (shellMode === "wide") {
            qmlSettings.toggleRailCollapsed();
            focusControlSoon(persistentRail.collapseControl, persistentRail.collapseControl);
        } else if (shellMode === "narrow") {
            if (navigationDrawer.visible)
                navigationDrawer.close();
            else
                navigationDrawer.open();
        }
    }

    function applyInspectorToggle() {
        if (shellMode === "wide") {
            qmlSettings.toggleInspectorCollapsed();
            restoreInspectorFocus();
        } else if (inspectorDrawer.visible) {
            inspectorDrawer.close();
        } else {
            inspectorDrawer.open();
        }
    }

    function rememberGeometrySoon() {
        if (geometryTrackingReady && visibility === Window.Windowed)
            geometryTimer.restart();
    }

    function restoreWindowState() {
        const geometry = qmlSettings.normalGeometry;
        x = geometry.x;
        y = geometry.y;
        width = Math.max(minimumWidth, geometry.width);
        height = Math.max(minimumHeight, geometry.height);
    }

    color: Theme.canvas
    height: 900
    minimumHeight: 600
    minimumWidth: 680
    objectName: "carnopyQmlRoot"
    palette.alternateBase: Theme.surfaceMuted
    palette.base: Theme.surface
    palette.button: Theme.surfaceRaised
    palette.buttonText: Theme.text
    palette.highlight: Theme.primary
    palette.highlightedText: Theme.highlightedText
    palette.placeholderText: Theme.textSubtle
    palette.text: Theme.text
    palette.window: Theme.canvas
    palette.windowText: Theme.text
    title: qsTr("Carnopy")
    visibility: Window.Hidden
    width: 1440

    Binding {
        property: "mode"
        target: Theme
        value: root.qmlSettings.effectiveTheme
    }

    Binding {
        property: "reducedMotion"
        target: Theme
        value: root.qmlSettings.reducedMotion
    }

    Timer {
        id: geometryTimer

        interval: 240
        onTriggered: root.normalGeometryRememberRequested(root.x, root.y, root.width, root.height)
    }

    Connections {
        function onLayoutReset() {
            const geometry = root.qmlSettings.normalGeometry;
            root.visibility = Window.Windowed;
            root.x = geometry.x;
            root.y = geometry.y;
            root.width = Math.max(root.minimumWidth, geometry.width);
            root.height = Math.max(root.minimumHeight, geometry.height);
        }

        ignoreUnknownSignals: true
        target: root.qmlSettings
    }

    onHeightChanged: rememberGeometrySoon()
    onWidthChanged: rememberGeometrySoon()
    onXChanged: rememberGeometrySoon()
    onYChanged: rememberGeometrySoon()

    Component.onCompleted: restoreWindowState()

    onShellModeChanged: {
        navigationFocusReturnTarget = null;
        inspectorFocusReturnTarget = null;
        if (navigationDrawer.visible)
        navigationDrawer.close();
        if (inspectorDrawer.visible)
        inspectorDrawer.close();
    }

    Action {
        id: railToggleAction

        enabled: root.shellMode !== "compact"
        objectName: "railToggleAction"
        shortcut: "Ctrl+B"
        onTriggered: root.applyRailToggle()
    }

    Action {
        id: inspectorToggleAction

        objectName: "inspectorToggleAction"
        shortcut: "Ctrl+I"
        onTriggered: root.applyInspectorToggle()
    }

    RowLayout {
        anchors.fill: parent
        spacing: 0

        NavRail {
            id: persistentRail

            Layout.fillHeight: true
            Layout.preferredWidth: implicitWidth
            allowCollapse: root.shellMode === "wide"
            collapsed: root.railEffectiveCollapsed
            currentPage: root.currentPage
            activityAvailable: root.controllerAvailable && root.desktopController.workspaceAvailable
            datasetAvailable: root.controllerAvailable && root.desktopController.workspaceAvailable
            inspectAvailable: root.controllerAvailable && root.desktopController.workspaceAvailable
            runAvailable: root.controllerAvailable && root.desktopController.workspaceAvailable
            visualizationAvailable: root.controllerAvailable
                                    && root.desktopController.workspaceAvailable
            yamlAvailable: root.configController !== null && root.configController.hasDocument
            objectName: "persistentNavigationRail"
            onCollapseRequested: root.requestRailToggle(persistentRail.collapseControl)
            onPageRequested: pageKey => root.routeTo(pageKey)
            visible: root.shellMode !== "narrow"
        }

        Rectangle {
            Layout.fillHeight: true
            Layout.fillWidth: true
            color: Theme.canvas

            ColumnLayout {
                anchors.fill: parent
                spacing: 0

                CommandBar {
                    id: commandBar

                    Layout.fillWidth: true
                    appearanceExpanded: root.shellMode !== "narrow"
                    breadcrumb: {
                        if (!root.controllerAvailable || !root.desktopController.workspaceAvailable)
                        return qsTr("Local workbench");
                        if (root.configController !== null && root.configController.hasDocument)
                        return root.desktopController.workspaceRootPath + "  ›  "
                        + root.configController.fileDisplay;
                        return root.desktopController.workspaceRootPath;
                    }
                    canImport: root.configController !== null && root.configController.canImport
                    canNew: root.configController !== null && root.configController.canCreate
                    canSave: root.configController !== null && root.configController.canSave
                    canSaveAs: root.configController !== null && root.configController.canSaveAs
                    documentDirty: root.configController !== null && root.configController.dirty
                    documentOpen: root.configController !== null
                                  && root.configController.hasDocument
                    effectiveTheme: root.qmlSettings.effectiveTheme
                    inspectorOpen: root.inspectorWideVisible || inspectorDrawer.visible
                    objectName: "documentCommandBar"
                    onAppearanceModeRequested: mode => root.qmlSettings.themeMode = mode
                    onCloseConfigurationRequested: root.requestConfigurationClose()
                    onImportRequested: root.requestCommandImport()
                    onInspectorToggleRequested: root.requestInspectorToggle(
                                                    commandBar.inspectorToggleControl)
                    onNewRequested: root.routeTo("workspace")
                    onRailMenuRequested: root.requestRailToggle(commandBar.railMenuControl)
                    onSaveAsRequested: root.datasetSaveAsRequested(false)
                    onSaveRequested: root.datasetSaveRequested(false)
                    pageTitle: root.pageTitle(root.currentPage)
                    shellMode: root.shellMode
                    showInspectorButton: !(root.inspectorWideVisible || inspectorDrawer.visible)
                    showAppearanceSelector: !root.inspectorWideVisible
                    showRailMenu: root.shellMode === "narrow"
                    statusLabel: {
                        if (root.currentPage === "run" && root.executionController !== null)
                        return root.executionController.state === "running" ? qsTr("Running") : (
                                                                                  root.executionController.state
                                                                                  === "succeeded"
                                                                                  ? qsTr("Run complete") :
                                                                                    root.executionController.snapshotAvailable
                                                                                    ? qsTr("Ready to run") :
                                                                                      qsTr("Saved configuration required"));
                        if (root.controllerAvailable && root.desktopController.workspaceState
                            === "loading")
                        return qsTr("Loading");
                        if (root.controllerAvailable && root.desktopController.workspaceState
                            === "editing")
                        return root.desktopController.datasetDraft.locallyValid ? qsTr(
                                                                                      "Dataset complete") :
                                                                                  qsTr("Needs attention");
                        if (root.controllerAvailable && root.desktopController.workspaceAvailable)
                        return qsTr("Workspace ready");
                        return qsTr("No workspace");
                    }
                    statusTone: root.controllerAvailable && root.desktopController.workspaceState
                                === "loading" ? "information" : (root.currentPage === "run"
                                                                 && root.executionController
                                                                 !== null ? (
                                                                                root.executionController.state
                                                                                === "succeeded"
                                                                                ? "success" : (
                                                                                      root.executionController.state
                                                                                      === "invalid"
                                                                                      || root.executionController.state
                                                                                      === "failed"
                                                                                      ? "danger" : (
                                                                                            root.executionController.state
                                                                                            === "running"
                                                                                            || root.executionController.state
                                                                                            === "starting"
                                                                                            ? "information" :
                                                                                              "neutral"))) :
                                                                            (root.controllerAvailable
                                                                             && root.desktopController.workspaceState
                                                                             === "editing" &&
                                                                             !root.desktopController.datasetDraft.locallyValid
                                                                             ? "danger" : (
                                                                                   root.controllerAvailable
                                                                                   && root.desktopController.workspaceAvailable
                                                                                   ? "success" :
                                                                                     "neutral")))
                    themeMode: root.qmlSettings.themeMode
                }

                Rectangle {
                    id: capabilityLoadingBanner

                    Layout.fillWidth: true
                    Layout.preferredHeight: capabilityLoadingContent.implicitHeight + 18
                    Accessible.name: capabilityLoadingTitle.text + ". "
                                     + capabilityLoadingDetail.text
                    border.color: Theme.information
                    border.width: 1
                    color: Theme.informationSoft
                    objectName: "capabilityLoadingBanner"
                    visible: root.controllerAvailable && root.desktopController.workspaceState
                             === "loading"

                    RowLayout {
                        id: capabilityLoadingContent

                        anchors.fill: parent
                        anchors.leftMargin: 14
                        anchors.rightMargin: 14
                        spacing: Theme.spacingMedium

                        BusyIndicator {
                            Layout.alignment: Qt.AlignVCenter
                            Layout.preferredHeight: 24
                            Layout.preferredWidth: 24
                            objectName: "capabilityLoadingIndicator"
                            running: capabilityLoadingBanner.visible
                        }

                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 1

                            Label {
                                id: capabilityLoadingTitle

                                Layout.fillWidth: true
                                color: Theme.text
                                font.family: Theme.sansFamily
                                font.pixelSize: 12
                                font.weight: Font.DemiBold
                                objectName: "capabilityLoadingTitle"
                                text: qsTr("Preparing local CoolProp capabilities")
                            }

                            Label {
                                id: capabilityLoadingDetail

                                Layout.fillWidth: true
                                color: Theme.textMuted
                                font.family: Theme.sansFamily
                                font.pixelSize: 11
                                objectName: "capabilityLoadingDetail"
                                text: qsTr(
                                          "Importing the installed CoolProp package, enumerating local fluids and aliases, and constructing model, property, and visualization choices. No network service is contacted.")
                                wrapMode: Text.Wrap
                            }
                        }
                    }
                }

                OperationFeedback {
                    Layout.fillWidth: true
                    issues: root.operationFailureIssues
                    message: root.operationFailureMessage
                    objectName: "operationFeedback"
                    onDismissed: root.clearOperationFailure()
                    operation: root.operationFailureOperation
                    title: root.operationFailureTitle
                }

                Item {
                    Layout.fillHeight: true
                    Layout.fillWidth: true
                    objectName: "workbenchPageHost"

                    Loader {
                        id: workspacePageLoader

                        active: root.currentPage === "workspace" || item !== null
                        anchors.fill: parent
                        objectName: "workspacePageLoader"
                        sourceComponent: workspacePage
                        visible: root.currentPage === "workspace"
                    }

                    Loader {
                        id: datasetPageLoader

                        active: root.currentPage === "dataset" || item !== null
                        anchors.fill: parent
                        objectName: "datasetPageLoader"
                        sourceComponent: datasetPage
                        visible: root.currentPage === "dataset"
                    }

                    Loader {
                        id: yamlPageLoader

                        active: root.currentPage === "yaml" || item !== null
                        anchors.fill: parent
                        objectName: "yamlPageLoader"
                        sourceComponent: yamlPage
                        visible: root.currentPage === "yaml"
                    }

                    Loader {
                        id: visualizationPageLoader

                        active: root.currentPage === "visualization" || item !== null
                        anchors.fill: parent
                        objectName: "visualizationPageLoader"
                        sourceComponent: visualizationPage
                        visible: root.currentPage === "visualization"
                    }

                    Loader {
                        id: runPageLoader

                        active: root.currentPage === "run" || item !== null
                        anchors.fill: parent
                        objectName: "runPageLoader"
                        sourceComponent: runPage
                        visible: root.currentPage === "run"
                    }

                    Loader {
                        id: inspectPageLoader

                        active: root.currentPage === "inspect" || item !== null
                        anchors.fill: parent
                        objectName: "inspectPageLoader"
                        sourceComponent: inspectPage
                        visible: root.currentPage === "inspect"
                    }

                    Loader {
                        id: activityPageLoader

                        active: root.currentPage === "activity" || item !== null
                        anchors.fill: parent
                        objectName: "activityPageLoader"
                        sourceComponent: activityPage
                        visible: root.currentPage === "activity"
                    }

                    Loader {
                        id: settingsPageLoader

                        active: root.currentPage === "settings" || item !== null
                        anchors.fill: parent
                        objectName: "settingsPageLoader"
                        sourceComponent: settingsPage
                        visible: root.currentPage === "settings"
                    }

                    Loader {
                        id: helpPageLoader

                        active: root.currentPage === "help" || item !== null
                        anchors.fill: parent
                        objectName: "helpPageLoader"
                        sourceComponent: helpPage
                        visible: root.currentPage === "help"
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 28
                    border.color: Theme.border
                    border.width: 1
                    color: Theme.surface

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 14
                        anchors.rightMargin: 14
                        spacing: Theme.spacingSmall

                        Rectangle {
                            Layout.preferredHeight: 7
                            Layout.preferredWidth: 7
                            color: Theme.success
                            radius: 4
                        }

                        Label {
                            Layout.fillWidth: true
                            color: Theme.textMuted
                            font.family: Theme.sansFamily
                            font.pixelSize: 10
                            text: qsTr(
                                      "Ready · local QML shell · worker scientific boundary preserved")
                        }

                        Label {
                            color: Theme.textSubtle
                            font.family: Theme.monoFamily
                            font.pixelSize: 10
                            text: root.shellMode
                        }
                    }
                }
            }
        }

        ColumnLayout {
            Layout.fillHeight: true
            Layout.maximumWidth: root.inspectorWidth
            Layout.minimumWidth: root.inspectorWidth
            Layout.preferredWidth: root.inspectorWidth
            spacing: 0
            visible: root.inspectorWideVisible

            AppearanceSelector {
                Layout.fillWidth: true
                effectiveTheme: root.qmlSettings.effectiveTheme
                expanded: true
                objectName: "dockedAppearanceSelector"
                onModeRequested: mode => root.qmlSettings.themeMode = mode
                showBoundary: true
                themeMode: root.qmlSettings.themeMode
            }

            ContextInspector {
                id: persistentInspector

                activityController: root.activityController
                blockingField: root.configController !== null ? root.configController.blockingField :
                                                                ""
                blockingIssue: root.configController !== null ? root.configController.blockingIssue :
                                                                ""
                blockingRow: root.configController !== null ? root.configController.blockingRow : -1
                blockingSection: root.configController !== null
                                 ? root.configController.blockingSection : "none"
                Layout.fillHeight: true
                Layout.fillWidth: true
                closeButtonVisible: true
                configurationDirty: root.configController !== null && root.configController.dirty
                configurationFile: root.configController !== null
                                   ? root.configController.fileDisplay : ""
                configurationOpen: root.configController !== null
                                   && root.configController.hasDocument
                canValidate: root.configController !== null && root.configController.canValidate
                datasetIssue: root.controllerAvailable ? root.desktopController.datasetDraft.issue :
                                                         ""
                datasetValid: root.controllerAvailable
                              && root.desktopController.datasetDraft.locallyValid
                executionController: root.executionController
                inspectionController: root.inspectionController
                objectName: "persistentContextInspector"
                onAttentionRequested: (section, field, row) => root.configurationAttentionRequested(
                                                                   section, field, row)
                onCloseRequested: root.requestInspectorToggle(persistentInspector.closeControl)
                onInspectionExploreRequested: root.inspectionExploreRequested()
                onValidateRequested: root.datasetValidateRequested()
                pageKey: root.currentPage
                workspacePath: root.controllerAvailable ? root.desktopController.workspaceRootPath :
                                                          ""
                workspaceState: root.controllerAvailable ? root.desktopController.workspaceState :
                                                           "unavailable"
                visualizationActiveEdit: root.controllerAvailable
                                         && root.desktopController.hasActivePlotEdit
                visualizationIssue: root.controllerAvailable
                                    ? root.desktopController.visualizationDraft.issue : ""
                visualizationValid: root.controllerAvailable
                                    && root.desktopController.visualizationDraft.locallyValid
                workerValidationIssue: root.configController !== null
                                       ? root.configController.workerValidationIssue : ""
                workerValidationIssues: root.configController !== null
                                        ? root.configController.workerValidationIssues : []
                workerValidationState: root.configController !== null
                                       ? root.configController.workerValidationState : "unavailable"
                yamlAvailable: root.configController !== null && root.configController.yamlAvailable
            }
        }
    }

    Drawer {
        id: navigationDrawer

        edge: Qt.LeftEdge
        height: root.height
        modal: true
        objectName: "navigationDrawer"
        onClosed: root.restoreNavigationFocus()
        width: Math.min(300, root.width * 0.88)

        contentItem: NavRail {
            allowCollapse: false
            collapsed: false
            currentPage: root.currentPage
            activityAvailable: root.controllerAvailable && root.desktopController.workspaceAvailable
            datasetAvailable: root.controllerAvailable && root.desktopController.workspaceAvailable
            inspectAvailable: root.controllerAvailable && root.desktopController.workspaceAvailable
            runAvailable: root.controllerAvailable && root.desktopController.workspaceAvailable
            visualizationAvailable: root.controllerAvailable
                                    && root.desktopController.workspaceAvailable
            yamlAvailable: root.configController !== null && root.configController.hasDocument
            onPageRequested: pageKey => root.routeTo(pageKey)
        }
    }

    Drawer {
        id: inspectorDrawer

        edge: Qt.RightEdge
        height: root.height
        modal: root.shellMode === "narrow"
        objectName: "inspectorDrawer"
        onClosed: root.restoreInspectorFocus()
        width: Math.min(328, root.width * 0.9)

        contentItem: ContextInspector {
            activityController: root.activityController
            blockingField: root.configController !== null ? root.configController.blockingField : ""
            blockingIssue: root.configController !== null ? root.configController.blockingIssue : ""
            blockingRow: root.configController !== null ? root.configController.blockingRow : -1
            blockingSection: root.configController !== null ? root.configController.blockingSection :
                                                              "none"
            closeButtonVisible: true
            configurationDirty: root.configController !== null && root.configController.dirty
            configurationFile: root.configController !== null ? root.configController.fileDisplay :
                                                                ""
            configurationOpen: root.configController !== null && root.configController.hasDocument
            canValidate: root.configController !== null && root.configController.canValidate
            datasetIssue: root.controllerAvailable ? root.desktopController.datasetDraft.issue : ""
            datasetValid: root.controllerAvailable
                          && root.desktopController.datasetDraft.locallyValid
            executionController: root.executionController
            inspectionController: root.inspectionController
            objectName: "drawerContextInspector"
            onAttentionRequested: (section, field, row) => root.configurationAttentionRequested(
                                                               section, field, row)
            onCloseRequested: root.requestInspectorToggle(null)
            onInspectionExploreRequested: root.inspectionExploreRequested()
            onValidateRequested: root.datasetValidateRequested()
            pageKey: root.currentPage
            workspacePath: root.controllerAvailable ? root.desktopController.workspaceRootPath : ""
            workspaceState: root.controllerAvailable ? root.desktopController.workspaceState :
                                                       "unavailable"
            visualizationActiveEdit: root.controllerAvailable
                                     && root.desktopController.hasActivePlotEdit
            visualizationIssue: root.controllerAvailable
                                ? root.desktopController.visualizationDraft.issue : ""
            visualizationValid: root.controllerAvailable
                                && root.desktopController.visualizationDraft.locallyValid
            workerValidationIssue: root.configController !== null
                                   ? root.configController.workerValidationIssue : ""
            workerValidationIssues: root.configController !== null
                                    ? root.configController.workerValidationIssues : []
            workerValidationState: root.configController !== null
                                   ? root.configController.workerValidationState : "unavailable"
            yamlAvailable: root.configController !== null && root.configController.yamlAvailable
        }
    }

    Component {
        id: workspacePage

        WorkspacePage {
            desktopController: root.desktopController
            expectedColumns: root.cardColumnCount
            importFolder: root.controllerAvailable && root.desktopController.workspaceAvailable
                          ? root.localFileUrl(
                                root.desktopController.workspaceController.configsPath) : ""
            objectName: "workspacePage"
            onCancelWorkspaceRequested: root.workspaceCancelRequested()
            onCommitWorkspaceRequested: confirmed => root.workspaceCommitRequested(confirmed)
            onCreateWorkspacePathRequested: path => root.workspaceCreatePathRequested(path)
            onCreateWorkspaceRequested: (parentPath, childName) => root.workspaceCreateRequested(
                                                                       parentPath, childName)
            onInitializeWorkspaceRequested: path => root.workspaceInitializeRequested(path)
            onOpenWorkspaceRequested: path => root.workspaceOpenRequested(path)
            onImportDatasetRequested: path => root.requestDatasetImport(path)
            onNewDatasetRequested: mode => root.requestDatasetNew(mode)
        }
    }

    Component {
        id: datasetPage

        DatasetPage {
            attentionField: root.pendingAttentionField
            attentionRow: root.pendingAttentionRow
            attentionSerial: root.pendingAttentionSerial
            configController: root.configController
            datasetDraft: root.desktopController.datasetDraft
            desktopController: root.desktopController
            expectedColumns: root.cardColumnCount
            objectName: "datasetPage"
            onCoordinateChangeRequested: axis => root.datasetCoordinateChangeRequested(axis)
            onFluidSelectionRequested: (value, selected) => root.datasetFluidSelectionRequested(
                                                                value, selected)
            onFluidMoveRequested: (row, offset) => root.datasetFluidMoveRequested(row, offset)
            onFluidRemoveRequested: row => root.datasetFluidRemoveRequested(row)
            onModelChangeRequested: model => root.datasetModelChangeRequested(model)
            onModeChangeRequested: mode => root.datasetModeChangeRequested(mode)
            onOutputSelectionRequested: (format, selected) => root.datasetOutputSelectionRequested(
                                                                  format, selected)
            onPropertySelectionRequested: (value, selected)
                                          => root.datasetPropertySelectionRequested(value, selected)
            onPropertyMoveRequested: (row, offset) => root.datasetPropertyMoveRequested(row, offset)
            onPropertyRemoveRequested: row => root.datasetPropertyRemoveRequested(row)
            onSamplerKindChangeRequested: (draft, kind) => root.datasetSamplerKindChangeRequested(
                                                               draft, kind)
            onSamplerTextChangeRequested: (draft, field, text)
                                          => root.datasetSamplerTextChangeRequested(draft, field,
                                                                                    text)
            onSamplerUnitChangeRequested: (draft, unit) => root.datasetSamplerUnitChangeRequested(
                                                               draft, unit)
        }
    }

    Component {
        id: yamlPage

        YamlPreviewPage {
            configController: root.desktopController.datasetConfigController
            objectName: "yamlPreviewPage"
            onAttentionRequested: (section, field, row) => root.configurationAttentionRequested(
                                                               section, field, row)
            onCopyCompleted: toastHost.showMessage(qsTr("YAML copied to the clipboard."), "success")
        }
    }

    Component {
        id: visualizationPage

        VisualizationPage {
            attentionField: root.pendingAttentionField
            attentionRow: root.pendingAttentionRow
            attentionSerial: root.pendingAttentionSerial
            expectedColumns: root.cardColumnCount
            configuredResultsController: root.configuredPlotResultsController
            objectName: "visualizationPage"
            sessionPlotController: root.sessionPlotController
            visualizationDraft: root.desktopController.visualizationDraft
            onAddPlotRequested: root.visualizationAddPlotRequested()
            onCancelPlotRequested: root.visualizationCancelPlotRequested()
            onCommitPlotRequested: root.visualizationCommitPlotRequested()
            onEditPlotRequested: row => root.visualizationEditPlotRequested(row)
            onEnabledChangeRequested: enabled => root.visualizationEnabledRequested(enabled)
            onFluidSelectionRequested: (value, selected)
                                       => root.visualizationFluidSelectionRequested(value, selected)
            onFormatChangeRequested: format => root.visualizationFormatRequested(format)
            onMappingAddRequested: model => root.visualizationMappingAddRequested(model)
            onMappingFieldChangeRequested: (model, row, field)
                                           => root.visualizationMappingFieldChangeRequested(model,
                                                                                            row, field)
            onMappingRemoveRequested: (model, row) => root.visualizationMappingRemoveRequested(model,
                                                                                               row)
            onMappingValueChangeRequested: (model, row, value)
                                           => root.visualizationMappingValueChangeRequested(model,
                                                                                            row, value)
            onMovePlotRequested: (row, offset) => root.visualizationMovePlotRequested(row, offset)
            onPlotFieldChangeRequested: (draft, field, value) => root.plotFieldChangeRequested(draft,
                                                                                               field, value)
            onPlotFluidSelectionRequested: (draft, value, selected)
                                           => root.plotFluidSelectionRequested(draft, value,
                                                                               selected)
            onRemovePlotRequested: row => root.visualizationRemovePlotRequested(row)
            onConfiguredGenerationRequested: requestId => root.configuredPlotGenerationRequested(
                                                              requestId)
            onConfiguredOutcomeRequested: index => root.configuredPlotOutcomeRequested(index)
            onConfiguredExportRequested: path => root.configuredPlotExportRequested(path)
            onConfiguredExploreRunRequested: root.configuredPlotExploreRunRequested()
            onConfiguredOpenPdfRequested: root.configuredPlotOpenPdfRequested()
            onConfiguredSessionEditRequested: row => root.configuredPlotSessionEditRequested(row)
            onSessionBeginEditRequested: format => root.sessionPlotBeginEditRequested(format)
            onSessionCancelEditRequested: root.sessionPlotCancelEditRequested()
            onSessionRenderRequested: root.sessionPlotRenderRequested()
            onSessionForceStopRequested: root.sessionPlotForceStopRequested()
            onSessionExportRequested: path => root.sessionPlotExportRequested(path)
            onSessionOpenPdfRequested: root.sessionPlotOpenPdfRequested()
            onPlotExportCompleted: (imagePath, sidecarPath) => toastHost.showMessage(qsTr(
                                                                                         "Exported %1 and its provenance sidecar.").arg(
                                                                                         imagePath),
                                                                                     "success")
        }
    }

    Component {
        id: runPage

        RunPage {
            configuredPlotsAvailable: executionController !== null && executionController.operation
                                      === "generate" && executionController.state === "succeeded"
                                      && executionController.resultRequestId.length > 0
            executionController: root.executionController
            expectedColumns: root.shellMode === "narrow" ? 1 : root.cardColumnCount
            inspectRunAvailable: configuredPlotsAvailable
                                 && executionController.resultOutputDirectory.length > 0
            objectName: "runPage"
            onCancelRequested: root.runCancelRequested()
            onForceStopRequested: root.runForceStopRequested()
            onGenerateRequested: root.runGenerateRequested()
            onInspectRunRequested: root.runInspectRunRequested()
            onValidateRequested: root.runValidateRequested()
            onViewPlotsRequested: root.runViewPlotsRequested()
        }
    }

    Component {
        id: inspectPage

        InspectPage {
            inspectionController: root.inspectionController
            objectName: "inspectPage"
            onInspectSourceRequested: path => root.inspectionInspectRequested(path)
            onMoreSourcesRequested: root.inspectionMoreSourcesRequested()
            onPreviewPageRequested: pageOffset => root.inspectionPreviewPageRequested(pageOffset)
            onRefreshRequested: root.inspectionRefreshRequested()
            onRefreshSourcesRequested: root.inspectionSourcesRefreshRequested()
            onSelectTableRequested: tableId => root.inspectionTableRequested(tableId)
        }
    }

    Component {
        id: activityPage

        ActivityPage {
            activityController: root.activityController
            objectName: "activityPage"
            onInspectRunRequested: root.activityInspectRunRequested()
            onRecordSelectionRequested: recordId => root.activityRecordSelectionRequested(recordId)
            onRecordsRefreshRequested: root.activityRecordsRefreshRequested()
            onRecoveryRefreshRequested: root.activityRecoveryRefreshRequested()
            onRecoverySelectionRequested: (row, selected) => root.activityRecoverySelectionRequested(
                                                                 row, selected)
            onRemoveRecordRequested: root.activityRecordRemovalRequested()
            onRemoveRecoveryRequested: root.activityRecoveryRemovalRequested()
            onViewPlotsRequested: root.activityViewPlotsRequested()
        }
    }

    Component {
        id: settingsPage

        SettingsPage {
            objectName: "settingsPage"
            onLayoutResetRequested: root.settingsLayoutResetRequested()
            qmlSettings: root.qmlSettings
        }
    }

    Component {
        id: helpPage

        HelpPage {
            objectName: "helpPage"
        }
    }

    ToastHost {
        id: toastHost

        objectName: "toastHost"
    }

    Connections {
        function onActivityActionFailed(title, message) {
            toastHost.showMessage(title + ": " + message, "danger");
        }

        function onBusyShutdownConfirmationRequested(mode, message) {
            busyShutdownDialog.busyMode = mode;
            busyShutdownDialog.bodyText = message;
            busyShutdownDialog.acceptText = mode === "cancel_generation" ? qsTr("Cancel and close") :
                                                                           qsTr("Force stop and close");
            busyShutdownDialog.open();
        }

        function onAttentionRequested(section, field, row) {
            if (section !== "dataset" && section !== "visualization")
                return;
            root.routeTo(section);
            root.pendingAttentionField = field;
            root.pendingAttentionRow = row;
            root.pendingAttentionSerial += 1;
        }

        function onCloseWindowRequested() {
            root.close();
        }

        function onDatasetDecisionRequested() {
            datasetDecisionDialog.open();
        }

        function onDatasetDocumentOpened() {
            root.routeTo("dataset");
        }

        function onNavigationRequested(pageKey, detail) {
            root.routeTo(pageKey);
            if (pageKey === "visualization" && detail === "configured")
                Qt.callLater(function () {
                    if (visualizationPageLoader.item !== null)
                        visualizationPageLoader.item.showConfiguredPlots();
                });
            else if (pageKey === "visualization" && detail === "explore")
                Qt.callLater(function () {
                    if (visualizationPageLoader.item !== null)
                        visualizationPageLoader.item.showExploreInspectedData();
                });
        }

        function onShutdownConfirmationRequested() {
            shutdownDiscardDialog.open();
        }

        function onTransientEditShutdownConfirmationRequested(message) {
            transientEditShutdownDialog.bodyText = message;
            transientEditShutdownDialog.open();
        }

        function onWorkspaceStateChanged() {
            const workspaceAvailable = root.desktopController.workspaceAvailable;
            if ((root.currentPage === "dataset" || root.currentPage === "run" || root.currentPage
                 === "inspect" || root.currentPage === "visualization" || root.currentPage
                 === "activity") && !workspaceAvailable)
                root.routeTo("workspace");
            if (root.currentPage === "yaml" && (root.configController === null ||
                                                !root.configController.hasDocument))
                root.routeTo(workspaceAvailable ? "dataset" : "workspace");
        }

        target: root.controllerAvailable ? root.desktopController : null
    }

    Connections {
        function onExternalChangeRequested() {
            externalChangeDialog.open();
        }

        function onImportSucceeded(path, importedExternally) {
            root.clearOperationFailure();
            const detail = importedExternally ? qsTr("Imported external configuration: ") : qsTr(
                                                    "Opened workspace configuration: ");
            toastHost.showMessage(detail + path, "success");
        }

        function onOperationFailed(operation, title, message, issues) {
            root.operationFailureOperation = operation;
            root.operationFailureTitle = title;
            root.operationFailureMessage = message;
            root.operationFailureIssues = issues;
        }

        function onReformatConfirmationRequested(action) {
            root.pendingReformatAction = action;
            reformatConfirmationDialog.open();
        }

        function onSavePathRequested(defaultPath) {
            saveConfigurationDialog.selectedFile = root.localFileUrl(defaultPath);
            saveConfigurationDialog.open();
        }

        function onSaveSucceeded(path) {
            root.clearOperationFailure();
            toastHost.showMessage(qsTr("Saved validated configuration: ") + path, "success");
        }

        target: root.configController
    }

    DecisionDialog {
        id: datasetDecisionDialog

        acceptText: qsTr("Continue")
        bodyText: root.controllerAvailable ? root.desktopController.datasetDecisionMessage : ""
        objectName: "datasetDecisionDialog"
        onAccepted: root.datasetDecisionCommitRequested(true)
        onRejected: root.datasetDecisionCancelRequested()
        rejectText: qsTr("Cancel")
        title: root.controllerAvailable ? root.desktopController.datasetDecisionTitle : ""
    }

    DecisionDialog {
        id: configurationDiscardDialog

        acceptText: qsTr("Discard and continue")
        bodyText: qsTr(
                      "The current configuration has unsaved changes. Discard them and continue with this operation?")
        objectName: "configurationDiscardDialog"
        onAccepted: {
            const action = root.pendingReplacementAction;
            root.pendingReplacementAction = "";
            if (action === "new") {
                const mode = root.pendingReplacementMode;
                root.pendingReplacementMode = "";
                root.datasetNewRequested(mode, true);
            } else if (action === "import") {
                const path = root.pendingReplacementPath;
                root.pendingReplacementPath = "";
                root.datasetImportRequested(path, true);
            } else if (action === "close") {
                root.datasetCloseRequested(true);
            }
        }
        onRejected: {
            root.pendingReplacementAction = "";
            root.pendingReplacementMode = "";
            root.pendingReplacementPath = "";
        }
        rejectText: qsTr("Cancel")
        title: qsTr("Discard unsaved configuration?")
    }

    DecisionDialog {
        id: reformatConfirmationDialog

        acceptText: qsTr("Reformat and continue")
        bodyText: qsTr(
                      "This imported file will be written in Carnopy's deterministic YAML format. Comments and source formatting are not preserved.")
        objectName: "reformatConfirmationDialog"
        onAccepted: {
            const action = root.pendingReformatAction;
            root.pendingReformatAction = "";
            root.datasetConfirmReformatRequested(action);
        }
        onRejected: root.pendingReformatAction = ""
        rejectText: qsTr("Cancel")
        title: qsTr("Confirm deterministic reformat")
    }

    DecisionDialog {
        id: externalChangeDialog

        acceptText: qsTr("Reload external file")
        alternateText: qsTr("Save As…")
        bodyText: qsTr(
                      "The saved configuration changed outside Carnopy. Reload the external file, save this draft under a new name, or cancel.")
        objectName: "externalChangeDialog"
        onAccepted: root.datasetReloadRequested(true)
        onAlternate: root.datasetSaveAsRequested(false)
        rejectText: qsTr("Cancel")
        title: qsTr("Configuration changed outside Carnopy")
    }

    DecisionDialog {
        id: shutdownDiscardDialog

        acceptText: qsTr("Discard and close")
        bodyText: qsTr(
                      "The open configuration has unsaved changes. Discard them and close Carnopy?")
        objectName: "shutdownDiscardDialog"
        onAccepted: root.shutdownConfirmed(true)
        onRejected: root.shutdownConfirmed(false)
        rejectText: qsTr("Cancel")
        title: qsTr("Close Carnopy?")
    }

    DecisionDialog {
        id: transientEditShutdownDialog

        acceptText: qsTr("Cancel edit and close")
        bodyText: ""
        objectName: "transientEditShutdownDialog"
        onAccepted: root.transientEditShutdownConfirmed(true)
        onRejected: root.transientEditShutdownConfirmed(false)
        rejectText: qsTr("Keep open")
        title: qsTr("Unfinished plot edit")
    }

    DecisionDialog {
        id: busyShutdownDialog

        property string busyMode: ""

        acceptText: qsTr("Cancel and close")
        bodyText: ""
        objectName: "busyShutdownDialog"
        onAccepted: root.busyShutdownConfirmed(true)
        onRejected: root.busyShutdownConfirmed(false)
        rejectText: qsTr("Keep open")
        title: busyMode === "force_stop_plot" ? qsTr("Stop plot render and close?") : qsTr(
                                                    "Cancel generation and close?")
    }

    FileDialog {
        id: saveConfigurationDialog

        defaultSuffix: "yaml"
        fileMode: FileDialog.SaveFile
        nameFilters: [qsTr("YAML configurations (*.yaml *.yml)")]
        objectName: "saveConfigurationDialog"
        parentWindow: root
        title: qsTr("Save dataset configuration")
        onAccepted: {
            root.saveSelectionPath = selectedFile.toString();
            root.saveSelectionAccepted = true;
            Qt.callLater(root.completeSaveSelection);
        }
        onRejected: {
            root.saveSelectionAccepted = false;
            root.saveSelectionPath = "";
            root.datasetSavePathCancelled();
        }
        onVisibleChanged: root.completeSaveSelection()
    }

    Shortcut {
        onActivated: root.routeTo("settings")
        sequence: "Ctrl+,"
    }

    Shortcut {
        onActivated: root.routeTo("help")
        sequences: [StandardKey.HelpContents]
    }
}
