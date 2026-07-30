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
    property string selectorText: qsTr("Edit selection")
    property bool allowMove: true
    property bool locked: false
    property bool showCanonicalIdentities: false
    property bool showPropertyPresentation: false
    property int summaryLimit: showPropertyPresentation ? 6 : 4
    readonly property int selectedCount: selectedList.count
    readonly property int remainingCount: Math.max(0, selectedCount - summaryLimit)

    signal moveRequested(int row, int offset)
    signal removeRequested(int row)
    signal selectionRequested(string value, bool selected)

    function focusRow(row) {
        selectorButton.forceActiveFocus();
        return selectorButton;
    }

    function openSelector() {
        if (!root.locked)
            selectorPopup.open();
    }

    implicitHeight: content.implicitHeight

    ColumnLayout {
        id: content

        anchors.left: parent.left
        anchors.right: parent.right
        spacing: Theme.spacingSmall

        AppButton {
            id: selectorButton

            Accessible.description: qsTr("Search and change selected %1 values").arg(root.noun)
            enabled: !root.locked
            iconName: "search"
            Layout.bottomMargin: root.showCanonicalIdentities ? Theme.spacingTiny : 0
            objectName: root.objectName + "OpenButton"
            onClicked: root.openSelector()
            text: root.selectorText
        }

        ListView {
            id: selectedList

            Accessible.name: qsTr("Selected %1 values").arg(root.noun)
            Layout.fillWidth: true
            Layout.preferredHeight: root.selectedCount === 0 ? 44 : Math.min(root.selectedCount,
                                                                             root.summaryLimit) * (
                                                                   root.showPropertyPresentation
                                                                   ? 48 : 40)
            boundsBehavior: Flickable.StopAtBounds
            clip: true
            flickableDirection: root.showPropertyPresentation ? Flickable.VerticalFlick :
                                                                Flickable.HorizontalFlick
            interactive: false
            model: root.selectedModel
            objectName: root.objectName + "SelectedList"
            orientation: root.showPropertyPresentation ? ListView.Vertical : ListView.Horizontal
            pixelAligned: true
            spacing: Theme.spacingTiny

            delegate: Rectangle {
                id: selectedRow

                required property string canonical
                required property string display
                required property int index
                required property string issue
                required property string label
                required property string symbol
                required property string unit
                required property string value

                border.color: issue.length > 0 ? Theme.danger : Theme.border
                border.width: 1
                color: Theme.surfaceRaised
                height: root.showPropertyPresentation ? 44 : 36
                objectName: root.objectName + "SelectedItem-" + index
                radius: Theme.radiusSmall
                width: root.showPropertyPresentation ? ListView.view.width : Math.min(
                                                           ListView.view.width,
                                                           selectedContent.implicitWidth + 18)

                RowLayout {
                    id: selectedContent

                    anchors.fill: parent
                    anchors.leftMargin: 10
                    anchors.rightMargin: 4
                    spacing: Theme.spacingTiny

                    Label {
                        Layout.fillWidth: root.showPropertyPresentation
                        Layout.maximumWidth: root.showPropertyPresentation
                                             ? Number.POSITIVE_INFINITY : 176
                        color: Theme.text
                        elide: Text.ElideRight
                        font.family: Theme.sansFamily
                        font.pixelSize: 12
                        text: root.showPropertyPresentation && selectedRow.label.length > 0
                              ? selectedRow.label : selectedRow.display
                    }

                    PropertySymbol {
                        Layout.preferredWidth: 34
                        accessibleName: selectedRow.label
                        objectName: "propertySymbol-" + selectedRow.value
                        symbolMarkup: selectedRow.symbol
                        visible: root.showPropertyPresentation && selectedRow.symbol.length > 0
                    }

                    Label {
                        Layout.preferredWidth: 92
                        color: Theme.textMuted
                        elide: Text.ElideRight
                        font.family: Theme.sansFamily
                        font.pixelSize: 11
                        horizontalAlignment: Text.AlignRight
                        text: selectedRow.unit
                        visible: root.showPropertyPresentation && selectedRow.unit.length > 0
                    }

                    AppButton {
                        Accessible.description: qsTr("Actions for %1").arg(selectedRow.display)
                        compact: true
                        implicitHeight: 30
                        implicitWidth: 30
                        objectName: root.objectName + "SelectedActions-" + selectedRow.index
                        onClicked: rowMenu.open()
                        text: qsTr("More actions")

                        contentItem: Label {
                            color: Theme.text
                            font.family: Theme.sansFamily
                            font.pixelSize: 18
                            horizontalAlignment: Text.AlignHCenter
                            text: "⋯"
                            verticalAlignment: Text.AlignVCenter
                        }

                        Menu {
                            id: rowMenu

                            MenuItem {
                                enabled: root.allowMove && selectedRow.index > 0 && !root.locked
                                objectName: root.objectName + "MoveUp-" + selectedRow.index
                                onTriggered: root.moveRequested(selectedRow.index, -1)
                                text: qsTr("Move up")
                            }

                            MenuItem {
                                enabled: root.allowMove && selectedRow.index + 1
                                         < selectedList.count && !root.locked
                                objectName: root.objectName + "MoveDown-" + selectedRow.index
                                onTriggered: root.moveRequested(selectedRow.index, 1)
                                text: qsTr("Move down")
                            }

                            MenuSeparator {}

                            MenuItem {
                                enabled: !root.locked
                                objectName: root.objectName + "Remove-" + selectedRow.index
                                onTriggered: root.removeRequested(selectedRow.index)
                                text: qsTr("Remove")
                            }
                        }
                    }
                }

                ToolTip.text: selectedRow.issue
                ToolTip.visible: selectedHover.hovered && selectedRow.issue.length > 0

                HoverHandler {
                    id: selectedHover
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

        AppButton {
            Accessible.description: qsTr("Show every selected %1").arg(root.noun)
            objectName: root.objectName + "MoreButton"
            onClicked: root.openSelector()
            text: qsTr("+%1 more").arg(root.remainingCount)
            tone: "quiet"
            visible: root.remainingCount > 0
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.spacingTiny
            visible: root.showCanonicalIdentities && selectedList.count > 0

            Label {
                Layout.alignment: Qt.AlignVCenter
                color: Theme.textMuted
                font.family: Theme.sansFamily
                font.pixelSize: 11
                objectName: root.objectName + "CanonicalLabel"
                text: qsTr("Canonical backend identities:")
                verticalAlignment: Text.AlignVCenter
            }

            ListView {
                Layout.alignment: Qt.AlignVCenter
                Layout.fillWidth: true
                Layout.preferredHeight: 20
                boundsBehavior: Flickable.StopAtBounds
                clip: true
                interactive: false
                model: root.selectedModel
                objectName: root.objectName + "CanonicalList"
                orientation: ListView.Horizontal
                spacing: Theme.spacingTiny

                delegate: Label {
                    required property string canonical
                    required property int index

                    color: Theme.textMuted
                    font.family: Theme.monoFamily
                    font.pixelSize: 11
                    height: ListView.view.height
                    text: canonical + (index + 1 < selectedList.count ? "," : "")
                    verticalAlignment: Text.AlignVCenter
                    width: implicitWidth
                }
            }
        }
    }

    Popup {
        id: selectorPopup

        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        focus: true
        modal: false
        objectName: root.objectName + "Popover"
        padding: 14
        parent: Overlay.overlay
        width: Math.min(560, Math.max(320, parent.width - 48))
        x: Math.round((parent.width - width) / 2)
        y: Math.max(24, Math.round((parent.height - height) / 2))

        onClosed: {
            if (root.choiceModel !== null)
            root.choiceModel.filterText = "";
            searchField.text = "";
            selectorButton.forceActiveFocus();
        }
        onOpened: {
            if (root.choiceModel !== null)
            root.choiceModel.filterText = "";
            searchField.text = "";
            searchField.forceActiveFocus();
        }

        background: Rectangle {
            border.color: Theme.borderStrong
            border.width: 1
            color: Theme.surface
            radius: Theme.radiusMedium
        }

        contentItem: ColumnLayout {
            spacing: Theme.spacingMedium

            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.spacingSmall

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 2

                    Label {
                        Layout.fillWidth: true
                        color: Theme.text
                        font.family: Theme.sansFamily
                        font.pixelSize: 17
                        font.weight: Font.DemiBold
                        text: root.selectorText
                    }

                    Label {
                        Layout.fillWidth: true
                        color: Theme.textMuted
                        font.family: Theme.sansFamily
                        font.pixelSize: 11
                        text: qsTr("Changes apply immediately.")
                    }
                }

                AppButton {
                    objectName: root.objectName + "DoneButton"
                    onClicked: selectorPopup.close()
                    text: qsTr("Done")
                    tone: "primary"
                }
            }

            TextField {
                id: searchField

                Accessible.name: qsTr("Search available %1 values").arg(root.noun)
                Layout.fillWidth: true
                objectName: root.objectName + "SearchField"
                placeholderText: qsTr("Search by name, identifier, or canonical value")
                selectByMouse: true
                onTextChanged: {
                    if (root.choiceModel !== null)
                    root.choiceModel.filterText = text;
                    chooserList.currentIndex = chooserList.count > 0 ? 0 : -1;
                }

                Keys.onDownPressed: event => {
                    if (chooserList.count > 0) {
                        chooserList.currentIndex = 0;
                        chooserList.currentItem.forceActiveFocus();
                        event.accepted = true;
                    }
                }
            }

            ListView {
                id: chooserList

                Accessible.name: qsTr("Matching %1 choices").arg(root.noun)
                Layout.fillWidth: true
                Layout.preferredHeight: Math.min(320, Math.max(88, contentHeight))
                boundsBehavior: Flickable.StopAtBounds
                clip: true
                currentIndex: count > 0 ? 0 : -1
                model: root.choiceModel
                objectName: root.objectName + "ChoiceList"
                pixelAligned: true
                spacing: Theme.spacingTiny

                ScrollBar.vertical: ScrollBar {
                    policy: ScrollBar.AsNeeded
                }

                delegate: ItemDelegate {
                    id: choiceRow

                    required property int index
                    required property var model

                    function boolRole(name) {
                        return choiceRow.model !== null && choiceRow.model !== undefined
                                && choiceRow.model[name] === true;
                    }

                    function stringRole(name) {
                        if (choiceRow.model === null || choiceRow.model === undefined
                                || choiceRow.model[name] === null || choiceRow.model[name]
                                === undefined)
                            return "";
                        return String(choiceRow.model[name]);
                    }

                    function applySelection() {
                        if (!choiceRow.enabled)
                            return;
                        root.selectionRequested(choiceRow.stringRole("value"), !choiceRow.boolRole(
                                                    "selected"));
                        Qt.callLater(function () {
                            if (selectorPopup.opened)
                                searchField.forceActiveFocus();
                        });
                    }

                    Accessible.description: stringRole("issue")
                    Accessible.name: stringRole("label").length > 0 ? stringRole("label") :
                                                                      stringRole("display")
                    activeFocusOnTab: true
                    enabled: !root.locked && (boolRole("compatible") || boolRole("selected"))
                    highlighted: ListView.isCurrentItem || hovered
                    objectName: root.objectName + "ChoiceItem-" + index
                    onClicked: applySelection()
                    width: ListView.view.width

                    Keys.onDownPressed: event => {
                        if (choiceRow.index + 1 < chooserList.count) {
                            chooserList.currentIndex = choiceRow.index + 1;
                            chooserList.currentItem.forceActiveFocus();
                        }
                        event.accepted = true;
                    }
                    Keys.onReturnPressed: event => {
                        choiceRow.applySelection();
                        event.accepted = true;
                    }
                    Keys.onSpacePressed: event => {
                        choiceRow.applySelection();
                        event.accepted = true;
                    }
                    Keys.onUpPressed: event => {
                        if (choiceRow.index === 0) {
                            searchField.forceActiveFocus();
                        } else {
                            chooserList.currentIndex = choiceRow.index - 1;
                            chooserList.currentItem.forceActiveFocus();
                        }
                        event.accepted = true;
                    }

                    contentItem: RowLayout {
                        spacing: Theme.spacingSmall

                        Label {
                            Layout.preferredWidth: 20
                            color: choiceRow.boolRole("selected") ? Theme.success : Theme.textSubtle
                            font.family: Theme.sansFamily
                            font.pixelSize: 14
                            text: choiceRow.boolRole("selected") ? "✓" : ""
                        }

                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 1

                            Label {
                                Layout.fillWidth: true
                                color: choiceRow.enabled ? Theme.text : Theme.textSubtle
                                elide: Text.ElideRight
                                font.family: Theme.sansFamily
                                font.pixelSize: 12
                                text: choiceRow.stringRole("label").length > 0
                                      ? choiceRow.stringRole("label") : choiceRow.stringRole(
                                            "display")
                            }

                            Label {
                                Layout.fillWidth: true
                                color: choiceRow.stringRole("issue").length > 0 ? Theme.danger :
                                                                                  Theme.textMuted

                                elide: Text.ElideRight
                                font.family: Theme.monoFamily
                                font.pixelSize: 10
                                text: choiceRow.stringRole("issue").length > 0
                                      ? choiceRow.stringRole("issue") : choiceRow.stringRole(
                                            "value") + (choiceRow.stringRole("canonical")
                                                        !== choiceRow.stringRole("value") ? " · "
                                                                                            + choiceRow.stringRole(
                                                                                                "canonical") :
                                                                                            "")
                            }
                        }

                        PropertySymbol {
                            Layout.preferredWidth: 34
                            accessibleName: choiceRow.stringRole("label")
                            symbolMarkup: choiceRow.stringRole("symbol")
                            visible: root.showPropertyPresentation && choiceRow.stringRole(
                                         "symbol").length > 0
                        }

                        Label {
                            Layout.preferredWidth: 92
                            color: Theme.textMuted
                            font.family: Theme.sansFamily
                            font.pixelSize: 11
                            horizontalAlignment: Text.AlignRight
                            text: choiceRow.stringRole("unit")
                            visible: root.showPropertyPresentation && choiceRow.stringRole(
                                         "unit").length > 0
                        }
                    }

                    background: Rectangle {
                        border.color: choiceRow.activeFocus ? Theme.focus : (choiceRow.stringRole(
                                                                                 "issue").length
                                                                             > 0 ? Theme.danger :
                                                                                   Theme.border)
                        border.width: choiceRow.activeFocus ? 2 : 1
                        color: choiceRow.highlighted ? Theme.surfaceMuted : Theme.surfaceRaised
                        radius: Theme.radiusSmall
                    }
                }

                Label {
                    anchors.centerIn: parent
                    color: Theme.textMuted
                    font.family: Theme.sansFamily
                    font.pixelSize: 12
                    text: qsTr("No matching %1 values").arg(root.noun)
                    visible: chooserList.count === 0
                }
            }
        }
    }
}
