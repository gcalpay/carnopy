import QtQuick
import QtQuick.Layouts
import Carnopy

Item {
    id: root

    default property alias contentData: grid.data
    property int minimumCardWidth: 300
    property int maximumColumns: 3
    readonly property int columnCount: Math.max(1, Math.min(maximumColumns, Math.floor((width
                                                                                        + grid.columnSpacing)
                                                                                       / (minimumCardWidth
                                                                                          + grid.columnSpacing))))

    implicitHeight: grid.implicitHeight

    GridLayout {
        id: grid

        anchors.left: parent.left
        anchors.right: parent.right
        columnSpacing: Theme.spacingMedium
        columns: root.columnCount
        rowSpacing: Theme.spacingMedium
    }
}
