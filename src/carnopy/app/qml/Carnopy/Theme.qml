pragma Singleton

import QtQuick

QtObject {
    property string mode: "dark"
    property bool reducedMotion: false

    readonly property color canvas: pick("#f3f5f4", "#f2dfbd", "#0f0f0f")
    readonly property color surface: pick("#ffffff", "#fff2d9", "#141715")
    readonly property color surfaceRaised: pick("#f8faf9", "#f9e8ca", "#191d1a")
    readonly property color surfaceMuted: pick("#e9efeb", "#ead4ae", "#202620")
    readonly property color border: pick("#d3dcd6", "#d6b67e", "#303932")
    readonly property color borderStrong: pick("#abb9b0", "#b48d50", "#47534b")
    readonly property color text: pick("#17211b", "#332518", "#f1f4f2")
    readonly property color textMuted: pick("#5c6a61", "#73583c", "#aab5ae")
    readonly property color textSubtle: pick("#7b887f", "#795a3d", "#7f8b83")

    readonly property color navigation: pick("#102019", "#1d160f", "#0f0f0f")
    readonly property color navigationRaised: pick("#183025", "#2d2116", "#191d1a")
    readonly property color navigationText: "#f1f4f2"
    readonly property color navigationMuted: pick("#9fb3a6", "#c6a77b", "#aab5ae")
    readonly property color navigationSelected: pick("#0d6d49", "#134d36", "#123d2c")

    readonly property color primary: pick("#087a50", "#0b7650", "#159660")
    readonly property color primaryHover: pick("#066c46", "#086844", "#1cad70")
    readonly property color primaryPressed: pick("#055c3c", "#07583a", "#128052")
    readonly property color primarySoft: pick("#e1f3eb", "#d9eadc", "#123d2c")
    readonly property color information: pick("#2469c7", "#486f91", "#73a9f5")
    readonly property color informationSoft: pick("#e7f0fd", "#dce7ec", "#172d43")
    readonly property color warning: pick("#9b6508", "#ad6500", "#f2b84b")
    readonly property color warningSoft: pick("#fff3d7", "#ffe0a6", "#423319")
    readonly property color danger: pick("#b33131", "#ad4033", "#ff7777")
    readonly property color dangerSoft: pick("#fdeaea", "#f5d5c9", "#432326")
    readonly property color success: pick("#087a50", "#0b7650", "#39d47d")
    readonly property color highlightedText: "#ffffff"

    readonly property int radiusSmall: 4
    readonly property int radiusMedium: 7
    readonly property int radiusLarge: 10
    readonly property int spacingTiny: 4
    readonly property int spacingSmall: 8
    readonly property int spacingMedium: 12
    readonly property int spacingLarge: 20
    readonly property int spacingXLarge: 28

    readonly property int durationFast: reducedMotion ? 0 : 110
    readonly property int durationStandard: reducedMotion ? 0 : 180
    readonly property int durationEmphasis: reducedMotion ? 0 : 240

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
