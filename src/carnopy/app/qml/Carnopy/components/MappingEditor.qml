pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Carnopy

Item {
    id: root

    required property var mappingModel
    property string emptyText: qsTr("No rows configured")
    property bool locked: false
    property string noun: qsTr("mapping")

    signal addRequested(var model)
    signal fieldChangeRequested(var model, int row, string field)
    signal removeRequested(var model, int row)
    signal valueChangeRequested(var model, int row, string value)

    function focusRow(row) {
        if (row >= 0)
            mappingList.positionViewAtIndex(row, ListView.Contain);
        Qt.callLater(function () {
            const item = row >= 0 ? mappingList.itemAtIndex(row) : null;
            if (item)
                item.forceActiveFocus();
            else
                addButton.forceActiveFocus();
        });
    }

    implicitHeight: content.implicitHeight

    ColumnLayout {
        id: content

        anchors.left: parent.left
        anchors.right: parent.right
        spacing: Theme.spacingSmall

        Label {
            Layout.fillWidth: true
            color: Theme.textMuted
            font.family: Theme.sansFamily
            font.pixelSize: 12
            text: root.emptyText
            visible: mappingList.count === 0
            wrapMode: Text.Wrap
        }

        ListView {
            id: mappingList

            Accessible.name: qsTr("Configured %1 rows").arg(root.noun)
            Layout.fillWidth: true
            Layout.preferredHeight: Math.max(0, Math.min(240, contentHeight))
            boundsBehavior: Flickable.StopAtBounds
            clip: true
            interactive: contentHeight > height
            model: root.mappingModel
            objectName: root.objectName + "Rows"
            pixelAligned: true
            spacing: Theme.spacingTiny

            ScrollBar.vertical: ScrollBar {
                policy: ScrollBar.AsNeeded
            }

            delegate: Rectangle {
                id: mappingRow

                required property var choices
                required property string field
                required property string hint
                required property int index
                required property string issue
                required property string rawValue

                border.color: issue.length > 0 ? Theme.danger : Theme.border
                border.width: 1
                color: Theme.surfaceRaised
                height: issue.length > 0 ? 92 : 60
                radius: Theme.radiusSmall
                width: ListView.view.width

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 8
                    spacing: Theme.spacingTiny

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: Theme.spacingSmall

                        AppComboBox {
                            id: fieldBox

                            Accessible.name: qsTr("%1 field").arg(root.noun)
                            Layout.fillWidth: true
                            Layout.minimumWidth: 0
                            currentIndex: indexForRoleValue(mappingRow.field)
                            enabled: !root.locked
                            model: root.mappingModel === null || root.mappingModel === undefined
                                   ? null : root.mappingModel.fieldChoices
                            objectName: root.objectName + "Field-" + mappingRow.index
                            onActivated: root.fieldChangeRequested(root.mappingModel,
                                                                   mappingRow.index, String(
                                                                       currentValue))
                        }

                        AppComboBox {
                            id: choiceValueBox

                            Accessible.name: qsTr("%1 value").arg(root.noun)
                            Layout.fillWidth: true
                            Layout.minimumWidth: 0
                            currentIndex: indexForRoleValue(mappingRow.rawValue)
                            enabled: !root.locked
                            model: mappingRow.choices
                            objectName: root.objectName + "ChoiceValue-" + mappingRow.index
                            onActivated: root.valueChangeRequested(root.mappingModel,
                                                                   mappingRow.index, String(
                                                                       currentValue))
                            textRole: "label"
                            valueRole: "value"
                            visible: mappingRow.choices.length > 0
                        }

                        TextField {
                            Accessible.name: qsTr("%1 value").arg(root.noun)
                            Layout.fillWidth: true
                            Layout.minimumWidth: 0
                            color: Theme.text
                            enabled: !root.locked
                            font.family: Theme.monoFamily
                            font.pixelSize: 12
                            objectName: root.objectName + "TextValue-" + mappingRow.index
                            onEditingFinished: root.valueChangeRequested(root.mappingModel,
                                                                         mappingRow.index, text)
                            placeholderText: mappingRow.hint
                            selectByMouse: true
                            text: mappingRow.rawValue
                            visible: mappingRow.choices.length === 0
                        }

                        AppButton {
                            Accessible.description: qsTr("Remove %1 row").arg(root.noun)
                            compact: true
                            enabled: !root.locked
                            objectName: root.objectName + "Remove-" + mappingRow.index
                            onClicked: root.removeRequested(root.mappingModel, mappingRow.index)
                            text: qsTr("Remove")
                        }
                    }

                    Label {
                        Layout.fillWidth: true
                        color: Theme.danger
                        font.family: Theme.sansFamily
                        font.pixelSize: 11
                        text: mappingRow.issue
                        visible: mappingRow.issue.length > 0
                        wrapMode: Text.Wrap
                    }
                }
            }
        }

        AppButton {
            id: addButton

            enabled: !root.locked && root.mappingModel !== null && root.mappingModel !== undefined
                     && root.mappingModel.fieldChoices.length > 0
            objectName: root.objectName + "AddButton"
            onClicked: root.addRequested(root.mappingModel)
            text: qsTr("Add row")
        }
    }
}
