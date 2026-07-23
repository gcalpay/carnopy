import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Carnopy

Dialog {
    id: root

    property alias childName: childNameField.text
    property alias expertMode: expertModeCheck.checked
    property alias expertPath: expertPathField.text
    property alias parentPath: parentPathField.text

    signal browseParentRequested
    signal createRequested(string path, string childName, bool expertMode)

    function resetFields() {
        childNameField.clear();
        expertModeCheck.checked = false;
        expertPathField.clear();
    }

    anchors.centerIn: Overlay.overlay
    closePolicy: Popup.CloseOnEscape
    modal: true
    padding: 20
    standardButtons: Dialog.NoButton
    title: qsTr("Create Workspace")
    width: Math.min(520, Overlay.overlay.width - 32)

    background: Rectangle {
        border.color: Theme.borderStrong
        border.width: 1
        color: Theme.surface
        radius: Theme.radiusLarge
    }

    contentItem: ColumnLayout {
        spacing: Theme.spacingMedium

        Label {
            Layout.fillWidth: true
            color: Theme.textMuted
            font.family: Theme.sansFamily
            font.pixelSize: 12
            text: qsTr(
                      "Choose an existing parent folder and enter one new folder name. Carnopy will refuse an existing target.")
            wrapMode: Text.Wrap
        }

        Label {
            color: Theme.text
            font.family: Theme.sansFamily
            font.pixelSize: 12
            text: qsTr("Parent folder")
            visible: !root.expertMode
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.spacingSmall
            visible: !root.expertMode

            TextField {
                id: parentPathField

                Accessible.name: qsTr("Workspace parent folder")
                Layout.fillWidth: true
                font.family: Theme.monoFamily
                objectName: "workspaceParentPathField"
                placeholderText: qsTr("Choose an existing folder")
                readOnly: true
            }

            AppButton {
                iconName: "search"
                objectName: "workspaceParentBrowseButton"
                onClicked: root.browseParentRequested()
                text: qsTr("Browse")
            }
        }

        Label {
            color: Theme.text
            font.family: Theme.sansFamily
            font.pixelSize: 12
            text: qsTr("New workspace folder name")
            visible: !root.expertMode
        }

        TextField {
            id: childNameField

            Accessible.name: qsTr("New workspace folder name")
            Layout.fillWidth: true
            font.family: Theme.sansFamily
            objectName: "workspaceChildNameField"
            placeholderText: qsTr("my-carnopy-workspace")
            visible: !root.expertMode
        }

        CheckBox {
            id: expertModeCheck

            Accessible.name: text
            activeFocusOnTab: true
            font.family: Theme.sansFamily
            objectName: "workspaceExpertModeCheck"
            text: qsTr("Enter a complete non-existing path instead")
        }

        TextField {
            id: expertPathField

            Accessible.name: qsTr("Complete new workspace path")
            Layout.fillWidth: true
            font.family: Theme.monoFamily
            objectName: "workspaceExpertPathField"
            placeholderText: qsTr("/path/to/new-workspace")
            visible: root.expertMode
        }

        RowLayout {
            Layout.alignment: Qt.AlignRight
            spacing: Theme.spacingSmall

            AppButton {
                onClicked: root.reject()
                text: qsTr("Cancel")
            }

            AppButton {
                enabled: root.expertMode ? root.expertPath.trim().length > 0 :
                                           root.parentPath.length > 0 && root.childName.trim(
                                               ).length > 0
                objectName: "workspaceCreateConfirmButton"
                onClicked: {
                    root.createRequested(root.expertMode ? root.expertPath : root.parentPath,
                                         root.childName, root.expertMode);
                    root.close();
                }
                text: qsTr("Create")
                tone: "primary"
            }
        }
    }
}
