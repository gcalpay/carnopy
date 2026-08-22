pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Carnopy

Card {
    id: root

    required property var draft
    required property int index
    property string attentionField: ""
    property int attentionSerial: 0
    property string unitRejectionMessage: ""

    signal kindChangeRequested(var draft, string kind)
    signal textChangeRequested(var draft, string field, string text)
    signal unitChangeRequested(var draft, string unit)

    function fieldVisible(name) {
        return root.draft.activeFields.indexOf(name) >= 0;
    }

    function axisLabel(axis) {
        if (axis === "vapor_mass_fraction")
            return qsTr("Vapor mass fraction sampler");
        if (axis === "temperature")
            return qsTr("Temperature sampler");
        if (axis === "pressure")
            return qsTr("Pressure sampler");
        return String(axis).replace(/_/g, " ") + qsTr(" sampler");
    }

    function indexForValue(combo, value) {
        for (let row = 0; row < combo.count; ++row) {
            if (String(combo.valueAt(row)) === value)
                return row;
        }
        return -1;
    }

    function focusField(field) {
        let target = unitChoice;
        if (field === "kind")
            target = kindChoice;
        else if (field === "values")
            target = valuesField;
        else if (field === "start")
            target = startField;
        else if (field === "stop")
            target = stopField;
        else if (field === "step")
            target = stepField;
        else if (field === "start_exp")
            target = startExponentField;
        else if (field === "stop_exp")
            target = stopExponentField;
        else if (field === "num")
            target = countField;
        else if (field === "base")
            target = baseField;
        target.forceActiveFocus();
        return target;
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

    onAttentionSerialChanged: {
        if (root.attentionField.length > 0)
        Qt.callLater(() => root.focusField(root.attentionField));
    }

    objectName: "samplerEditor-" + String(draft.axis)
    meta: root.draft.valid ? qsTr("%1 points").arg(root.draft.sampleCount) : qsTr("Unavailable")
    metaColor: root.draft.valid ? Theme.success : Theme.red
    metaObjectName: "samplerPointCount-" + String(root.draft.axis)
    subtitle: qsTr(
                  "Declared values remain in the selected unit. Exact canonical identity is required for a unit-only change.")
    title: root.axisLabel(draft.axis)

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

    ColumnLayout {
        Layout.fillWidth: true
        visible: root.fieldVisible("values")

        Label {
            color: Theme.textMuted
            font.family: Theme.sansFamily
            font.pixelSize: 11
            text: qsTr("Values")
        }

        TextField {
            id: valuesField

            Accessible.name: root.draft.axis + qsTr(" explicit values")
            Layout.fillWidth: true
            objectName: "samplerField-" + String(root.draft.axis) + "-values"
            onTextEdited: root.textChangeRequested(root.draft, "values", text)
            placeholderText: qsTr("Comma-separated values")
        }
    }

    GridLayout {
        Layout.fillWidth: true
        columnSpacing: Theme.spacingMedium
        columns: width >= 620 ? 2 : 1
        rowSpacing: Theme.spacingSmall
        visible: root.draft.kind !== "explicit"

        ColumnLayout {
            Layout.fillWidth: true
            visible: root.fieldVisible("start")

            Label {
                color: Theme.textMuted
                font.family: Theme.sansFamily
                font.pixelSize: 11
                text: qsTr("Min")
            }

            TextField {
                id: startField

                Accessible.name: root.draft.axis + qsTr(" start")
                Layout.fillWidth: true
                objectName: "samplerField-" + String(root.draft.axis) + "-start"
                onTextEdited: root.textChangeRequested(root.draft, "start", text)
                placeholderText: qsTr("Start")
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            visible: root.fieldVisible("stop")

            Label {
                color: Theme.textMuted
                font.family: Theme.sansFamily
                font.pixelSize: 11
                text: qsTr("Max")
            }

            TextField {
                id: stopField

                Accessible.name: root.draft.axis + qsTr(" stop")
                Layout.fillWidth: true
                objectName: "samplerField-" + String(root.draft.axis) + "-stop"
                onTextEdited: root.textChangeRequested(root.draft, "stop", text)
                placeholderText: qsTr("Stop")
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            visible: root.fieldVisible("step")

            Label {
                color: Theme.textMuted
                font.family: Theme.sansFamily
                font.pixelSize: 11
                text: qsTr("Step size")
            }

            TextField {
                id: stepField

                Accessible.name: root.draft.axis + qsTr(" step size")
                Layout.fillWidth: true
                objectName: "samplerField-" + String(root.draft.axis) + "-step"
                onTextEdited: root.textChangeRequested(root.draft, "step", text)
                placeholderText: qsTr("Step size")
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            visible: root.fieldVisible("start_exp")

            Label {
                color: Theme.textMuted
                font.family: Theme.sansFamily
                font.pixelSize: 11
                text: qsTr("Start exponent")
            }

            TextField {
                id: startExponentField

                Accessible.name: root.draft.axis + qsTr(" start exponent")
                Layout.fillWidth: true
                objectName: "samplerField-" + String(root.draft.axis) + "-start_exp"
                onTextEdited: root.textChangeRequested(root.draft, "start_exp", text)
                placeholderText: qsTr("Start exponent")
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            visible: root.fieldVisible("stop_exp")

            Label {
                color: Theme.textMuted
                font.family: Theme.sansFamily
                font.pixelSize: 11
                text: qsTr("Stop exponent")
            }

            TextField {
                id: stopExponentField

                Accessible.name: root.draft.axis + qsTr(" stop exponent")
                Layout.fillWidth: true
                objectName: "samplerField-" + String(root.draft.axis) + "-stop_exp"
                onTextEdited: root.textChangeRequested(root.draft, "stop_exp", text)
                placeholderText: qsTr("Stop exponent")
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            visible: root.fieldVisible("num")

            Label {
                color: Theme.textMuted
                font.family: Theme.sansFamily
                font.pixelSize: 11
                text: qsTr("Points")
            }

            TextField {
                id: countField

                Accessible.name: root.draft.axis + qsTr(" number of samples")
                Layout.fillWidth: true
                inputMethodHints: Qt.ImhDigitsOnly
                objectName: "samplerField-" + String(root.draft.axis) + "-num"
                onTextEdited: root.textChangeRequested(root.draft, "num", text)
                placeholderText: qsTr("Number of samples")
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            visible: root.fieldVisible("base")

            Label {
                color: Theme.textMuted
                font.family: Theme.sansFamily
                font.pixelSize: 11
                text: qsTr("Base")
            }

            TextField {
                id: baseField

                Accessible.name: root.draft.axis + qsTr(" logarithm base")
                Layout.fillWidth: true
                objectName: "samplerField-" + String(root.draft.axis) + "-base"
                onTextEdited: root.textChangeRequested(root.draft, "base", text)
                placeholderText: qsTr("Base")
            }
        }
    }

    Label {
        Accessible.name: root.draft.axis + qsTr(" derived spacing and interval count")
        Layout.fillWidth: true
        color: Theme.success
        font.family: Theme.monoFamily
        font.pixelSize: 11
        objectName: "samplerDerived-" + String(root.draft.axis)
        text: qsTr("Spacing %1 %2 · %3 intervals").arg(root.draft.kind === "linspace"
                                                       ? root.draft.spacingText :
                                                         stepField.text).arg(root.draft.unit).arg(
                  root.draft.intervalCount)
        visible: root.draft.valid && (root.draft.kind === "linspace" || root.draft.kind
                                      === "stepspace")
        wrapMode: Text.Wrap
    }

    ValidationIssue {
        Layout.fillWidth: true
        field: root.unitRejectionMessage.length > 0 ? "dataset.grid." + root.draft.axis + ".unit" :
                                                      root.draft.firstInvalidField
        issue: root.unitRejectionMessage.length > 0 ? root.unitRejectionMessage : root.draft.issue
    }
}
