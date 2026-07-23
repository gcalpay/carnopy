pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Carnopy

Control {
    id: root

    property bool collapsed: false
    property bool allowCollapse: true
    property string currentPage: "workspace"
    property bool datasetAvailable: false
    property bool visualizationAvailable: false
    property bool yamlAvailable: false
    readonly property alias collapseControl: railCollapseButton
    readonly property alias navigationModel: navigationModel
    readonly property int preferredWidth: collapsed ? 76 : 224

    function restoreCurrentPageFocus() {
        for (let row = 0; row < navigationModel.count; ++row) {
            if (navigationModel.get(row).pageKey !== root.currentPage)
                continue;
            navigationList.positionViewAtIndex(row, ListView.Contain);
            Qt.callLater(() => {
                const item = navigationList.itemAtIndex(row);
                if (item !== null && item.visible && item.enabled)
                    item.forceActiveFocus(Qt.OtherFocusReason);
            });
            return;
        }
    }

    signal collapseRequested
    signal pageRequested(string pageKey)

    implicitWidth: preferredWidth
    padding: 10

    background: Rectangle {
        color: Theme.navigation
    }

    ListModel {
        id: navigationModel

        objectName: "primaryNavigationModel"

        ListElement {
            pageKey: "workspace"
            title: qsTr("Workspace")
            iconName: "layout-dashboard"
            available: true
            unavailableReason: ""
        }
        ListElement {
            pageKey: "dataset"
            title: qsTr("Dataset")
            iconName: "database"
            available: true
            unavailableReason: qsTr("Create or import a dataset configuration first.")
        }
        ListElement {
            pageKey: "visualization"
            title: qsTr("Visualization")
            iconName: "chart-spline"
            available: true
            unavailableReason: qsTr("Create or import a dataset configuration first.")
        }
        ListElement {
            pageKey: "yaml"
            title: qsTr("YAML Preview")
            iconName: "file-code"
            available: true
            unavailableReason: qsTr("Create or import a dataset configuration first.")
        }
        ListElement {
            pageKey: "run"
            title: qsTr("Run")
            iconName: "play"
            available: false
            unavailableReason: qsTr("Generation is the next GUI-2 workflow in Stage 3.")
        }
        ListElement {
            pageKey: "inspect"
            title: qsTr("Inspect")
            iconName: "search"
            available: false
            unavailableReason: qsTr("Inspection follows generation in Stage 4.")
        }
        ListElement {
            pageKey: "activity"
            title: qsTr("Activity and Recovery")
            iconName: "activity"
            available: false
            unavailableReason: qsTr("Jobs and recovery enter QML in Stage 5.")
        }
        ListElement {
            pageKey: "sweeps"
            title: qsTr("Model Sweeps")
            iconName: "git-compare-arrows"
            available: false
            unavailableReason: qsTr("Model-sweep workflow migration follows the core GUI-2 stages.")
        }
        ListElement {
            pageKey: "preparation"
            title: qsTr("ML Preparation")
            iconName: "flask-conical"
            available: false
            unavailableReason: qsTr("ML preparation remains outside the active GUI-2 stage.")
        }
        ListElement {
            pageKey: "three-d"
            title: qsTr("3D")
            iconName: "box"
            available: false
            unavailableReason: qsTr("Native 3D is reserved for GUI-2 Stages 6 and 7.")
        }
    }

    contentItem: ColumnLayout {
        spacing: Theme.spacingSmall

        RowLayout {
            Layout.fillWidth: true
            Layout.leftMargin: root.collapsed ? 7 : 4
            Layout.rightMargin: root.collapsed ? 7 : 4
            Layout.topMargin: 4
            spacing: 10

            Image {
                Layout.preferredHeight: 36
                Layout.preferredWidth: 36
                fillMode: Image.PreserveAspectFit
                source: Theme.brandingSource()
                sourceSize.height: 72
                sourceSize.width: 72
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 0
                visible: !root.collapsed

                Label {
                    color: Theme.navigationText
                    font.family: Theme.sansFamily
                    font.pixelSize: 16
                    font.weight: Font.DemiBold
                    text: qsTr("CARNOPY")
                }

                Label {
                    color: Theme.navigationMuted
                    font.family: Theme.sansFamily
                    font.pixelSize: 9
                    text: qsTr("Scientific data workbench")
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.leftMargin: 4
            Layout.rightMargin: 4
            Layout.topMargin: 4
            color: Theme.divider
            Layout.preferredHeight: 1
        }

        ListView {
            id: navigationList

            Layout.fillHeight: true
            Layout.fillWidth: true
            boundsBehavior: Flickable.StopAtBounds
            clip: true
            flickableDirection: Flickable.VerticalFlick
            model: navigationModel
            pixelAligned: true
            spacing: 3

            ScrollBar.vertical: ScrollBar {
                policy: ScrollBar.AsNeeded
            }

            delegate: Button {
                id: navigationButton

                required property bool available
                required property string iconName
                required property string pageKey
                required property string title
                required property string unavailableReason

                readonly property bool effectivelyAvailable: available && (pageKey !== "dataset"
                                                                           || root.datasetAvailable)
                                                             && (pageKey !== "visualization"
                                                                 || root.visualizationAvailable) && (
                                                                 pageKey !== "yaml"
                                                                 || root.yamlAvailable)

                Accessible.description: effectivelyAvailable ? "" : unavailableReason
                Accessible.name: title
                activeFocusOnTab: effectivelyAvailable
                checkable: effectivelyAvailable
                checked: root.currentPage === pageKey
                enabled: effectivelyAvailable
                height: 42
                hoverEnabled: true
                objectName: "nav-" + pageKey
                onClicked: root.pageRequested(pageKey)
                width: navigationList.width

                ToolTip.delay: 500
                ToolTip.text: effectivelyAvailable && root.collapsed ? title : unavailableReason
                ToolTip.visible: hovered && (root.collapsed || !effectivelyAvailable)

                contentItem: RowLayout {
                    spacing: 11

                    AppIcon {
                        Layout.alignment: Qt.AlignVCenter
                        Layout.leftMargin: root.collapsed ? 8 : 4
                        iconColor: navigationButton.enabled ? Theme.navigationText :
                                                              Theme.navigationMuted
                        iconSize: 19
                        name: navigationButton.iconName
                        opacity: navigationButton.enabled ? 1 : 0.55
                    }

                    Label {
                        Layout.fillWidth: true
                        color: navigationButton.enabled ? Theme.navigationText :
                                                          Theme.navigationMuted
                        elide: Text.ElideRight
                        font.family: Theme.sansFamily
                        font.pixelSize: 12
                        font.weight: navigationButton.checked ? Font.Medium : Font.Normal
                        opacity: navigationButton.enabled ? 1 : 0.62
                        text: navigationButton.title
                        visible: !root.collapsed
                    }
                }

                background: Rectangle {
                    border.color: navigationButton.activeFocus ? Theme.focus : "transparent"
                    border.width: navigationButton.activeFocus ? 2 : 0
                    color: {
                        if (navigationButton.checked)
                        return Theme.navigationSelected;
                        if (navigationButton.hovered && navigationButton.enabled)
                        return Theme.navigationRaised;
                        return "transparent";
                    }
                    radius: Theme.radiusSmall

                    Behavior on color {
                        ColorAnimation {
                            duration: Theme.durationFast
                        }
                    }
                }
            }
        }

        AppButton {
            Layout.fillWidth: true
            compact: root.collapsed
            foregroundColor: Theme.navigationText
            iconName: "settings"
            objectName: "settingsNavigationButton"
            onClicked: root.pageRequested("settings")
            text: qsTr("Settings")
            tone: root.currentPage === "settings" ? "primary" : "quiet"
        }

        AppButton {
            Layout.fillWidth: true
            compact: root.collapsed
            foregroundColor: Theme.navigationText
            iconName: "circle-question-mark"
            objectName: "helpNavigationButton"
            onClicked: root.pageRequested("help")
            text: qsTr("Help")
            tone: root.currentPage === "help" ? "primary" : "quiet"
        }

        AppButton {
            id: railCollapseButton

            Accessible.description: root.collapsed ? qsTr("Expand navigation rail") : qsTr(
                                                         "Collapse navigation rail")
            Layout.fillWidth: true
            compact: root.collapsed
            foregroundColor: Theme.navigationText
            iconName: root.collapsed ? "panel-left-open" : "panel-left-close"
            objectName: "railCollapseButton"
            onClicked: root.collapseRequested()
            text: qsTr("Collapse")
            tone: "quiet"
            visible: root.allowCollapse
        }
    }
}
