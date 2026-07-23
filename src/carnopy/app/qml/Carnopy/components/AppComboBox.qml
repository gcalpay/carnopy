pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import Carnopy

ComboBox {
    id: root

    property string delegateObjectPrefix: objectName

    palette.button: Theme.surfaceRaised
    palette.buttonText: Theme.text
    palette.highlight: Theme.primary
    palette.highlightedText: Theme.highlightedText
    palette.text: Theme.text
    palette.window: Theme.surfaceRaised
    hoverEnabled: true
    implicitHeight: 36

    contentItem: Label {
        color: Theme.text
        elide: Text.ElideRight
        font.family: Theme.sansFamily
        font.pixelSize: 12
        leftPadding: 0
        rightPadding: 0
        text: root.displayText
        verticalAlignment: Text.AlignVCenter
    }

    delegate: ItemDelegate {
        id: rowDelegate

        required property int index

        highlighted: root.highlightedIndex === index
        objectName: root.delegateObjectPrefix + "Item-" + index
        text: root.textAt(index)
        width: ListView.view.width

        contentItem: Label {
            color: Theme.text
            elide: Text.ElideRight
            font.family: Theme.sansFamily
            font.pixelSize: 12
            text: rowDelegate.text
            verticalAlignment: Text.AlignVCenter
        }

        background: Rectangle {
            color: rowDelegate.highlighted || rowDelegate.hovered ? Theme.hover :
                                                                    Theme.surfaceRaised
        }
    }

    background: Rectangle {
        border.color: root.activeFocus ? Theme.focus : Theme.borderStrong
        border.width: root.activeFocus ? 2 : 1
        color: root.hovered ? Theme.hover : Theme.surfaceRaised
        radius: Theme.radiusSmall

        Behavior on color {
            ColorAnimation {
                duration: Theme.durationFast
            }
        }
    }
}
