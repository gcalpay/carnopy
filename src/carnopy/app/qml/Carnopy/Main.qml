pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
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
    signal normalGeometryRememberRequested(int x, int y, int width, int height)
    signal settingsLayoutResetRequested

    readonly property bool runtimeReady: true
    readonly property string shellMode: width >= 1280 ? "wide" : (width >= 800 ? "compact" :
                                                                                 "narrow")

    readonly property bool railEffectiveCollapsed: shellMode !== "wide" || qmlSettings.railCollapsed
    readonly property bool inspectorWideVisible: shellMode === "wide" &&
                                                 !qmlSettings.inspectorCollapsed
    readonly property int railWidth: shellMode === "narrow" ? 0 : (railEffectiveCollapsed ? 76 :
                                                                                            224)

    readonly property int inspectorWidth: inspectorWideVisible ? 304 : 0
    readonly property int availableCentralWidth: Math.max(1, width - railWidth - inspectorWidth)
    readonly property int cardColumnCount: Math.max(1, Math.min(3, Math.floor((
                                                                                  availableCentralWidth
                                                                                  - 48 + 12)
                                                                              / 312)))
    readonly property bool controllerAvailable: desktopController !== null
    readonly property bool hasFake3dViewport: false
    readonly property string effectiveTheme: qmlSettings.effectiveTheme
    readonly property int motionDuration: Theme.durationStandard
    property string currentPage: "workspace"
    property bool geometryTrackingReady: false

    function pageTitle(pageKey) {
        if (pageKey === "settings")
            return qsTr("Settings");
        if (pageKey === "help")
            return qsTr("Help");
        return qsTr("Workspace");
    }

    function routeTo(pageKey) {
        currentPage = pageKey;
        navigationDrawer.close();
    }

    function toggleRail() {
        if (shellMode === "wide")
            qmlSettings.railCollapsed = !qmlSettings.railCollapsed;
        else if (shellMode === "narrow")
            navigationDrawer.open();
    }

    function toggleInspector() {
        if (shellMode === "wide")
            qmlSettings.inspectorCollapsed = !qmlSettings.inspectorCollapsed;
        else if (inspectorDrawer.opened)
            inspectorDrawer.close();
        else
            inspectorDrawer.open();
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
        visibility = qmlSettings.maximized ? Window.Maximized : Window.Windowed;
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
    palette.highlightedText: "#ffffff"
    palette.placeholderText: Theme.textSubtle
    palette.text: Theme.text
    palette.window: Theme.canvas
    palette.windowText: Theme.text
    title: qsTr("Carnopy")
    visibility: Window.Hidden
    width: 1440

    Binding {
        property: "dark"
        target: Theme
        value: root.qmlSettings.effectiveTheme === "dark"
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
            objectName: "persistentNavigationRail"
            onCollapseRequested: root.toggleRail()
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
                    Layout.fillWidth: true
                    breadcrumb: root.controllerAvailable
                                && root.desktopController.workspaceAvailable
                                ? root.desktopController.workspaceRootPath : qsTr("Local workbench")
                    inspectorOpen: root.inspectorWideVisible || inspectorDrawer.opened
                    objectName: "documentCommandBar"
                    onInspectorToggleRequested: root.toggleInspector()
                    onRailMenuRequested: navigationDrawer.open()
                    pageTitle: root.pageTitle(root.currentPage)
                    showInspectorButton: !(root.inspectorWideVisible || inspectorDrawer.opened)
                    showRailMenu: root.shellMode === "narrow"
                    statusLabel: {
                        if (root.controllerAvailable && root.desktopController.workspaceState
                            === "loading")
                        return qsTr("Loading");
                        if (root.controllerAvailable && root.desktopController.workspaceAvailable)
                        return qsTr("Workspace ready");
                        return qsTr("No workspace");
                    }
                    statusTone: root.controllerAvailable
                                && root.desktopController.workspaceAvailable ? "success" : "neutral"
                }

                Loader {
                    Layout.fillHeight: true
                    Layout.fillWidth: true
                    objectName: "workbenchPageLoader"
                    sourceComponent: {
                        if (root.currentPage === "settings")
                        return settingsPage;
                        if (root.currentPage === "help")
                        return helpPage;
                        return workspacePage;
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

        ContextInspector {
            Layout.fillHeight: true
            Layout.preferredWidth: root.inspectorWidth
            closeButtonVisible: true
            objectName: "persistentContextInspector"
            onCloseRequested: root.toggleInspector()
            workspacePath: root.controllerAvailable ? root.desktopController.workspaceRootPath : ""
            workspaceState: root.controllerAvailable ? root.desktopController.workspaceState :
                                                       "unavailable"
            visible: root.inspectorWideVisible
        }
    }

    Drawer {
        id: navigationDrawer

        edge: Qt.LeftEdge
        height: root.height
        modal: true
        width: Math.min(300, root.width * 0.88)

        contentItem: NavRail {
            allowCollapse: false
            collapsed: false
            currentPage: root.currentPage
            onPageRequested: pageKey => root.routeTo(pageKey)
        }
    }

    Drawer {
        id: inspectorDrawer

        edge: Qt.RightEdge
        height: root.height
        modal: root.shellMode === "narrow"
        objectName: "inspectorDrawer"
        width: Math.min(328, root.width * 0.9)

        contentItem: ContextInspector {
            closeButtonVisible: true
            objectName: "drawerContextInspector"
            onCloseRequested: inspectorDrawer.close()
            workspacePath: root.controllerAvailable ? root.desktopController.workspaceRootPath : ""
            workspaceState: root.controllerAvailable ? root.desktopController.workspaceState :
                                                       "unavailable"
        }
    }

    Component {
        id: workspacePage

        WorkspacePage {
            desktopController: root.desktopController
            expectedColumns: root.cardColumnCount
            objectName: "workspacePage"
            onCancelWorkspaceRequested: root.workspaceCancelRequested()
            onCommitWorkspaceRequested: confirmed => root.workspaceCommitRequested(confirmed)
            onCreateWorkspacePathRequested: path => root.workspaceCreatePathRequested(path)
            onCreateWorkspaceRequested: (parentPath, childName) => root.workspaceCreateRequested(
                                                                       parentPath, childName)
            onInitializeWorkspaceRequested: path => root.workspaceInitializeRequested(path)
            onOpenWorkspaceRequested: path => root.workspaceOpenRequested(path)
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

    Shortcut {
        enabled: root.shellMode === "wide"
        onActivated: root.toggleRail()
        sequence: "Ctrl+B"
    }

    Shortcut {
        onActivated: root.toggleInspector()
        sequence: "Ctrl+I"
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
