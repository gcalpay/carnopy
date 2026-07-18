pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Carnopy

Card {
    id: root

    required property var draft
    property string unitRejectionMessage: ""

    signal kindChangeRequested(var draft, string kind)
    signal textChangeRequested(var draft, string field, string text)
    signal unitChangeRequested(var draft, string unit)

    function fieldVisible(name) {
        return root.draft.activeFields.indexOf(name) >= 0;
    }

    function indexForValue(combo, value) {
        for (let row = 0; row < combo.count; ++row) {
            if (String(combo.valueAt(row)) === value)
                return row;
        }
        return -1;
    }

    function syncFromDraft() {
        kindChoice.currentIndex = indexForValue(kindChoice, root.draft.kind);
        unitChoice.currentIndex = indexForValue(unitChoice, root.draft.unit);
        valuesField.text = root.draft.text("values");
        startField.text = root.draft.text("start");
        stopField.text = root.draft.text("stop");
        stepField.text = root.draft.text("step");
        startExponentField.text = root.draft.text("start_exp");
        stopExponentField.text = root.draft.text("stop_exp");
        countField.text = root.draft.text("num");
        baseField.text = root.draft.text("base");
    }

    objectName: "samplerEditor-" + String(draft.axis)
    subtitle: qsTr(
                  "Declared values remain in the selected unit. Exact canonical identity is required for a unit-only change.")
    title: String(draft.axis).replace(/_/g, " ")

    Connections {
        function onAvailableUnitsChanged() {
            root.syncFromDraft();
        }

        function onFieldsChanged() {
            root.syncFromDraft();
        }

        function onKindChanged() {
            root.syncFromDraft();
        }

        function onUnitChangeRejected(field, message) {
            root.unitRejectionMessage = message;
            unitChoice.forceActiveFocus();
        }

        function onUnitChanged() {
            root.unitRejectionMessage = "";
            root.syncFromDraft();
        }

        target: root.draft
    }

    Component.onCompleted: syncFromDraft()

    GridLayout {
        Layout.fillWidth: true
        columnSpacing: Theme.spacingMedium
        columns: width >= 620 ? 2 : 1
        rowSpacing: Theme.spacingSmall

        ColumnLayout {
            Layout.fillWidth: true
            spacing: Theme.spacingTiny

            Label {
                color: Theme.textMuted
                font.family: Theme.sansFamily
                font.pixelSize: 11
                text: qsTr("Sampler")
            }

            AppComboBox {
                id: kindChoice

                Accessible.name: root.draft.axis + qsTr(" sampler kind")
                Layout.fillWidth: true
                model: root.draft.availableKinds
                objectName: "samplerKind-" + String(root.draft.axis)
                onActivated: root.kindChangeRequested(root.draft, String(currentValue))
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            spacing: Theme.spacingTiny

            Label {
                color: Theme.textMuted
                font.family: Theme.sansFamily
                font.pixelSize: 11
                text: qsTr("Unit")
            }

            AppComboBox {
                id: unitChoice

                Accessible.name: root.draft.axis + qsTr(" unit")
                Layout.fillWidth: true
                model: root.draft.availableUnits
                objectName: "samplerUnit-" + String(root.draft.axis)
                onActivated: root.unitChangeRequested(root.draft, String(currentValue))
            }
        }
    }

    TextField {
        id: valuesField

        Accessible.name: root.draft.axis + qsTr(" explicit values")
        Layout.fillWidth: true
        objectName: "samplerField-" + String(root.draft.axis) + "-values"
        onTextEdited: root.textChangeRequested(root.draft, "values", text)
        placeholderText: qsTr("Comma-separated values")
        visible: root.fieldVisible("values")
    }

    GridLayout {
        Layout.fillWidth: true
        columnSpacing: Theme.spacingMedium
        columns: width >= 620 ? 2 : 1
        rowSpacing: Theme.spacingSmall
        visible: root.draft.kind !== "explicit"

        TextField {
            id: startField

            Accessible.name: root.draft.axis + qsTr(" start")
            Layout.fillWidth: true
            objectName: "samplerField-" + String(root.draft.axis) + "-start"
            onTextEdited: root.textChangeRequested(root.draft, "start", text)
            placeholderText: qsTr("Start")
            visible: root.fieldVisible("start")
        }

        TextField {
            id: stopField

            Accessible.name: root.draft.axis + qsTr(" stop")
            Layout.fillWidth: true
            objectName: "samplerField-" + String(root.draft.axis) + "-stop"
            onTextEdited: root.textChangeRequested(root.draft, "stop", text)
            placeholderText: qsTr("Stop")
            visible: root.fieldVisible("stop")
        }

        TextField {
            id: stepField

            Accessible.name: root.draft.axis + qsTr(" step")
            Layout.fillWidth: true
            objectName: "samplerField-" + String(root.draft.axis) + "-step"
            onTextEdited: root.textChangeRequested(root.draft, "step", text)
            placeholderText: qsTr("Step")
            visible: root.fieldVisible("step")
        }

        TextField {
            id: startExponentField

            Accessible.name: root.draft.axis + qsTr(" start exponent")
            Layout.fillWidth: true
            objectName: "samplerField-" + String(root.draft.axis) + "-start_exp"
            onTextEdited: root.textChangeRequested(root.draft, "start_exp", text)
            placeholderText: qsTr("Start exponent")
            visible: root.fieldVisible("start_exp")
        }

        TextField {
            id: stopExponentField

            Accessible.name: root.draft.axis + qsTr(" stop exponent")
            Layout.fillWidth: true
            objectName: "samplerField-" + String(root.draft.axis) + "-stop_exp"
            onTextEdited: root.textChangeRequested(root.draft, "stop_exp", text)
            placeholderText: qsTr("Stop exponent")
            visible: root.fieldVisible("stop_exp")
        }

        TextField {
            id: countField

            Accessible.name: root.draft.axis + qsTr(" number of samples")
            Layout.fillWidth: true
            inputMethodHints: Qt.ImhDigitsOnly
            objectName: "samplerField-" + String(root.draft.axis) + "-num"
            onTextEdited: root.textChangeRequested(root.draft, "num", text)
            placeholderText: qsTr("Number of samples")
            visible: root.fieldVisible("num")
        }

        TextField {
            id: baseField

            Accessible.name: root.draft.axis + qsTr(" logarithm base")
            Layout.fillWidth: true
            objectName: "samplerField-" + String(root.draft.axis) + "-base"
            onTextEdited: root.textChangeRequested(root.draft, "base", text)
            placeholderText: qsTr("Base")
            visible: root.fieldVisible("base")
        }
    }

    ValidationIssue {
        Layout.fillWidth: true
        field: root.unitRejectionMessage.length > 0 ? "dataset.grid." + root.draft.axis + ".unit" :
                                                      root.draft.firstInvalidField
        issue: root.unitRejectionMessage.length > 0 ? root.unitRejectionMessage : root.draft.issue
    }
}
