pragma Singleton

import QtQuick

QtObject {
    property bool dark: false
    property bool reducedMotion: false

    readonly property color canvas: dark ? "#091522" : "#f3f6f8"
    readonly property color surface: dark ? "#102235" : "#ffffff"
    readonly property color surfaceRaised: dark ? "#162b40" : "#f8fafb"
    readonly property color surfaceMuted: dark ? "#1a3045" : "#edf2f5"
    readonly property color border: dark ? "#294158" : "#d8e1e8"
    readonly property color borderStrong: dark ? "#3b5870" : "#b9c7d2"
    readonly property color text: dark ? "#f0f5f8" : "#10283b"
    readonly property color textMuted: dark ? "#a9bac7" : "#5b7080"
    readonly property color textSubtle: dark ? "#7f94a5" : "#7a8d9c"

    readonly property color navigation: "#071b30"
    readonly property color navigationRaised: "#0d2945"
    readonly property color navigationText: "#edf6fb"
    readonly property color navigationMuted: "#9fb3c4"
    readonly property color navigationSelected: "#0d624a"

    readonly property color primary: "#12825b"
    readonly property color primaryHover: "#0f7451"
    readonly property color primaryPressed: "#0b6245"
    readonly property color primarySoft: dark ? "#123d35" : "#e1f3eb"
    readonly property color information: dark ? "#70a7f5" : "#2469c7"
    readonly property color informationSoft: dark ? "#153657" : "#e7f0fd"
    readonly property color warning: dark ? "#f0bd61" : "#9b6508"
    readonly property color warningSoft: dark ? "#473719" : "#fff3d7"
    readonly property color danger: dark ? "#ff8e8e" : "#b33131"
    readonly property color dangerSoft: dark ? "#4b2428" : "#fdeaea"
    readonly property color success: dark ? "#71d6a4" : "#087a50"

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

    function iconSource(name) {
        return name.length === 0 ? "" : Qt.resolvedUrl("../../resources/icons/" + name + ".svg");
    }

    function brandingSource() {
        return Qt.resolvedUrl("../../resources/branding/carnopy-mark.png");
    }
}
