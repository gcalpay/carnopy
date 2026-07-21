import QtQuick
import QtQuick.Controls
import Carnopy

Control {
    id: root

    property string text: ""
    property int searchPosition: 0

    function copyAll() {
        sourceText.selectAll();
        sourceText.copy();
        sourceText.deselect();
    }

    function findNext(query) {
        const needle = String(query);
        if (needle.length === 0) {
            sourceText.deselect();
            root.searchPosition = 0;
            return false;
        }
        const lowerText = root.text.toLocaleLowerCase();
        const lowerNeedle = needle.toLocaleLowerCase();
        let index = lowerText.indexOf(lowerNeedle, root.searchPosition);
        if (index < 0)
            index = lowerText.indexOf(lowerNeedle, 0);
        if (index < 0) {
            sourceText.deselect();
            root.searchPosition = 0;
            return false;
        }
        sourceText.cursorPosition = index + needle.length;
        sourceText.select(index, index + needle.length);
        root.searchPosition = index + needle.length;
        return true;
    }

    function lineNumberText() {
        const count = Math.max(1, root.text.split("\n").length);
        const lines = [];
        for (let row = 1; row <= count; ++row)
            lines.push(String(row));
        return lines.join("\n");
    }

    background: Rectangle {
        border.color: Theme.border
        border.width: 1
        color: Theme.surface
        radius: Theme.radiusSmall
    }

    contentItem: Flickable {
        id: sourceFlickable

        boundsBehavior: Flickable.StopAtBounds
        clip: true
        contentHeight: Math.max(height, sourceRow.implicitHeight)
        contentWidth: Math.max(width, sourceRow.implicitWidth)
        flickableDirection: Flickable.AutoFlickDirection

        ScrollBar.horizontal: ScrollBar {
            policy: ScrollBar.AsNeeded
        }

        ScrollBar.vertical: ScrollBar {
            policy: ScrollBar.AsNeeded
        }

        Row {
            id: sourceRow

            height: Math.max(sourceFlickable.height, implicitHeight)

            Rectangle {
                color: Theme.surfaceMuted
                height: parent.height
                width: 56

                Text {
                    anchors.fill: parent
                    anchors.margins: 12
                    color: Theme.textSubtle
                    font.family: Theme.monoFamily
                    font.pixelSize: 12
                    horizontalAlignment: Text.AlignRight
                    text: root.lineNumberText()
                }
            }

            Rectangle {
                color: Theme.border
                height: parent.height
                width: 1
            }

            TextEdit {
                id: sourceText

                Accessible.name: qsTr("Authoritative YAML preview")
                color: Theme.text
                font.family: Theme.monoFamily
                font.pixelSize: 12
                height: Math.max(sourceFlickable.height, implicitHeight + 24)
                leftPadding: 14
                objectName: "yamlSourceText"
                readOnly: true
                rightPadding: 14
                selectByKeyboard: true
                selectByMouse: true
                selectionColor: Theme.primary
                selectedTextColor: "#ffffff"
                text: root.text
                textFormat: Text.PlainText
                topPadding: 12
                width: Math.max(sourceFlickable.width - 57, implicitWidth + 28)
                wrapMode: TextEdit.NoWrap
            }
        }
    }
}
