pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Carnopy

Item {
    id: root

    property var choiceModel: null
    property var selectedModel: null
    property string emptyText: qsTr("Nothing selected")
    property string noun: qsTr("item")
    property bool allowMove: true
    property bool locked: false

    signal addRequested(string value)
    signal moveRequested(int row, int offset)
    signal removeRequested(int row)
    signal removeValueRequested(int row, string value)

    implicitHeight: content.implicitHeight

    ColumnLayout {
        id: content

        anchors.left: parent.left
        anchors.right: parent.right
        spacing: Theme.spacingSmall

        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.spacingSmall

            AppComboBox {
                id: choiceBox

                Accessible.name: qsTr("Available %1").arg(root.noun)
                Layout.fillWidth: true
                delegateObjectPrefix: root.objectName + "Choice"
                model: root.choiceModel
                objectName: root.objectName + "ChoiceBox"
                textRole: "display"
                valueRole: "value"
            }

            AppButton {
                enabled: !root.locked && choiceBox.count > 0 && choiceBox.currentValue !== undefined
                objectName: root.objectName + "AddButton"
                onClicked: root.addRequested(String(choiceBox.currentValue))
                text: qsTr("Add")
                tone: "primary"
            }
        }

        ListView {
            id: selectedList

            Accessible.name: qsTr("Selected %1 values").arg(root.noun)
            Layout.fillWidth: true
            Layout.preferredHeight: Math.max(48, Math.min(184, contentHeight))
            boundsBehavior: Flickable.StopAtBounds
            clip: true
            flickableDirection: Flickable.VerticalFlick
            interactive: contentHeight > height
            model: root.selectedModel
            objectName: root.objectName + "SelectedList"
            pixelAligned: true
            spacing: Theme.spacingTiny

            ScrollBar.vertical: ScrollBar {
                policy: ScrollBar.AsNeeded
            }

            delegate: Rectangle {
                id: selectedRow

                required property string display
                required property int index
                required property string issue
                required property string value

                border.color: issue.length > 0 ? Theme.danger : Theme.border
                border.width: 1
                color: Theme.surfaceRaised
                height: 42
                radius: Theme.radiusSmall
                width: ListView.view.width

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 10
                    anchors.rightMargin: 6
                    spacing: Theme.spacingTiny

                    Label {
                        Layout.fillWidth: true
                        color: Theme.text
                        elide: Text.ElideRight
                        font.family: Theme.sansFamily
                        font.pixelSize: 12
                        text: selectedRow.display
                    }

                    AppButton {
                        Accessible.description: qsTr("Move %1 up").arg(selectedRow.display)
                        enabled: !root.locked && selectedRow.index > 0
                        implicitWidth: 56
                        onClicked: root.moveRequested(selectedRow.index, -1)
                        text: qsTr("Up")
                        visible: root.allowMove
                    }

                    AppButton {
                        Accessible.description: qsTr("Move %1 down").arg(selectedRow.display)
                        enabled: !root.locked && selectedRow.index + 1 < selectedList.count
                        implicitWidth: 64
                        onClicked: root.moveRequested(selectedRow.index, 1)
                        text: qsTr("Down")
                        visible: root.allowMove
                    }

                    AppButton {
                        Accessible.description: qsTr("Remove %1").arg(selectedRow.display)
                        enabled: !root.locked
                        implicitWidth: 78
                        onClicked: {
                            root.removeRequested(selectedRow.index);
                            root.removeValueRequested(selectedRow.index, selectedRow.value);
                        }
                        text: qsTr("Remove")
                    }
                }

                ToolTip.text: selectedRow.issue
                ToolTip.visible: hover.hovered && selectedRow.issue.length > 0

                HoverHandler {
                    id: hover
                }
            }

            Label {
                anchors.centerIn: parent
                color: Theme.textMuted
                font.family: Theme.sansFamily
                font.pixelSize: 12
                text: root.emptyText
                visible: selectedList.count === 0
            }
        }
    }
}
