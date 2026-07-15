pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ApplicationWindow {
    id: root

    required property QtObject desktopController
    required property string startupWorkspace
    readonly property bool runtimeReady: true

    visible: true
    width: 760
    height: 480
    color: "#f4f7f9"
    title: qsTr("Carnopy")
    objectName: "carnopyQmlRoot"

    Rectangle {
        anchors.fill: parent
        color: root.color

        ColumnLayout {
            anchors.centerIn: parent
            spacing: 18

            Image {
                Layout.alignment: Qt.AlignHCenter
                Layout.preferredWidth: 112
                Layout.preferredHeight: 112
                fillMode: Image.PreserveAspectFit
                source: "../../resources/branding/carnopy-mark.png"
                sourceSize.width: 224
                sourceSize.height: 224
            }

            Label {
                Layout.alignment: Qt.AlignHCenter
                color: "#0d2138"
                font.family: "IBM Plex Sans"
                font.pixelSize: 30
                font.weight: Font.DemiBold
                text: qsTr("Carnopy")
            }

            RowLayout {
                Layout.alignment: Qt.AlignHCenter
                spacing: 8

                Image {
                    Layout.preferredWidth: 18
                    Layout.preferredHeight: 18
                    source: "../../resources/icons/flask-conical.svg"
                    sourceSize.width: 36
                    sourceSize.height: 36
                }

                Label {
                    color: "#365067"
                    font.family: "IBM Plex Sans"
                    font.pixelSize: 14
                    text: qsTr("Packaged QML runtime ready")
                }
            }
        }
    }
}
