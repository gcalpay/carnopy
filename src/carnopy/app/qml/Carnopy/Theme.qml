pragma Singleton

import QtQuick

QtObject {
    property string mode: "dark"
    property bool reducedMotion: false

    readonly property color canvas: pick("#f3f5f4", "#e7bd69", "#0f0f0f")
    readonly property color surface: pick("#ffffff", "#f6d994", "#141715")
    readonly property color surfaceRaised: pick("#f8faf9", "#f0cc7f", "#191d1a")
    readonly property color surfaceMuted: pick("#e9efeb", "#ddb15f", "#202620")
    readonly property color border: pick("#d3dcd6", "#b9802f", "#303932")
    readonly property color borderStrong: pick("#abb9b0", "#8e5e20", "#47534b")
    readonly property color text: pick("#17211b", "#38230d", "#f1f4f2")
    readonly property color textMuted: pick("#5c6a61", "#704619", "#aab5ae")
    readonly property color textSubtle: pick("#7b887f", "#865a24", "#7f8b83")

    readonly property color navigation: pick("#102019", "#4b2f11", "#0f0f0f")
    readonly property color navigationRaised: pick("#183025", "#654116", "#191d1a")
    readonly property color navigationText: "#f1f4f2"
    readonly property color navigationMuted: pick("#9fb3a6", "#e5c487", "#aab5ae")
    readonly property color navigationSelected: pick("#0d6d49", "#176143", "#123d2c")

    readonly property color primary: pick("#087a50", "#0b7650", "#159660")
    readonly property color primaryHover: pick("#066c46", "#086844", "#1cad70")
    readonly property color primaryPressed: pick("#055c3c", "#07583a", "#128052")
    readonly property color primarySoft: pick("#e1f3eb", "#b9cf91", "#123d2c")
    readonly property color information: pick("#2469c7", "#486f91", "#73a9f5")
    readonly property color informationSoft: pick("#e7f0fd", "#d0c18f", "#172d43")
    readonly property color warning: pick("#9b6508", "#ad6500", "#f2b84b")
    readonly property color warningSoft: pick("#fff3d7", "#f3c86e", "#423319")
    readonly property color danger: pick("#b33131", "#ad4033", "#ff7777")
    readonly property color dangerSoft: pick("#fdeaea", "#eab77d", "#432326")
    readonly property color success: pick("#087a50", "#0b7650", "#39d47d")
    readonly property color highlightedText: "#ffffff"

    // The workbench uses this small semantic role set. The legacy names above
    // remain aliases for Controls and pre-Stage-2 components.
    readonly property color divider: border
    readonly property color hover: surfaceMuted
    readonly property color focus: primary
    readonly property color amber: warning
    readonly property color red: danger

    readonly property int radiusSmall: 3
    readonly property int radiusMedium: 5
    readonly property int radiusLarge: 7
    readonly property int spacingTiny: 4
    readonly property int spacingSmall: 8
    readonly property int spacingMedium: 12
    readonly property int spacingLarge: 20
    readonly property int spacingXLarge: 28

    readonly property int durationFast: reducedMotion ? 0 : 140
    readonly property int durationStandard: reducedMotion ? 0 : 200
    readonly property int durationEmphasis: reducedMotion ? 0 : 200

    readonly property string sansFamily: "IBM Plex Sans"
    readonly property string monoFamily: "IBM Plex Mono"

    function pick(light, warm, dark) {
        if (mode === "light")
            return light;
        if (mode === "warm")
            return warm;
        return dark;
    }

    function iconSource(name) {
        return name.length === 0 ? "" : Qt.resolvedUrl("../../resources/icons/" + name + ".svg");
    }

    function brandingSource() {
        return Qt.resolvedUrl("../../resources/branding/carnopy-mark.png");
    }
}
