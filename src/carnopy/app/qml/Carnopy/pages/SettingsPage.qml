import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Carnopy

Item {
    id: root

    required property var qmlSettings

    signal layoutResetRequested

    Flickable {
        anchors.fill: parent
        boundsBehavior: Flickable.StopAtBounds
        clip: true
        contentHeight: pageColumn.implicitHeight + 48
        contentWidth: width
        flickableDirection: Flickable.VerticalFlick
        objectName: "settingsPageFlickable"
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

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 3

                Label {
                    color: Theme.text
                    font.family: Theme.sansFamily
                    font.pixelSize: 23
                    font.weight: Font.DemiBold
                    text: qsTr("Settings")
                }

                Label {
                    Layout.fillWidth: true
                    color: Theme.textMuted
                    font.family: Theme.sansFamily
                    font.pixelSize: 13
                    text: qsTr("Appearance and layout preferences are local to Carnopy Desktop.")
                    wrapMode: Text.Wrap
                }
            }

            Card {
                Layout.fillWidth: true
                subtitle: qsTr(
                              "System follows the operating-system color scheme and updates while Carnopy is running.")
                title: qsTr("Theme")

                RowLayout {
                    Layout.fillWidth: true
                    spacing: Theme.spacingSmall

                    AppButton {
                        Layout.fillWidth: true
                        iconName: "monitor"
                        objectName: "systemThemeButton"
                        onClicked: {
                            if (root.qmlSettings !== null)
                                root.qmlSettings.themeMode = "system";
                        }
                        text: qsTr("System")
                        tone: root.qmlSettings !== null && root.qmlSettings.themeMode === "system"
                              ? "primary" : "secondary"
                    }

                    AppButton {
                        Layout.fillWidth: true
                        iconName: "appearance-light"
                        objectName: "lightThemeButton"
                        onClicked: {
                            if (root.qmlSettings !== null)
                                root.qmlSettings.themeMode = "light";
                        }
                        text: qsTr("Light")
                        tone: root.qmlSettings !== null && root.qmlSettings.themeMode === "light"
                              ? "primary" : "secondary"
                    }

                    AppButton {
                        Layout.fillWidth: true
                        iconColor: Theme.warning
                        iconName: "appearance-warm"
                        objectName: "warmThemeButton"
                        onClicked: {
                            if (root.qmlSettings !== null)
                                root.qmlSettings.themeMode = "warm";
                        }
                        text: qsTr("Warm")
                        tone: root.qmlSettings !== null && root.qmlSettings.themeMode === "warm"
                              ? "primary" : "secondary"
                    }

                    AppButton {
                        Layout.fillWidth: true
                        iconName: "appearance-dark"
                        objectName: "darkThemeButton"
                        onClicked: {
                            if (root.qmlSettings !== null)
                                root.qmlSettings.themeMode = "dark";
                        }
                        text: qsTr("Dark")
                        tone: root.qmlSettings !== null && root.qmlSettings.themeMode === "dark"
                              ? "primary" : "secondary"
                    }
                }

                Label {
                    Layout.fillWidth: true
                    color: Theme.textMuted
                    font.family: Theme.sansFamily
                    font.pixelSize: 12
                    text: qsTr("Effective theme: %1").arg(root.qmlSettings === null ? "" :
                                                                                      root.qmlSettings.effectiveTheme)
                }
            }

            Card {
                Layout.fillWidth: true
                objectName: "motionPreferenceCard"
                subtitle: root.qmlSettings !== null && root.qmlSettings.reducedMotion ? qsTr(
                                                                                            "Reduced motion is active. Subsequent control and notification transitions are immediate; scrolling remains direct.") :
                                                                                        qsTr("Standard motion is active. Brief control and notification transitions remain interruptible; scrolling remains direct.")
                title: qsTr("Motion and accessibility")

                Switch {
                    Accessible.description: qsTr("Disable nonessential interface animation")
                    Layout.fillWidth: true
                    checked: root.qmlSettings !== null && root.qmlSettings.reducedMotion
                    font.family: Theme.sansFamily
                    objectName: "reducedMotionSwitch"
                    onToggled: {
                        if (root.qmlSettings !== null)
                            root.qmlSettings.reducedMotion = checked;
                    }
                    text: qsTr("Reduce motion")
                }
            }

            Card {
                Layout.fillWidth: true
                subtitle: qsTr(
                              "These preferences apply immediately on wide screens and are restored at the next start. Compact and narrow modes use temporary responsive overrides.")
                title: qsTr("Wide desktop layout")

                Switch {
                    Layout.fillWidth: true
                    checked: root.qmlSettings !== null && root.qmlSettings.railCollapsed
                    font.family: Theme.sansFamily
                    objectName: "railPreferenceSwitch"
                    onToggled: {
                        if (root.qmlSettings !== null)
                            root.qmlSettings.railCollapsed = checked;
                    }
                    text: qsTr("Navigation rail collapsed")
                }

                Switch {
                    Layout.fillWidth: true
                    checked: root.qmlSettings !== null && root.qmlSettings.inspectorCollapsed
                    font.family: Theme.sansFamily
                    objectName: "inspectorPreferenceSwitch"
                    onToggled: {
                        if (root.qmlSettings !== null)
                            root.qmlSettings.inspectorCollapsed = checked;
                    }
                    text: qsTr("Context inspector collapsed")
                }
            }

            Card {
                Layout.fillWidth: true
                subtitle: qsTr(
                              "Restores the wide rail, inspector, normal geometry, and non-maximized state. Theme and reduced-motion choices are preserved.")
                title: qsTr("Reset layout")

                AppButton {
                    iconName: "rotate-ccw"
                    objectName: "resetLayoutButton"
                    onClicked: resetDialog.open()
                    text: qsTr("Reset layout")
                }
            }
        }
    }

    DecisionDialog {
        id: resetDialog

        acceptText: qsTr("Reset layout")
        bodyText: qsTr(
                      "Reset the saved QML window geometry, navigation rail, and context inspector layout?")
        onAccepted: {
            if (root.qmlSettings !== null)
                root.layoutResetRequested();
        }
        title: qsTr("Reset interface layout")
    }
}
