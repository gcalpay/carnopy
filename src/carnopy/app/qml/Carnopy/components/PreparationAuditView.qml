pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Carnopy

Item {
    id: root

    required property var audit
    property int selectedSection: 0
    readonly property int expectedColumns: width >= 960 ? 2 : 1

    function displayStatus(value) {
        if (value === undefined || value === null || String(value).length === 0)
            return qsTr("Not recorded");
        const normalized = String(value).replace(/_/g, " ");
        return normalized.charAt(0).toUpperCase() + normalized.slice(1);
    }

    function formatNumber(value) {
        const number = Number(value);
        if (!Number.isFinite(number))
            return String(value);
        if (number === 0)
            return "0";
        if (Math.abs(number) >= 100000 || Math.abs(number) < 0.001)
            return number.toExponential(4);
        return Number(number.toPrecision(6)).toString();
    }

    function formatOptional(value, available) {
        return available ? formatNumber(value) : qsTr("Not recorded");
    }

    function formatFraction(value, available) {
        return available ? qsTr("%1%").arg(formatNumber(Number(value) * 100)) : qsTr(
                               "Not recorded");
    }

    function formatBoolean(value, available) {
        if (!available)
            return qsTr("Not recorded");
        return value ? qsTr("Yes") : qsTr("No");
    }

    function scenarioText(value) {
        return String(value).length > 0 ? String(value) : qsTr("All scenarios");
    }

    function listText(value) {
        if (value === undefined || value === null || value.length === 0)
            return qsTr("None recorded");
        return value.join(", ");
    }

    function qualityTone(status) {
        if (status === "completed")
            return "success";
        if (status === "completed_with_failures" || status === "unavailable")
            return "warning";
        if (status === "failed")
            return "danger";
        return "neutral";
    }

    implicitHeight: auditColumn.implicitHeight
    implicitWidth: 720
    objectName: "preparationAuditView"

    component EvidenceRow: Rectangle {
        id: evidenceRow

        required property string detail
        required property string heading
        property string metadata: ""
        property string warning: ""

        Accessible.description: detail + (metadata.length > 0 ? ". " + metadata : "") + (
                                    warning.length > 0 ? ". " + warning : "")
        Accessible.name: heading
        border.color: Theme.divider
        border.width: 1
        color: Theme.surfaceRaised
        implicitHeight: evidenceRowColumn.implicitHeight + 20
        radius: Theme.radiusSmall
        width: ListView.view ? ListView.view.width : (parent ? parent.width : 0)

        ColumnLayout {
            id: evidenceRowColumn

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
                text: evidenceRow.heading
                wrapMode: Text.Wrap
            }

            Label {
                Layout.fillWidth: true
                color: Theme.textMuted
                font.family: Theme.monoFamily
                font.pixelSize: 10
                text: evidenceRow.detail
                wrapMode: Text.Wrap
            }

            Label {
                Layout.fillWidth: true
                color: Theme.textMuted
                font.family: Theme.sansFamily
                font.pixelSize: 10
                text: evidenceRow.metadata
                visible: text.length > 0
                wrapMode: Text.Wrap
            }

            Label {
                Layout.fillWidth: true
                color: Theme.warning
                font.family: Theme.sansFamily
                font.pixelSize: 10
                text: evidenceRow.warning
                visible: text.length > 0
                wrapMode: Text.Wrap
            }
        }
    }

    component EvidenceCard: Card {
        id: evidenceCard

        required property string accessibleName
        required property var evidenceModel
        required property string listObjectName
        required property Component rowDelegate
        property string emptyText: qsTr("No findings were recorded.")
        property string unavailableText: qsTr("This evidence was not recorded for the source.")

        Layout.fillWidth: true
        meta: evidenceModel.available ? qsTr("%1 row(s)").arg(evidenceModel.count) : qsTr(
                                            "Unavailable")

        ListView {
            id: evidenceList

            Accessible.name: evidenceCard.accessibleName
            Layout.fillWidth: true
            Layout.preferredHeight: Math.max(0, Math.min(280, contentHeight))
            activeFocusOnTab: count > 0
            boundsBehavior: Flickable.StopAtBounds
            clip: true
            delegate: evidenceCard.rowDelegate
            interactive: contentHeight > height
            model: evidenceCard.evidenceModel
            objectName: evidenceCard.listObjectName
            pixelAligned: true
            reuseItems: true
            spacing: Theme.spacingTiny
            visible: evidenceCard.evidenceModel.available && count > 0

            ScrollBar.vertical: ScrollBar {
                policy: ScrollBar.AsNeeded
            }
        }

        Label {
            Layout.fillWidth: true
            color: Theme.textMuted
            font.family: Theme.sansFamily
            font.pixelSize: 11
            text: evidenceCard.evidenceModel.available ? evidenceCard.emptyText :
                                                         evidenceCard.unavailableText
            visible: !evidenceCard.evidenceModel.available || evidenceCard.evidenceModel.count === 0
            wrapMode: Text.Wrap
        }
    }

    ColumnLayout {
        id: auditColumn

        spacing: Theme.spacingMedium
        width: parent.width

        Card {
            Layout.fillWidth: true
            objectName: "preparationAuditSummaryCard"
            subtitle: root.audit.available ? qsTr(
                                                 "Verified, finalized Preparation evidence is projected through fixed typed models. Counts and values retain the source revision accepted by Inspect.") :
                                             qsTr("This source has no current typed Preparation audit projection. Legacy bundles may not contain these diagnostics.")
            title: qsTr("Preparation audit")

            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.spacingSmall

                StatusBadge {
                    label: root.audit.available ? root.displayStatus(root.audit.qualityStatus) :
                                                  qsTr("Unavailable")
                    objectName: "preparationAuditStatus"
                    tone: root.audit.available ? root.qualityTone(root.audit.qualityStatus) :
                                                 "neutral"
                }

                Item {
                    Layout.fillWidth: true
                }

                Label {
                    color: Theme.textMuted
                    font.family: Theme.sansFamily
                    font.pixelSize: 11
                    text: qsTr("Finalized evidence")
                    visible: root.audit.available
                }
            }

            Repeater {
                model: root.audit.qualityOverview

                delegate: EvidenceRow {
                    required property string baselineStatus
                    required property string duplicateStatus
                    required property int eligibleRowCount
                    required property bool eligibleRowCountAvailable
                    required property int errorCount
                    required property int excludedRowCount
                    required property bool excludedRowCountAvailable
                    required property bool flagCountMatches
                    required property string gridStatus
                    required property int inspectedFlagCount
                    required property bool inspectedFlagCountAvailable
                    required property string matrixStatus
                    required property int recordedFlagCount
                    required property bool recordedFlagCountAvailable
                    required property string scenarioStatus

                    Layout.fillWidth: true
                    detail: qsTr("Eligible %1 · excluded %2 · quality flags %3 / %4").arg(
                                root.formatOptional(eligibleRowCount,
                                                    eligibleRowCountAvailable)).arg(
                                root.formatOptional(excludedRowCount,
                                                    excludedRowCountAvailable)).arg(
                                root.formatOptional(inspectedFlagCount,
                                                    inspectedFlagCountAvailable)).arg(
                                root.formatOptional(recordedFlagCount, recordedFlagCountAvailable))
                    heading: qsTr("Finalized row and quality summary")
                    metadata: qsTr(
                                  "Scenarios: %1 · matrix: %2 · baselines: %3 · duplicates: %4 · grid: %5").arg(
                                  root.displayStatus(scenarioStatus)).arg(root.displayStatus(
                                                                              matrixStatus)).arg(
                                  root.displayStatus(baselineStatus)).arg(root.displayStatus(
                                                                              duplicateStatus)).arg(
                                  root.displayStatus(gridStatus))
                    warning: errorCount > 0 ? qsTr("%1 audit issue(s) were recorded.").arg(
                                                  errorCount) : ((recordedFlagCountAvailable
                                                                  && inspectedFlagCountAvailable &&
                                                                  !flagCountMatches) ? qsTr(
                                                                                           "Recorded and inspected quality-flag counts differ.") :
                                                                                       "")
                }
            }
        }

        TabBar {
            id: auditSections

            Layout.fillWidth: true
            currentIndex: root.selectedSection
            objectName: "preparationAuditSections"
            onCurrentIndexChanged: root.selectedSection = currentIndex

            TabButton {
                Accessible.name: qsTr("Preparation quality and scenario audit")
                objectName: "preparationAuditOverviewTab"
                text: qsTr("Quality and scenarios")
            }

            TabButton {
                Accessible.name: qsTr("Preparation matrix audit")
                objectName: "preparationAuditMatrixTab"
                text: qsTr("Matrix")
            }

            TabButton {
                Accessible.name: qsTr("Preparation baseline audit")
                objectName: "preparationAuditBaselineTab"
                text: qsTr("Baselines")
            }
        }

        StackLayout {
            Layout.fillWidth: true
            currentIndex: root.selectedSection
            objectName: "preparationAuditSectionStack"

            ResponsiveCardGrid {
                Layout.fillWidth: true
                maximumColumns: root.expectedColumns
                minimumCardWidth: 360
                objectName: "preparationAuditOverviewGrid"
                uniformHeights: false

                EvidenceCard {
                    accessibleName: qsTr("Preparation scenarios")
                    emptyText: qsTr("No Preparation scenarios were recorded.")
                    evidenceModel: root.audit.scenariosModel
                    listObjectName: "preparationAuditScenariosList"
                    subtitle: qsTr(
                                  "Committed scenarios and their finalized row, partition, transformation, and leakage-evidence counts.")
                    title: qsTr("Scenarios")
                    rowDelegate: Component {
                        EvidenceRow {
                            required property string kind
                            required property bool leakageAvailable
                            required property string name
                            required property int partitionCount
                            required property int rowCount
                            required property int transformationCount

                            detail: qsTr(
                                        "%1 · %2 row(s) · %3 partition(s) · %4 transformation(s)").arg(
                                        root.displayStatus(kind)).arg(rowCount).arg(
                                        partitionCount).arg(transformationCount)
                            heading: name
                            metadata: leakageAvailable ? qsTr("State-leakage evidence recorded") :
                                                         qsTr("State-leakage evidence unavailable")
                        }
                    }
                }

                EvidenceCard {
                    accessibleName: qsTr("Preparation partitions")
                    emptyText: qsTr("No finalized partition counts were recorded.")
                    evidenceModel: root.audit.partitionsModel
                    listObjectName: "preparationAuditPartitionsList"
                    subtitle: qsTr(
                                  "Finalized row counts, retained in scenario and partition order.")
                    title: qsTr("Partitions")
                    rowDelegate: Component {
                        EvidenceRow {
                            required property string partition
                            required property int rowCount
                            required property string scenario

                            detail: qsTr("%1 row(s)").arg(rowCount)
                            heading: qsTr("%1 · %2").arg(scenario).arg(partition)
                        }
                    }
                }

                EvidenceCard {
                    accessibleName: qsTr("Preparation state leakage checks")
                    emptyText: qsTr("No state-leakage checks were recorded.")
                    evidenceModel: root.audit.leakageAudits
                    listObjectName: "preparationAuditLeakageList"
                    subtitle: qsTr(
                                  "Duplicate states are counted independently from states crossing finalized partition boundaries.")
                    title: qsTr("State leakage")
                    rowDelegate: Component {
                        EvidenceRow {
                            required property int crossPartitionGroupCount
                            required property int duplicateStateGroupCount
                            required property string identityColumn
                            required property string scenario

                            detail: qsTr("Duplicate groups %1 · cross-partition groups %2").arg(
                                        duplicateStateGroupCount).arg(crossPartitionGroupCount)
                            heading: scenario
                            metadata: qsTr("Identity: %1").arg(identityColumn)
                            warning: crossPartitionGroupCount > 0 ? qsTr(
                                                                        "This scenario contains states shared across partitions.") :
                                                                    ""
                        }
                    }
                }

                EvidenceCard {
                    accessibleName: qsTr("Preparation duplicate state checks")
                    emptyText: qsTr("No duplicate-state check was recorded.")
                    evidenceModel: root.audit.duplicateStateChecks
                    listObjectName: "preparationAuditDuplicateStatesList"
                    subtitle: qsTr(
                                  "Candidate duplicate source states and conflicting target groups.")
                    title: qsTr("Duplicate states")
                    rowDelegate: Component {
                        EvidenceRow {
                            required property bool countsAvailable
                            required property int conflictingTargetGroupCount
                            required property int duplicateGroupCount
                            required property int duplicateRowCount
                            required property var groupColumns
                            required property string identityColumn
                            required property string status

                            detail: countsAvailable ? qsTr(
                                                          "Groups %1 · rows %2 · target conflicts %3").arg(
                                                          duplicateGroupCount).arg(
                                                          duplicateRowCount).arg(
                                                          conflictingTargetGroupCount) : qsTr(
                                                          "Counts were not available for this check.")
                            heading: root.displayStatus(status)
                            metadata: qsTr("Grouped by %1%2").arg(root.listText(groupColumns)).arg(
                                          identityColumn.length > 0 ? qsTr(" · identity %1").arg(
                                                                          identityColumn) : "")
                            warning: countsAvailable && conflictingTargetGroupCount > 0 ? qsTr(
                                                                                              "Conflicting targets were recorded for duplicate states.") :
                                                                                          ""
                        }
                    }
                }

                EvidenceCard {
                    accessibleName: qsTr("Preparation structured grid groups")
                    emptyText: qsTr("No completed structured-grid groups were recorded.")
                    evidenceModel: root.audit.gridGroups
                    listObjectName: "preparationAuditGridGroupsList"
                    subtitle: qsTr(
                                  "Coverage, repeated cells, and phase-boundary evidence by source group.")
                    title: qsTr("Structured grid")
                    rowDelegate: Component {
                        EvidenceRow {
                            required property string backendModel
                            required property bool coverageAvailable
                            required property real coverageFraction
                            required property int expectedCells
                            required property int missingCells
                            required property int multiPhaseCellCount
                            required property int observedCells
                            required property string phaseBoundaryStatus
                            required property int repeatedCellCount
                            required property int repeatedRowCount
                            required property int rowCount
                            required property string sourceFluid
                            required property string sourceRunId
                            required property int transitionEdgeCount

                            detail: qsTr("Coverage %1 · %2 / %3 cells · %4 missing · %5 row(s)").arg(
                                        root.formatFraction(coverageFraction,
                                                            coverageAvailable)).arg(
                                        observedCells).arg(expectedCells).arg(missingCells).arg(
                                        rowCount)
                            heading: qsTr("%1 · %2 · %3").arg(sourceRunId).arg(sourceFluid).arg(
                                         backendModel)
                            metadata: qsTr(
                                          "Repeated cells %1 (%2 rows) · phase %3 · multi-phase cells %4 · transition edges %5").arg(
                                          repeatedCellCount).arg(repeatedRowCount).arg(
                                          root.displayStatus(phaseBoundaryStatus)).arg(
                                          multiPhaseCellCount).arg(transitionEdgeCount)
                            warning: missingCells > 0 || repeatedCellCount > 0 ? qsTr(
                                                                                     "Grid coverage contains missing or repeated cells.") :
                                                                                 ""
                        }
                    }
                }

                EvidenceCard {
                    accessibleName: qsTr("Preparation structured grid spacing")
                    emptyText: qsTr("No coordinate-spacing evidence was recorded.")
                    evidenceModel: root.audit.gridSpacing
                    listObjectName: "preparationAuditGridSpacingList"
                    subtitle: qsTr(
                                  "Coordinate extent and spacing evidence in deterministic group order.")
                    title: qsTr("Grid spacing")
                    rowDelegate: Component {
                        EvidenceRow {
                            required property string coordinate
                            required property int groupOrder
                            required property int levelCount
                            required property real maximum
                            required property bool maximumAvailable
                            required property real maximumSpacing
                            required property bool maximumSpacingAvailable
                            required property real medianSpacing
                            required property bool medianSpacingAvailable
                            required property real minimum
                            required property bool minimumAvailable
                            required property real minimumSpacing
                            required property bool minimumSpacingAvailable
                            required property int spacingCount
                            required property real spacingRatio
                            required property bool spacingRatioAvailable
                            required property bool uniformSpacing
                            required property bool uniformSpacingAvailable

                            detail: qsTr("Levels %1 · range %2 to %3 · spacing samples %4").arg(
                                        levelCount).arg(root.formatOptional(minimum,
                                                                            minimumAvailable)).arg(
                                        root.formatOptional(maximum, maximumAvailable)).arg(
                                        spacingCount)
                            heading: qsTr("Group %1 · %2").arg(groupOrder + 1).arg(coordinate)
                            metadata: qsTr(
                                          "Spacing min %1 · median %2 · max %3 · ratio %4 · uniform %5").arg(
                                          root.formatOptional(minimumSpacing,
                                                              minimumSpacingAvailable)).arg(
                                          root.formatOptional(medianSpacing,
                                                              medianSpacingAvailable)).arg(
                                          root.formatOptional(maximumSpacing,
                                                              maximumSpacingAvailable)).arg(
                                          root.formatOptional(spacingRatio,
                                                              spacingRatioAvailable)).arg(
                                          root.formatBoolean(uniformSpacing,
                                                             uniformSpacingAvailable))
                        }
                    }
                }

                EvidenceCard {
                    accessibleName: qsTr("Preparation structured grid phase counts")
                    emptyText: qsTr("No grid phase counts were recorded.")
                    evidenceModel: root.audit.gridPhaseCounts
                    listObjectName: "preparationAuditGridPhasesList"
                    subtitle: qsTr("Observed phase counts for each structured-grid group.")
                    title: qsTr("Grid phases")
                    rowDelegate: Component {
                        EvidenceRow {
                            required property int count
                            required property int groupOrder
                            required property string phase

                            detail: qsTr("%1 row(s)").arg(count)
                            heading: qsTr("Group %1 · %2").arg(groupOrder + 1).arg(phase)
                        }
                    }
                }
            }

            ResponsiveCardGrid {
                Layout.fillWidth: true
                maximumColumns: root.expectedColumns
                minimumCardWidth: 360
                objectName: "preparationAuditMatrixGrid"
                uniformHeights: false

                EvidenceCard {
                    accessibleName: qsTr("Preparation matrix checks")
                    emptyText: qsTr(
                                   "No matrix fits were recorded; inspect the status above for whether diagnostics were requested.")
                    evidenceModel: root.audit.matrixChecks
                    listObjectName: "preparationAuditMatrixChecksList"
                    subtitle: qsTr(
                                  "Rank, effective rank, condition, and configured thresholds by fit context.")
                    title: qsTr("Matrix checks")
                    rowDelegate: Component {
                        EvidenceRow {
                            required property real conditionNumber
                            required property bool conditionNumberAvailable
                            required property bool conditionNumberInfinite
                            required property real correlationThreshold
                            required property bool correlationThresholdAvailable
                            required property real effectiveRank
                            required property bool effectiveRankAvailable
                            required property real effectiveRankFraction
                            required property bool effectiveRankFractionAvailable
                            required property int featureCount
                            required property real featureRankFraction
                            required property bool featureRankFractionAvailable
                            required property string fitPartition
                            required property real nearConstantThreshold
                            required property bool nearConstantThresholdAvailable
                            required property int numericalRank
                            required property bool numericalRankAvailable
                            required property real rankTolerance
                            required property bool rankToleranceAvailable
                            required property string rankToleranceDefinition
                            required property int rowCount
                            required property string scenario
                            required property string status
                            required property int targetCount

                            detail: qsTr(
                                        "%1 row(s) · %2 feature(s) · %3 target(s) · numerical rank %4 (%5) · effective rank %6 (%7)").arg(
                                        rowCount).arg(featureCount).arg(targetCount).arg(
                                        root.formatOptional(numericalRank,
                                                            numericalRankAvailable)).arg(
                                        root.formatFraction(featureRankFraction,
                                                            featureRankFractionAvailable)).arg(
                                        root.formatOptional(effectiveRank,
                                                            effectiveRankAvailable)).arg(
                                        root.formatFraction(effectiveRankFraction,
                                                            effectiveRankFractionAvailable))
                            heading: qsTr("%1 · fit %2 · %3").arg(root.scenarioText(scenario)).arg(
                                         fitPartition).arg(root.displayStatus(status))
                            metadata: qsTr(
                                          "Condition %1%2 · rank tolerance %3 (%4) · correlation threshold %5 · near-constant threshold %6").arg(
                                          conditionNumberInfinite ? qsTr("Infinite") :
                                                                    root.formatOptional(
                                                                        conditionNumber,
                                                                        conditionNumberAvailable)).arg(
                                          conditionNumberInfinite ? qsTr(" (recorded)") : "").arg(
                                          root.formatOptional(rankTolerance,
                                                              rankToleranceAvailable)).arg(
                                          rankToleranceDefinition.length > 0
                                          ? rankToleranceDefinition : qsTr("not recorded")).arg(
                                          root.formatOptional(correlationThreshold,
                                                              correlationThresholdAvailable)).arg(
                                          root.formatOptional(nearConstantThreshold,
                                                              nearConstantThresholdAvailable))
                        }
                    }
                }

                EvidenceCard {
                    accessibleName: qsTr("Preparation matrix feature flags")
                    emptyText: qsTr(
                                   "No constant or near-constant feature or target flags were recorded.")
                    evidenceModel: root.audit.matrixFeatureFlags
                    listObjectName: "preparationAuditMatrixFlagsList"
                    subtitle: qsTr(
                                  "Constant and near-constant findings retain their scenario and fit partition.")
                    title: qsTr("Feature and target flags")
                    rowDelegate: Component {
                        EvidenceRow {
                            required property string field
                            required property string fitPartition
                            required property string kind
                            required property real relativeSpread
                            required property bool relativeSpreadAvailable
                            required property string scenario

                            detail: qsTr("%1 · relative spread %2").arg(root.displayStatus(
                                                                            kind)).arg(
                                        root.formatOptional(relativeSpread,
                                                            relativeSpreadAvailable))
                            heading: field
                            metadata: qsTr("%1 · fit %2").arg(root.scenarioText(scenario)).arg(
                                          fitPartition)
                        }
                    }
                }

                EvidenceCard {
                    accessibleName: qsTr("Preparation singular values")
                    emptyText: qsTr("No singular values were recorded.")
                    evidenceModel: root.audit.singularValues
                    listObjectName: "preparationAuditSingularValuesList"
                    subtitle: qsTr("Ordered singular values and explained-variance ratios by fit.")
                    title: qsTr("Singular values")
                    rowDelegate: Component {
                        EvidenceRow {
                            required property real explainedVarianceRatio
                            required property string fitPartition
                            required property int order
                            required property string scenario
                            required property real singularValue

                            detail: qsTr("Value %1 · explained variance %2").arg(root.formatNumber(
                                                                                     singularValue)).arg(
                                        root.formatFraction(explainedVarianceRatio, true))
                            heading: qsTr("%1 · fit %2 · singular value %3").arg(root.scenarioText(
                                                                                     scenario)).arg(
                                         fitPartition).arg(order + 1)
                        }
                    }
                }

                EvidenceCard {
                    accessibleName: qsTr("Preparation correlated feature pairs")
                    emptyText: qsTr("No highly correlated feature pairs were recorded.")
                    evidenceModel: root.audit.correlatedFeaturePairs
                    listObjectName: "preparationAuditCorrelatedPairsList"
                    subtitle: qsTr("Pairs exceeding the configured absolute-correlation threshold.")
                    title: qsTr("Correlated feature pairs")
                    rowDelegate: Component {
                        EvidenceRow {
                            required property real correlation
                            required property string fitPartition
                            required property var model
                            required property string scenario

                            detail: qsTr("Correlation %1").arg(root.formatNumber(correlation))
                            heading: qsTr("%1 ↔ %2").arg(model.left).arg(model.right)
                            metadata: qsTr("%1 · fit %2").arg(root.scenarioText(scenario)).arg(
                                          fitPartition)
                        }
                    }
                }

                EvidenceCard {
                    accessibleName: qsTr("Preparation feature target correlations")
                    emptyText: qsTr("No feature-target correlations were recorded.")
                    evidenceModel: root.audit.featureTargetCorrelations
                    listObjectName: "preparationAuditFeatureTargetList"
                    subtitle: qsTr(
                                  "Recorded feature-target relationships by scenario and fit partition.")
                    title: qsTr("Feature-target correlations")
                    rowDelegate: Component {
                        EvidenceRow {
                            required property real correlation
                            required property string feature
                            required property string fitPartition
                            required property string scenario
                            required property string target

                            detail: qsTr("Correlation %1").arg(root.formatNumber(correlation))
                            heading: qsTr("%1 → %2").arg(feature).arg(target)
                            metadata: qsTr("%1 · fit %2").arg(root.scenarioText(scenario)).arg(
                                          fitPartition)
                        }
                    }
                }
            }

            ResponsiveCardGrid {
                Layout.fillWidth: true
                maximumColumns: root.expectedColumns
                minimumCardWidth: 360
                objectName: "preparationAuditBaselineGrid"
                uniformHeights: false

                EvidenceCard {
                    accessibleName: qsTr("Preparation baseline checks")
                    emptyText: qsTr(
                                   "No baseline fits were recorded; inspect the status above for whether diagnostics were requested.")
                    evidenceModel: root.audit.baselineChecks
                    listObjectName: "preparationAuditBaselineChecksList"
                    subtitle: qsTr(
                                  "Diagnostic-only baseline execution context and completion counts.")
                    title: qsTr("Baseline checks")
                    rowDelegate: Component {
                        EvidenceRow {
                            required property int completedModelCount
                            required property int evaluationPartitionCount
                            required property int evaluationRowCount
                            required property int failedModelCount
                            required property int featureCount
                            required property string library
                            required property string libraryVersion
                            required property string policy
                            required property string scenario
                            required property string status
                            required property int targetCount
                            required property int trainRowCount
                            required property bool trainRowCountAvailable

                            detail: qsTr(
                                        "Train rows %1 · %2 feature(s) · %3 target(s) · %4 evaluation partition(s), %5 row(s)").arg(
                                        root.formatOptional(trainRowCount,
                                                            trainRowCountAvailable)).arg(
                                        featureCount).arg(targetCount).arg(
                                        evaluationPartitionCount).arg(evaluationRowCount)
                            heading: qsTr("%1 · %2").arg(root.scenarioText(scenario)).arg(
                                         root.displayStatus(status))
                            metadata: qsTr(
                                          "%1 %2 · completed models %3 · failed models %4 · %5").arg(
                                          library).arg(libraryVersion).arg(completedModelCount).arg(
                                          failedModelCount).arg(policy)
                            warning: failedModelCount > 0 ? qsTr(
                                                                "One or more diagnostic baseline fits failed.") :
                                                            ""
                        }
                    }
                }

                EvidenceCard {
                    accessibleName: qsTr("Preparation baseline metrics")
                    emptyText: qsTr("No baseline metrics were recorded.")
                    evidenceModel: root.audit.baselineMetrics
                    listObjectName: "preparationAuditBaselineMetricsList"
                    subtitle: qsTr(
                                  "Metrics and actual/prediction ranges retain model, target, and partition context.")
                    title: qsTr("Baseline metrics")
                    rowDelegate: Component {
                        EvidenceRow {
                            required property real actualMaximum
                            required property real actualMinimum
                            required property real meanAbsoluteError
                            required property string model
                            required property string partition
                            required property real predictionMaximum
                            required property real predictionMinimum
                            required property real rSquared
                            required property bool rSquaredAvailable
                            required property real rootMeanSquaredError
                            required property string scenario
                            required property string target

                            detail: qsTr("MAE %1 · RMSE %2 · R² %3").arg(root.formatNumber(
                                                                             meanAbsoluteError)).arg(
                                        root.formatNumber(rootMeanSquaredError)).arg(
                                        root.formatOptional(rSquared, rSquaredAvailable))
                            heading: qsTr("%1 · %2 · %3").arg(model).arg(target).arg(partition)
                            metadata: qsTr("%1 · actual %2 to %3 · prediction %4 to %5").arg(
                                          root.scenarioText(scenario)).arg(root.formatNumber(
                                                                               actualMinimum)).arg(
                                          root.formatNumber(actualMaximum)).arg(root.formatNumber(
                                                                                    predictionMinimum)).arg(
                                          root.formatNumber(predictionMaximum))
                        }
                    }
                }

                EvidenceCard {
                    accessibleName: qsTr("Preparation baseline failures")
                    emptyText: qsTr("No baseline fit failures were recorded.")
                    evidenceModel: root.audit.baselineFailures
                    listObjectName: "preparationAuditBaselineFailuresList"
                    subtitle: qsTr(
                                  "Fit failures remain visible without replacing successful diagnostic results.")
                    title: qsTr("Baseline failures")
                    rowDelegate: Component {
                        EvidenceRow {
                            required property string errorType
                            required property string message
                            required property string model
                            required property string scenario
                            required property string target

                            detail: qsTr("%1: %2").arg(errorType).arg(message)
                            heading: qsTr("%1 · %2").arg(model).arg(target)
                            metadata: root.scenarioText(scenario)
                            warning: qsTr(
                                         "Diagnostic fit failed; successful results remain inspectable.")
                        }
                    }
                }
            }
        }
    }
}
