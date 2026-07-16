pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import Carnopy

ApplicationWindow {
    id: root

    required property QtObject desktopController
    required property var qmlSettings
    required property string startupWorkspace

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

    color: Theme.canvas
    height: Math.max(600, qmlSettings.normalGeometry.height)
    minimumHeight: 600
    minimumWidth: 680
    objectName: "carnopyQmlRoot"
    title: qsTr("Carnopy")
    visibility: qmlSettings.maximized ? Window.Maximized : Window.Windowed
    width: Math.max(680, qmlSettings.normalGeometry.width)
    x: qmlSettings.normalGeometry.x
    y: qmlSettings.normalGeometry.y

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
        onTriggered: root.qmlSettings.rememberNormalGeometry(root.x, root.y, root.width,
                                                             root.height)

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

    onClosing: function (close) {
        root.qmlSettings.maximized = root.visibility === Window.Maximized;
        if (root.visibility === Window.Windowed)
            root.qmlSettings.rememberNormalGeometry(root.x, root.y, root.width, root.height);
    }
    onHeightChanged: rememberGeometrySoon()
    onWidthChanged: rememberGeometrySoon()
    onXChanged: rememberGeometrySoon()
    onYChanged: rememberGeometrySoon()

    Component.onCompleted: geometryTrackingReady = true

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
                    breadcrumb: root.startupWorkspace.length > 0 ? root.startupWorkspace : qsTr(
                                                                       "Local workbench")
                    inspectorOpen: root.inspectorWideVisible || inspectorDrawer.opened
                    objectName: "documentCommandBar"
                    onInspectorToggleRequested: root.toggleInspector()
                    onRailMenuRequested: navigationDrawer.open()
                    pageTitle: root.pageTitle(root.currentPage)
                    showInspectorButton: !root.inspectorWideVisible
                    showRailMenu: root.shellMode === "narrow"
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
            objectName: "persistentContextInspector"
            pageTitle: root.pageTitle(root.currentPage)
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
        width: Math.min(328, root.width * 0.9)

        contentItem: ContextInspector {
            closeButtonVisible: true
            pageTitle: root.pageTitle(root.currentPage)
            onCloseRequested: inspectorDrawer.close()
        }
    }

    Component {
        id: workspacePage

        EmptyStatePage {
            objectName: "workspacePage"
        }
    }

    Component {
        id: settingsPage

        SettingsPage {
            objectName: "settingsPage"
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
