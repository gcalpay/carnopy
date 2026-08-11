pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts
import QtQuick.Window
import Carnopy

Item {
    id: root

    function openImportDialog() {
        if (root.importFolder.toString().length > 0)
            importConfigurationDialog.currentFolder = root.importFolder;
        importConfigurationDialog.open();
    }

    required property var desktopController
    required property url importFolder
    property int expectedColumns: 1
    readonly property bool controllerAvailable: desktopController !== null
    readonly property bool configurationActionsVisible: workspaceState === "landing"
                                                        || workspaceState === "editing"
    readonly property string workspaceState: controllerAvailable ? desktopController.workspaceState :
                                                                   "unavailable"
    property bool initializeSelectionAccepted: false
    property string initializeSelectionPath: ""
    property bool openSelectionAccepted: false
    property string openSelectionPath: ""
    property bool reopenCreateDialogAfterFolderSelection: false

    signal cancelWorkspaceRequested
    signal commitWorkspaceRequested(bool confirmed)
    signal createWorkspacePathRequested(string path)
    signal createWorkspaceRequested(string parentPath, string childName)
    signal initializeWorkspaceRequested(string path)
    signal openWorkspaceRequested(string path)
    signal importConfigurationRequested(string path)
    signal newDatasetRequested(string mode)
    signal newSweepRequested
    property bool importSelectionAccepted: false
    property string importSelectionPath: ""

    function chooseCreateParent(reopenCreateDialog) {
        reopenCreateDialogAfterFolderSelection = reopenCreateDialog;
        if (createDialog.opened) {
            createDialog.close();
            createParentFolderOpenTimer.restart();
            return;
        }
        createParentFolderDialog.open();
    }

    function completeInitializeSelection() {
        if (!initializeSelectionAccepted || initializeFolderDialog.visible)
            return;
        const path = initializeSelectionPath;
        initializeSelectionAccepted = false;
        initializeSelectionPath = "";
        Qt.callLater(() => {
            const window = root.Window.window;
            if (window !== null)
                window.requestActivate();
            if (root.controllerAvailable)
                root.initializeWorkspaceRequested(path);
        });
    }

    function completeOpenSelection() {
        if (!openSelectionAccepted || openFolderDialog.visible)
            return;
        const path = openSelectionPath;
        openSelectionAccepted = false;
        openSelectionPath = "";
        Qt.callLater(() => {
            const window = root.Window.window;
            if (window !== null)
                window.requestActivate();
            if (root.controllerAvailable)
                root.openWorkspaceRequested(path);
        });
    }

    function completeImportSelection() {
        if (!importSelectionAccepted || importConfigurationDialog.visible)
            return;
        const path = importSelectionPath;
        importSelectionAccepted = false;
        importSelectionPath = "";
        Qt.callLater(() => {
            const window = root.Window.window;
            if (window !== null)
                window.requestActivate();
            if (root.controllerAvailable)
                root.importConfigurationRequested(path);
        });
    }

    Timer {
        id: createParentFolderOpenTimer

        interval: 1
        onTriggered: createParentFolderDialog.open()
    }

    Flickable {
        anchors.fill: parent
        boundsBehavior: Flickable.StopAtBounds
        clip: true
        contentHeight: pageColumn.implicitHeight + 48
        contentWidth: width
        flickableDirection: Flickable.VerticalFlick
        objectName: "workspacePageFlickable"
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
                        text: root.workspaceState === "unavailable" ? qsTr("Choose a workspace") :
                                                                      qsTr("Workspace")
                    }

                    Label {
                        Layout.fillWidth: true
                        color: Theme.textMuted
                        elide: Text.ElideMiddle
                        font.family: Theme.monoFamily
                        font.pixelSize: 12
                        text: root.controllerAvailable && root.desktopController.workspaceAvailable
                              ? root.desktopController.workspaceRootPath : qsTr(
                                    "Local folders remain under your control.")
                    }
                }

                StatusBadge {
                    label: {
                        if (root.workspaceState === "loading")
                        return qsTr("Loading capabilities");
                        if (root.workspaceState === "editing")
                        return qsTr("Configuration open");
                        if (root.workspaceState === "landing")
                        return qsTr("Workspace ready");
                        return qsTr("No workspace");
                    }
                    tone: root.workspaceState === "unavailable" ? "neutral" : (root.workspaceState
                                                                               === "loading"
                                                                               ? "information" :
                                                                                 "success")
                }
            }

            Card {
                Layout.fillWidth: true
                title: root.controllerAvailable
                       && root.desktopController.workspaceErrorMessage.length > 0 ? qsTr(
                                                                                        "Workspace action needs attention") :
                                                                                    qsTr("Workspace status")

                Label {
                    Layout.fillWidth: true
                    color: root.controllerAvailable
                           && root.desktopController.workspaceErrorMessage.length > 0
                           ? Theme.danger : Theme.textMuted
                    font.family: Theme.sansFamily
                    font.pixelSize: 12
                    objectName: "workspaceStatusMessage"
                    text: root.controllerAvailable
                          && root.desktopController.workspaceErrorMessage.length > 0
                          ? root.desktopController.workspaceErrorMessage : (
                                root.controllerAvailable
                                ? root.desktopController.workspaceStatusMessage : qsTr(
                                      "No workspace is open."))
                    wrapMode: Text.Wrap
                }

                ProgressBar {
                    Layout.fillWidth: true
                    indeterminate: true
                    objectName: "workspaceLoadingIndicator"
                    visible: root.workspaceState === "loading"
                }
            }

            ResponsiveCardGrid {
                Layout.fillWidth: true
                Layout.preferredHeight: implicitHeight
                maximumColumns: 3
                minimumCardWidth: 300
                objectName: "workspaceOverviewGrid"

                Card {
                    Layout.fillHeight: true
                    Layout.fillWidth: true
                    objectName: "createWorkspaceCard"
                    subtitle: qsTr(
                                  "Create a new folder below an existing parent. Existing targets are never reused or overwritten.")
                    title: qsTr("Create Workspace")

                    AppButton {
                        enabled: root.controllerAvailable
                                 && root.desktopController.canChangeWorkspace
                        iconName: "layout-dashboard"
                        objectName: "createWorkspaceButton"
                        onClicked: {
                            createDialog.resetFields();
                            root.chooseCreateParent(false);
                        }
                        text: qsTr("Create")
                        tone: "primary"
                    }
                }

                Card {
                    Layout.fillHeight: true
                    Layout.fillWidth: true
                    objectName: "initializeWorkspaceCard"
                    subtitle: qsTr(
                                  "Choose an existing ordinary folder that is not yet a Carnopy workspace. After confirmation, Carnopy adds its marker and managed subfolders without deleting unrelated contents.")
                    title: qsTr("Initialize Existing Folder")

                    AppButton {
                        enabled: root.controllerAvailable
                                 && root.desktopController.canChangeWorkspace
                        iconName: "database"
                        objectName: "initializeWorkspaceButton"
                        onClicked: initializeFolderDialog.open()
                        text: qsTr("Choose existing folder")
                    }
                }

                Card {
                    Layout.fillHeight: true
                    Layout.fillWidth: true
                    objectName: "openWorkspaceCard"
                    subtitle: qsTr(
                                  "Choose a folder that was already created or initialized by Carnopy. Carnopy validates its marker and managed structure before opening it.")
                    title: qsTr("Open Carnopy Workspace")

                    AppButton {
                        enabled: root.controllerAvailable
                                 && root.desktopController.canChangeWorkspace
                        iconName: "search"
                        objectName: "openWorkspaceButton"
                        onClicked: openFolderDialog.open()
                        text: qsTr("Choose workspace folder")
                    }
                }
            }

            Card {
                Layout.fillWidth: true
                subtitle: qsTr("Paths are stored in the existing Carnopy settings identity.")
                title: qsTr("Recent workspaces")

                ListView {
                    id: recentList

                    Layout.fillWidth: true
                    Layout.preferredHeight: Math.min(220, Math.max(48, contentHeight))
                    boundsBehavior: Flickable.StopAtBounds
                    clip: true
                    flickableDirection: Flickable.VerticalFlick
                    interactive: contentHeight > height
                    model: root.controllerAvailable ? root.desktopController.recentWorkspaces : null
                    objectName: "recentWorkspaceList"
                    pixelAligned: true
                    spacing: Theme.spacingSmall

                    ScrollBar.vertical: ScrollBar {
                        policy: ScrollBar.AsNeeded
                    }

                    delegate: AppButton {
                        id: recentButton

                        required property string path

                        iconName: "layout-dashboard"
                        objectName: "recentWorkspaceButton"
                        onClicked: root.openWorkspaceRequested(path)
                        text: path
                        width: ListView.view.width
                    }

                    Label {
                        anchors.centerIn: parent
                        color: Theme.textMuted
                        font.family: Theme.sansFamily
                        font.pixelSize: 12
                        text: qsTr("No recent workspaces")
                        visible: recentList.count === 0
                    }
                }
            }

            ResponsiveCardGrid {
                Layout.fillWidth: true
                Layout.preferredHeight: implicitHeight
                maximumColumns: 3
                minimumCardWidth: 300
                objectName: "newDatasetModeGrid"
                visible: root.configurationActionsVisible

                Repeater {
                    model: root.controllerAvailable
                           ? root.desktopController.datasetDraft.modeChoices : null

                    delegate: Card {
                        required property string value

                        Layout.fillWidth: true
                        subtitle: qsTr(
                                      "Start from Carnopy's packaged, worker-validated mode template.")
                        title: {
                            if (value === "property_table")
                            return qsTr("Property table");
                            if (value === "saturation_table")
                            return qsTr("Saturation table");
                            return qsTr("Vapor-mass-fraction table");
                        }

                        AppButton {
                            enabled: root.controllerAvailable
                                     && root.desktopController.configurationController.canCreate
                            objectName: "newDatasetButton-" + value
                            onClicked: root.newDatasetRequested(value)
                            text: qsTr("New Dataset")
                            tone: "primary"
                        }
                    }
                }
            }

            Card {
                Layout.fillWidth: true
                objectName: "newModelSweepCard"
                subtitle: qsTr(
                              "Compare two or more CoolProp models over one reproducible dataset specification with worker-verified planning and execution.")
                title: qsTr("Model Sweep")
                visible: root.configurationActionsVisible

                AppButton {
                    Accessible.description: qsTr(
                                                "Create a new structured Model Sweep configuration")
                    enabled: root.controllerAvailable
                             && root.desktopController.configurationController.canCreate
                    iconName: "git-compare-arrows"
                    objectName: "newModelSweepButton"
                    onClicked: root.newSweepRequested()
                    text: qsTr("New Model Sweep")
                    tone: "primary"
                }
            }

            Card {
                Layout.fillWidth: true
                subtitle: qsTr(
                              "Choose Dataset, Model Sweep, or Preparation YAML from configs/. The document_type discriminator selects the exact public schema. External YAML remains importable.")
                title: qsTr("Open or Import Configuration")
                visible: root.configurationActionsVisible

                AppButton {
                    enabled: root.controllerAvailable
                             && root.desktopController.configurationController.canImport
                    objectName: "importDatasetButton"
                    onClicked: root.openImportDialog()
                    text: qsTr("Choose YAML")
                }
            }
        }
    }

    WorkspaceOperationDialog {
        id: createDialog

        objectName: "createWorkspaceDialog"
        onBrowseParentRequested: root.chooseCreateParent(true)
        onCreateRequested: (path, childName, expertMode) => {
            if (!root.controllerAvailable)
                return;
            if (expertMode)
                root.createWorkspacePathRequested(path);
            else
                root.createWorkspaceRequested(path, childName);
        }
    }

    Connections {
        function onWorkspaceConfirmationRequested() {
            confirmationDialog.open();
        }

        target: root.controllerAvailable ? root.desktopController : null
    }

    DecisionDialog {
        id: confirmationDialog

        acceptText: qsTr("Continue")
        bodyText: root.controllerAvailable ? root.desktopController.workspaceConfirmationMessage :
                                             ""
        objectName: "workspaceConfirmationDialog"
        onAccepted: {
            if (root.controllerAvailable)
            root.commitWorkspaceRequested(true);
        }
        onRejected: {
            if (root.controllerAvailable)
            root.cancelWorkspaceRequested();
        }
        rejectText: qsTr("Cancel")
        title: root.controllerAvailable ? root.desktopController.workspaceConfirmationTitle : ""
    }

    FolderDialog {
        id: createParentFolderDialog

        objectName: "createParentFolderDialog"
        parentWindow: root.Window.window
        title: qsTr("Choose an existing parent folder")
        onAccepted: {
            createDialog.parentPath = selectedFolder.toString();
            root.reopenCreateDialogAfterFolderSelection = false;
            Qt.callLater(() => createDialog.open());
        }
        onRejected: {
            if (root.reopenCreateDialogAfterFolderSelection)
            Qt.callLater(() => createDialog.open());
            root.reopenCreateDialogAfterFolderSelection = false;
        }
    }

    FolderDialog {
        id: initializeFolderDialog

        objectName: "initializeFolderDialog"
        parentWindow: root.Window.window
        title: qsTr("Choose an existing folder to initialize")
        onAccepted: {
            root.initializeSelectionPath = selectedFolder.toString();
            root.initializeSelectionAccepted = true;
            Qt.callLater(root.completeInitializeSelection);
        }
        onRejected: {
            root.initializeSelectionAccepted = false;
            root.initializeSelectionPath = "";
        }
        onVisibleChanged: root.completeInitializeSelection()
    }

    FolderDialog {
        id: openFolderDialog

        objectName: "openFolderDialog"
        parentWindow: root.Window.window
        title: qsTr("Choose an initialized Carnopy workspace")
        onAccepted: {
            root.openSelectionPath = selectedFolder.toString();
            root.openSelectionAccepted = true;
            Qt.callLater(root.completeOpenSelection);
        }
        onRejected: {
            root.openSelectionAccepted = false;
            root.openSelectionPath = "";
        }
        onVisibleChanged: root.completeOpenSelection()
    }

    FileDialog {
        id: importConfigurationDialog

        fileMode: FileDialog.OpenFile
        nameFilters: [qsTr("YAML configurations (*.yaml *.yml)")]
        objectName: "importConfigurationDialog"
        parentWindow: root.Window.window
        title: qsTr("Import a dataset configuration")
        onAccepted: {
            root.importSelectionPath = selectedFile.toString();
            root.importSelectionAccepted = true;
            Qt.callLater(root.completeImportSelection);
        }
        onRejected: {
            root.importSelectionAccepted = false;
            root.importSelectionPath = "";
        }
        onVisibleChanged: root.completeImportSelection()
    }
}
