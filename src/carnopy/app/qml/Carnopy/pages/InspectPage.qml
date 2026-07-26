pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts
import QtQuick.Window
import Carnopy

Item {
    id: root

    required property var inspectionController
    property bool focusTable: false
    property int selectedTab: 0
    property bool fileSelectionAccepted: false
    property string fileSelectionPath: ""
    property bool folderSelectionAccepted: false
    property string folderSelectionPath: ""

    signal inspectSourceRequested(string path)
    signal moreSourcesRequested
    signal previewPageRequested(int pageOffset)
    signal refreshRequested
    signal refreshSourcesRequested
    signal selectTableRequested(string tableId)

    function completeFileSelection() {
        if (!fileSelectionAccepted || inspectFileDialog.visible)
            return;
        const path = fileSelectionPath;
        fileSelectionAccepted = false;
        fileSelectionPath = "";
        Qt.callLater(() => {
            const window = root.Window.window;
            if (window !== null)
                window.requestActivate();
            root.inspectSourceRequested(path);
        });
    }

    function completeFolderSelection() {
        if (!folderSelectionAccepted || inspectFolderDialog.visible)
            return;
        const path = folderSelectionPath;
        folderSelectionAccepted = false;
        folderSelectionPath = "";
        Qt.callLater(() => {
            const window = root.Window.window;
            if (window !== null)
                window.requestActivate();
            root.inspectSourceRequested(path);
        });
    }

    component FactList: ColumnLayout {
        required property var factModel

        spacing: 6

        Repeater {
            model: parent.factModel

            delegate: RowLayout {
                id: factRow

                required property bool available
                required property string label
                required property var value

                Layout.fillWidth: true
                spacing: Theme.spacingSmall
                visible: available

                Label {
                    Layout.fillWidth: true
                    color: Theme.textMuted
                    font.family: Theme.sansFamily
                    font.pixelSize: 12
                    text: factRow.label
                    wrapMode: Text.Wrap
                }

                Label {
                    Layout.fillWidth: true
                    Layout.preferredWidth: 220
                    color: Theme.text
                    elide: Text.ElideMiddle
                    font.family: Theme.monoFamily
                    font.pixelSize: 11
                    horizontalAlignment: Text.AlignRight
                    text: String(factRow.value)
                }
            }
        }
    }

    component DiagnosticFact: RowLayout {
        property string labelText: ""
        property color valueColor: Theme.text
        property string valueText: ""

        spacing: Theme.spacingSmall

        Label {
            Layout.fillWidth: true
            color: Theme.textMuted
            font.family: Theme.sansFamily
            font.pixelSize: 12
            text: parent.labelText
            wrapMode: Text.Wrap
        }

        Label {
            color: parent.valueColor
            font.family: Theme.monoFamily
            font.pixelSize: 11
            text: parent.valueText
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.leftMargin: 24
        anchors.rightMargin: 24
        anchors.topMargin: 22
        anchors.bottomMargin: 20
        spacing: Theme.spacingMedium

        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.spacingMedium
            visible: !root.focusTable

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 3

                Label {
                    Layout.fillWidth: true
                    color: Theme.text
                    font.family: Theme.sansFamily
                    font.pixelSize: 23
                    font.weight: Font.DemiBold
                    text: qsTr("Inspect generated data")
                }

                Label {
                    Layout.fillWidth: true
                    color: Theme.textMuted
                    font.family: Theme.sansFamily
                    font.pixelSize: 12
                    text: qsTr(
                              "Review recorded summaries, bounded tables, arrays, and diagnostics without changing source artifacts.")
                    wrapMode: Text.Wrap
                }
            }

            StatusBadge {
                label: {
                    if (root.inspectionController.state === "loading")
                    return qsTr("Inspecting");
                    if (root.inspectionController.state === "ready")
                    return root.inspectionController.integrityLabel;
                    if (root.inspectionController.state === "failed"
                        || root.inspectionController.state === "stale")
                    return qsTr("Needs attention");
                    return qsTr("No source selected");
                }
                tone: root.inspectionController.state === "ready" ? "success" : (
                                                                        root.inspectionController.state
                                                                        === "failed"
                                                                        || root.inspectionController.state
                                                                        === "stale" ? "danger" : (
                                                                                          root.inspectionController.state
                                                                                          === "loading"
                                                                                          ? "information" :
                                                                                            "neutral"))
            }
        }

        BlockingBanner {
            Layout.fillWidth: true
            actionText: qsTr("Refresh")
            message: root.inspectionController.issue
            objectName: "inspectionIssueBanner"
            onActionRequested: root.refreshRequested()
            title: root.inspectionController.state === "stale" ? qsTr("Inspection is stale") : qsTr(
                                                                     "Inspection failed")
            visible: root.inspectionController.issue.length > 0 && (root.inspectionController.state
                                                                    === "failed"
                                                                    || root.inspectionController.state
                                                                    === "stale")
        }

        RowLayout {
            Layout.fillHeight: true
            Layout.fillWidth: true
            spacing: Theme.spacingMedium

            Card {
                Layout.fillHeight: true
                Layout.maximumWidth: 286
                Layout.minimumWidth: 220
                Layout.preferredWidth: 250
                objectName: "inspectionSourcesCard"
                subtitle: qsTr(
                              "Workspace outputs are revealed in bounded groups of 20. External sources are inspected only after an explicit choice.")
                title: qsTr("Sources")
                visible: !root.focusTable && root.width >= 900

                RowLayout {
                    Layout.fillWidth: true

                    AppButton {
                        compact: true
                        enabled: root.inspectionController.canInspect
                        iconName: "file-code"
                        objectName: "inspectExternalFileButton"
                        onClicked: inspectFileDialog.open()
                        text: qsTr("Inspect CSV or Parquet")

                        ToolTip.text: text
                        ToolTip.visible: hovered
                    }

                    AppButton {
                        compact: true
                        enabled: root.inspectionController.canInspect
                        iconName: "search"
                        objectName: "inspectExternalFolderButton"
                        onClicked: inspectFolderDialog.open()
                        text: qsTr("Inspect run or bundle")

                        ToolTip.text: text
                        ToolTip.visible: hovered
                    }

                    AppButton {
                        compact: true
                        enabled: root.inspectionController.canInspect
                        iconName: "rotate-ccw"
                        objectName: "refreshInspectionSourcesButton"
                        onClicked: root.refreshSourcesRequested()
                        text: qsTr("Refresh source list")

                        ToolTip.text: text
                        ToolTip.visible: hovered
                    }
                }

                ListView {
                    id: sourcesList

                    Layout.fillHeight: true
                    Layout.fillWidth: true
                    boundsBehavior: Flickable.StopAtBounds
                    clip: true
                    model: root.inspectionController.workspaceSourcesModel
                    objectName: "inspectionSourcesList"
                    spacing: 4

                    ScrollBar.vertical: ScrollBar {
                        policy: ScrollBar.AsNeeded
                    }

                    delegate: Button {
                        id: sourceButton

                        required property bool inspectable
                        required property string issue
                        required property string kindHint
                        required property string name
                        required property string path

                        Accessible.description: issue.length > 0 ? issue : path
                        Accessible.name: qsTr("Inspect %1: %2").arg(kindHint).arg(name)
                        activeFocusOnTab: inspectable
                        enabled: inspectable && root.inspectionController.canInspect
                        height: 52
                        hoverEnabled: true
                        objectName: "inspectionSourceButton"
                        onClicked: root.inspectSourceRequested(path)
                        width: sourcesList.width

                        contentItem: ColumnLayout {
                            spacing: 1

                            Label {
                                Layout.fillWidth: true
                                color: Theme.text
                                elide: Text.ElideMiddle
                                font.family: Theme.sansFamily
                                font.pixelSize: 12
                                font.weight: Font.Medium
                                text: sourceButton.kindHint.length > 0 ? sourceButton.kindHint :
                                                                         qsTr("Workspace output")
                            }

                            Label {
                                Layout.fillWidth: true
                                color: sourceButton.issue.length > 0 ? Theme.danger :
                                                                       Theme.textMuted
                                elide: Text.ElideRight
                                font.family: Theme.monoFamily
                                font.pixelSize: 10
                                text: sourceButton.issue.length > 0 ? sourceButton.issue :
                                                                      sourceButton.name
                            }
                        }

                        background: Rectangle {
                            border.color: root.inspectionController.sourcePath
                                          === sourceButton.path ? Theme.focus : Theme.divider
                            border.width: root.inspectionController.sourcePath
                                          === sourceButton.path || sourceButton.activeFocus ? 2 : 1
                            color: sourceButton.hovered ? Theme.hover : Theme.surfaceRaised
                            radius: Theme.radiusSmall
                        }
                    }

                    footer: AppButton {
                        enabled: root.inspectionController.hasMoreWorkspaceSources
                        objectName: "inspectionShowMoreButton"
                        onClicked: root.moreSourcesRequested()
                        text: qsTr("Show 20 more")
                        visible: root.inspectionController.hasMoreWorkspaceSources
                        width: sourcesList.width
                    }

                    Label {
                        anchors.centerIn: parent
                        color: Theme.textMuted
                        font.family: Theme.sansFamily
                        font.pixelSize: 12
                        horizontalAlignment: Text.AlignHCenter
                        text: qsTr("No inspectable outputs are present in this workspace yet.")
                        visible: sourcesList.count === 0
                        width: Math.max(1, parent.width - 24)
                        wrapMode: Text.Wrap
                    }
                }
            }

            Card {
                Layout.fillHeight: true
                Layout.fillWidth: true
                objectName: "inspectionWorkbenchCard"
                title: root.focusTable ? qsTr("Focused table preview") : (
                                             root.inspectionController.sourcePath.length > 0
                                             ? root.inspectionController.sourcePath : qsTr(
                                                   "Inspection workbench"))

                RowLayout {
                    Layout.fillWidth: true
                    visible: root.width < 900 && !root.focusTable

                    ComboBox {
                        id: compactSourceSelector

                        Layout.fillWidth: true
                        enabled: root.inspectionController.workspaceSourcesModel.count > 0
                        model: root.inspectionController.workspaceSourcesModel
                        objectName: "inspectionCompactSourceSelector"
                        textRole: "name"
                        valueRole: "path"
                    }

                    AppButton {
                        compact: true
                        enabled: compactSourceSelector.currentIndex >= 0
                                 && root.inspectionController.canInspect
                        iconName: "search"
                        objectName: "inspectionCompactInspectButton"
                        onClicked: root.inspectSourceRequested(compactSourceSelector.currentValue)
                        text: qsTr("Inspect selected workspace source")

                        ToolTip.text: text
                        ToolTip.visible: hovered
                    }

                    AppButton {
                        compact: true
                        enabled: root.inspectionController.canInspect
                        iconName: "file-code"
                        onClicked: inspectFileDialog.open()
                        text: qsTr("Inspect external file")

                        ToolTip.text: text
                        ToolTip.visible: hovered
                    }

                    AppButton {
                        compact: true
                        enabled: root.inspectionController.canInspect
                        iconName: "search"
                        onClicked: inspectFolderDialog.open()
                        text: qsTr("Inspect external run or bundle")

                        ToolTip.text: text
                        ToolTip.visible: hovered
                    }
                }

                ProgressBar {
                    Layout.fillWidth: true
                    indeterminate: true
                    objectName: "inspectionLoadingIndicator"
                    visible: root.inspectionController.state === "loading"
                             || root.inspectionController.previewState === "loading"
                }

                RowLayout {
                    Layout.fillWidth: true

                    TabBar {
                        id: inspectionTabs

                        Layout.fillWidth: true
                        currentIndex: root.selectedTab
                        objectName: "inspectionTabBar"
                        onCurrentIndexChanged: root.selectedTab = currentIndex
                        visible: !root.focusTable

                        TabButton {
                            text: qsTr("Summary")
                        }
                        TabButton {
                            text: qsTr("Tables")
                        }
                        TabButton {
                            text: qsTr("Arrays")
                        }
                        TabButton {
                            text: qsTr("Diagnostics")
                        }
                    }

                    AppButton {
                        enabled: root.inspectionController.previewState === "ready"
                        iconName: root.focusTable ? "panel-right-open" : "panel-right-close"
                        objectName: "inspectionFocusTableButton"
                        onClicked: {
                            root.focusTable = !root.focusTable;
                            root.selectedTab = 1;
                        }
                        text: root.focusTable ? qsTr("Exit Focus Table") : qsTr("Focus Table")
                    }
                }

                StackLayout {
                    Layout.fillHeight: true
                    Layout.fillWidth: true
                    currentIndex: root.focusTable ? 1 : root.selectedTab
                    objectName: "inspectionTabStack"

                    Flickable {
                        boundsBehavior: Flickable.StopAtBounds
                        clip: true
                        contentHeight: summaryColumn.implicitHeight
                        contentWidth: width
                        flickableDirection: Flickable.VerticalFlick

                        ScrollBar.vertical: ScrollBar {
                            policy: ScrollBar.AsNeeded
                        }

                        ColumnLayout {
                            id: summaryColumn

                            spacing: Theme.spacingMedium
                            width: parent.width

                            Card {
                                flat: true
                                Layout.fillWidth: true
                                title: qsTr("Source")

                                FactList {
                                    Layout.fillWidth: true
                                    factModel: root.inspectionController.sourceSummaryModel
                                }
                            }

                            Card {
                                flat: true
                                Layout.fillWidth: true
                                title: qsTr("Identity")

                                FactList {
                                    Layout.fillWidth: true
                                    factModel: root.inspectionController.identitySummaryModel
                                }
                            }

                            Card {
                                flat: true
                                Layout.fillWidth: true
                                title: qsTr("Backend")

                                FactList {
                                    Layout.fillWidth: true
                                    factModel: root.inspectionController.backendSummaryModel
                                }
                            }

                            Card {
                                flat: true
                                Layout.fillWidth: true
                                title: qsTr("Rows")

                                FactList {
                                    Layout.fillWidth: true
                                    factModel: root.inspectionController.rowSummaryModel
                                }
                            }
                        }
                    }

                    ColumnLayout {
                        spacing: Theme.spacingSmall

                        RowLayout {
                            Layout.fillWidth: true

                            ComboBox {
                                id: tableSelector

                                Layout.fillWidth: true
                                enabled: root.inspectionController.tablesModel.count > 0
                                model: root.inspectionController.tablesModel
                                objectName: "inspectionTableSelector"
                                textRole: "label"
                                valueRole: "id"
                                onActivated: root.selectTableRequested(currentValue)
                            }

                            Label {
                                color: Theme.textMuted
                                font.family: Theme.monoFamily
                                font.pixelSize: 11
                                objectName: "inspectionTableRange"
                                text: root.inspectionController.previewState === "ready" ? qsTr(
                                                                                               "Rows %1–%2 of %3").arg(
                                                                                               root.inspectionController.previewFirstRow).arg(
                                                                                               root.inspectionController.previewLastRow).arg(
                                                                                               root.inspectionController.previewTotalRows) :
                                                                                           qsTr("No preview")
                            }
                        }

                        GridLayout {
                            Layout.fillHeight: true
                            Layout.fillWidth: true
                            columns: 2
                            columnSpacing: 0
                            rowSpacing: 0

                            Item {
                                Layout.preferredHeight: tableHeader.implicitHeight
                                Layout.preferredWidth: 52
                            }

                            HorizontalHeaderView {
                                id: tableHeader

                                Layout.fillWidth: true
                                Layout.preferredHeight: 34
                                clip: true
                                syncView: previewTable

                                delegate: Rectangle {
                                    required property string display

                                    color: Theme.surfaceRaised
                                    implicitHeight: 34
                                    implicitWidth: 150

                                    Label {
                                        anchors.fill: parent
                                        anchors.leftMargin: 8
                                        anchors.rightMargin: 8
                                        color: Theme.text
                                        elide: Text.ElideRight
                                        font.family: Theme.sansFamily
                                        font.pixelSize: 11
                                        font.weight: Font.Medium
                                        text: parent.display
                                        verticalAlignment: Text.AlignVCenter
                                    }
                                }
                            }

                            VerticalHeaderView {
                                Layout.fillHeight: true
                                Layout.preferredWidth: 52
                                clip: true
                                syncView: previewTable

                                delegate: Rectangle {
                                    required property string display

                                    color: Theme.surfaceRaised
                                    implicitHeight: 32
                                    implicitWidth: 52

                                    Label {
                                        anchors.fill: parent
                                        color: Theme.textMuted
                                        font.family: Theme.monoFamily
                                        font.pixelSize: 10
                                        horizontalAlignment: Text.AlignHCenter
                                        text: parent.display
                                        verticalAlignment: Text.AlignVCenter
                                    }
                                }
                            }

                            TableView {
                                id: previewTable

                                Layout.fillHeight: true
                                Layout.fillWidth: true
                                boundsBehavior: Flickable.StopAtBounds
                                clip: true
                                columnSpacing: 1
                                model: root.inspectionController.tableModel
                                objectName: "inspectionPreviewTable"
                                reuseItems: true
                                rowSpacing: 1

                                columnWidthProvider: function () {
                                    return 150;
                                }
                                rowHeightProvider: function () {
                                    return 32;
                                }

                                delegate: Rectangle {
                                    required property string display

                                    color: Theme.surface
                                    implicitHeight: 32
                                    implicitWidth: 150

                                    Label {
                                        anchors.fill: parent
                                        anchors.leftMargin: 8
                                        anchors.rightMargin: 8
                                        color: Theme.text
                                        elide: Text.ElideRight
                                        font.family: Theme.monoFamily
                                        font.pixelSize: 10
                                        text: parent.display
                                        verticalAlignment: Text.AlignVCenter
                                    }
                                }

                                ScrollBar.horizontal: ScrollBar {
                                    policy: ScrollBar.AsNeeded
                                }
                                ScrollBar.vertical: ScrollBar {
                                    policy: ScrollBar.AsNeeded
                                }
                            }
                        }

                        RowLayout {
                            Layout.fillWidth: true

                            AppButton {
                                enabled: root.inspectionController.previewFirstRow > 1
                                         && root.inspectionController.canPreview
                                objectName: "inspectionPreviousPageButton"
                                onClicked: root.previewPageRequested(Math.max(0,
                                                                              root.inspectionController.tableModel.pageOffset
                                                                              - 100))
                                text: qsTr("Previous 100")
                            }

                            Item {
                                Layout.fillWidth: true
                            }

                            AppButton {
                                enabled: root.inspectionController.previewLastRow > 0
                                         && root.inspectionController.previewLastRow
                                         < root.inspectionController.previewTotalRows
                                         && root.inspectionController.canPreview
                                objectName: "inspectionNextPageButton"
                                onClicked: root.previewPageRequested(
                                               root.inspectionController.tableModel.pageOffset
                                               + 100)
                                text: qsTr("Next 100")
                            }
                        }
                    }

                    ListView {
                        boundsBehavior: Flickable.StopAtBounds
                        clip: true
                        model: root.inspectionController.arraysModel
                        objectName: "inspectionArraysList"
                        spacing: Theme.spacingSmall

                        ScrollBar.vertical: ScrollBar {
                            policy: ScrollBar.AsNeeded
                        }

                        delegate: Rectangle {
                            id: arrayRow

                            required property string arrayName
                            required property string artifactLabel
                            required property string dtype
                            required property string format
                            required property string issue
                            required property bool metadataAvailable
                            required property string shapeDisplay

                            border.color: Theme.divider
                            border.width: 1
                            color: Theme.surfaceRaised
                            height: arrayColumn.implicitHeight + 24
                            radius: Theme.radiusSmall
                            width: ListView.view.width

                            ColumnLayout {
                                id: arrayColumn

                                anchors.left: parent.left
                                anchors.leftMargin: 12
                                anchors.right: parent.right
                                anchors.rightMargin: 12
                                anchors.verticalCenter: parent.verticalCenter
                                spacing: 3

                                Label {
                                    Layout.fillWidth: true
                                    color: Theme.text
                                    font.family: Theme.sansFamily
                                    font.pixelSize: 13
                                    font.weight: Font.Medium
                                    text: arrayRow.arrayName.length > 0 ? arrayRow.arrayName :
                                                                          arrayRow.artifactLabel
                                }

                                Label {
                                    Layout.fillWidth: true
                                    color: Theme.textMuted
                                    font.family: Theme.monoFamily
                                    font.pixelSize: 10
                                    text: arrayRow.metadataAvailable ? qsTr("%1 · %2 · %3").arg(
                                                                           arrayRow.format).arg(
                                                                           arrayRow.shapeDisplay).arg(
                                                                           arrayRow.dtype) :
                                                                       arrayRow.issue
                                    wrapMode: Text.Wrap
                                }
                            }
                        }

                        Label {
                            anchors.centerIn: parent
                            color: Theme.textMuted
                            font.family: Theme.sansFamily
                            font.pixelSize: 12
                            text: qsTr("This source reports no array artifacts.")
                            visible: parent.count === 0
                        }
                    }

                    Flickable {
                        boundsBehavior: Flickable.StopAtBounds
                        clip: true
                        contentHeight: diagnosticsColumn.implicitHeight
                        contentWidth: width
                        flickableDirection: Flickable.VerticalFlick
                        objectName: "inspectionDiagnosticsList"

                        ScrollBar.vertical: ScrollBar {
                            policy: ScrollBar.AsNeeded
                        }

                        ColumnLayout {
                            id: diagnosticsColumn

                            spacing: Theme.spacingMedium
                            width: parent.width

                            Card {
                                flat: true
                                Layout.fillWidth: true
                                title: qsTr("Source diagnostics")
                                visible: root.inspectionController.diagnosticsModel.available

                                Repeater {
                                    model: root.inspectionController.diagnosticsModel

                                    delegate: DiagnosticFact {
                                        id: diagnosticFact

                                        required property string issue
                                        required property string label
                                        required property string severity
                                        required property var value

                                        Layout.fillWidth: true
                                        labelText: label
                                        valueColor: severity === "error" ? Theme.danger : Theme.text
                                        valueText: issue.length > 0 ? issue : String(value)
                                    }
                                }
                            }

                            Card {
                                flat: true
                                Layout.fillWidth: true
                                title: qsTr("Phase counts")
                                visible: root.inspectionController.phaseCountsModel.available

                                Repeater {
                                    model: root.inspectionController.phaseCountsModel

                                    delegate: DiagnosticFact {
                                        required property int count
                                        required property string phase

                                        Layout.fillWidth: true
                                        labelText: phase
                                        valueText: String(count)
                                    }
                                }
                            }

                            Card {
                                flat: true
                                Layout.fillWidth: true
                                title: qsTr("Failure layers")
                                visible: root.inspectionController.failureLayerCountsModel.available

                                Repeater {
                                    model: root.inspectionController.failureLayerCountsModel

                                    delegate: DiagnosticFact {
                                        Layout.fillWidth: true
                                        labelText: model.layer
                                        valueText: String(model.count)
                                    }
                                }
                            }

                            Card {
                                flat: true
                                Layout.fillWidth: true
                                title: qsTr("Failure codes")
                                visible: root.inspectionController.failureCodeCountsModel.available

                                Repeater {
                                    model: root.inspectionController.failureCodeCountsModel

                                    delegate: DiagnosticFact {
                                        required property string code
                                        required property int count

                                        Layout.fillWidth: true
                                        labelText: code
                                        valueText: String(count)
                                    }
                                }
                            }

                            Card {
                                flat: true
                                Layout.fillWidth: true
                                title: qsTr("Failure properties")
                                visible: root.inspectionController.failurePropertyCountsModel.available

                                Repeater {
                                    model: root.inspectionController.failurePropertyCountsModel

                                    delegate: DiagnosticFact {
                                        Layout.fillWidth: true
                                        labelText: model.property
                                        valueText: String(model.count)
                                    }
                                }
                            }

                            Card {
                                flat: true
                                Layout.fillWidth: true
                                title: qsTr("Sweep delta reasons")
                                visible: root.inspectionController.sweepDeltaReasonCountsModel.available

                                Repeater {
                                    model: root.inspectionController.sweepDeltaReasonCountsModel

                                    delegate: DiagnosticFact {
                                        required property int count
                                        required property string reason

                                        Layout.fillWidth: true
                                        labelText: reason
                                        valueText: String(count)
                                    }
                                }
                            }

                            Card {
                                flat: true
                                Layout.fillWidth: true
                                title: qsTr("Preparation quality errors")
                                visible: root.inspectionController.preparationQualityErrorsModel.available

                                Repeater {
                                    model: root.inspectionController.preparationQualityErrorsModel

                                    delegate: Label {
                                        required property string message

                                        Layout.fillWidth: true
                                        color: Theme.danger
                                        font.family: Theme.sansFamily
                                        font.pixelSize: 12
                                        text: message
                                        wrapMode: Text.Wrap
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    FileDialog {
        id: inspectFileDialog

        fileMode: FileDialog.OpenFile
        nameFilters: [qsTr("Carnopy tables (*.csv *.parquet)")]
        objectName: "inspectionFileDialog"
        parentWindow: root.Window.window
        title: qsTr("Inspect a CSV or Parquet source")
        onAccepted: {
            root.fileSelectionPath = selectedFile.toString();
            root.fileSelectionAccepted = true;
            Qt.callLater(root.completeFileSelection);
        }
        onRejected: {
            root.fileSelectionAccepted = false;
            root.fileSelectionPath = "";
        }
        onVisibleChanged: root.completeFileSelection()
    }

    FolderDialog {
        id: inspectFolderDialog

        objectName: "inspectionFolderDialog"
        parentWindow: root.Window.window
        title: qsTr("Inspect a generated run or bundle")
        onAccepted: {
            root.folderSelectionPath = selectedFolder.toString();
            root.folderSelectionAccepted = true;
            Qt.callLater(root.completeFolderSelection);
        }
        onRejected: {
            root.folderSelectionAccepted = false;
            root.folderSelectionPath = "";
        }
        onVisibleChanged: root.completeFolderSelection()
    }
}
