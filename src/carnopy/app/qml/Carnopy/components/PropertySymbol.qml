import QtQuick
import QtQuick.Controls
import Carnopy

Label {
    id: root

    required property string accessibleName
    required property string symbolMarkup

    Accessible.name: root.accessibleName
    Accessible.role: Accessible.StaticText
    color: Theme.textMuted
    font.family: Theme.sansFamily
    font.pixelSize: 12
    horizontalAlignment: Text.AlignHCenter
    text: root.symbolMarkup
    textFormat: Text.RichText
}
