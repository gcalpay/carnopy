import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Carnopy

Dialog {
    id: root

    property string bodyText: ""
    property string acceptText: qsTr("Continue")
    property string alternateText: ""
    property string rejectText: qsTr("Cancel")

    signal alternate

    anchors.centerIn: Overlay.overlay
    closePolicy: Popup.CloseOnEscape
    modal: true
    padding: 20
    standardButtons: Dialog.NoButton
    width: Math.min(460, Overlay.overlay.width - 32)

    background: Rectangle {
        border.color: Theme.borderStrong
        border.width: 1
        color: Theme.surface
        radius: Theme.radiusLarge
    }

    contentItem: ColumnLayout {
        spacing: Theme.spacingLarge

        Label {
            Layout.fillWidth: true
            color: Theme.text
            font.family: Theme.sansFamily
            font.pixelSize: 14
            text: root.bodyText
            wrapMode: Text.Wrap
        }

        RowLayout {
            Layout.alignment: Qt.AlignRight
            spacing: Theme.spacingSmall

            AppButton {
                text: root.rejectText
                onClicked: root.reject()
            }

            AppButton {
                onClicked: {
                    root.close();
                    root.alternate();
                }
                text: root.alternateText
                visible: text.length > 0
            }

            AppButton {
                text: root.acceptText
                tone: "primary"
                onClicked: root.accept()
            }
        }
    }
}
