from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication, QEventLoop, QSettings, QTimer
from PySide6.QtQml import QQmlComponent
from PySide6.QtQuick import QQuickItem, QQuickWindow
from PySide6.QtWidgets import QApplication

from carnopy.app.preparation_audit import (
    BASELINE_CHECK_ROLES,
    BASELINE_FAILURE_ROLES,
    BASELINE_METRIC_ROLES,
    CORRELATED_PAIR_ROLES,
    DUPLICATE_STATE_ROLES,
    FEATURE_TARGET_CORRELATION_ROLES,
    GRID_GROUP_ROLES,
    GRID_PHASE_ROLES,
    GRID_SPACING_ROLES,
    LEAKAGE_ROLES,
    MATRIX_CHECK_ROLES,
    MATRIX_FEATURE_FLAG_ROLES,
    PARTITION_ROLES,
    QUALITY_OVERVIEW_ROLES,
    SCENARIO_ROLES,
    SINGULAR_VALUE_ROLES,
    PreparationAuditProjection,
)
from carnopy.app.preparation_audit_models import PreparationAuditModel
from carnopy.app.qml_resources import MANDATORY_QML_FILES
from carnopy.app.qml_runtime import QmlApplicationRuntime, create_qml_runtime
from carnopy.app.workspace import initialize_workspace

ROOT = Path(__file__).resolve().parents[1]

_BOOLEAN_ROLES = {
    "conditionNumberInfinite",
    "countsAvailable",
    "coverageAvailable",
    "eligibleRowCountAvailable",
    "excludedRowCountAvailable",
    "featureRankFractionAvailable",
    "flagCountMatches",
    "leakageAvailable",
    "maximumAvailable",
    "maximumSpacingAvailable",
    "medianSpacingAvailable",
    "minimumAvailable",
    "minimumSpacingAvailable",
    "nearConstantThresholdAvailable",
    "numericalRankAvailable",
    "rSquaredAvailable",
    "rankToleranceAvailable",
    "recordedFlagCountAvailable",
    "inspectedFlagCountAvailable",
    "relativeSpreadAvailable",
    "spacingRatioAvailable",
    "uniformSpacing",
    "uniformSpacingAvailable",
    "correlationThresholdAvailable",
    "effectiveRankAvailable",
    "effectiveRankFractionAvailable",
}
_REAL_ROLES = {
    "actualMaximum",
    "actualMinimum",
    "conditionNumber",
    "correlation",
    "correlationThreshold",
    "coverageFraction",
    "effectiveRank",
    "effectiveRankFraction",
    "explainedVarianceRatio",
    "featureRankFraction",
    "maximum",
    "maximumSpacing",
    "meanAbsoluteError",
    "medianSpacing",
    "minimum",
    "minimumSpacing",
    "nearConstantThreshold",
    "predictionMaximum",
    "predictionMinimum",
    "rSquared",
    "rankTolerance",
    "relativeSpread",
    "rootMeanSquaredError",
    "singularValue",
    "spacingRatio",
}
_INTEGER_ROLES = {
    "completedModelCount",
    "conflictingTargetGroupCount",
    "crossPartitionGroupCount",
    "duplicateGroupCount",
    "duplicateRowCount",
    "duplicateStateGroupCount",
    "eligibleRowCount",
    "errorCount",
    "evaluationPartitionCount",
    "evaluationRowCount",
    "excludedRowCount",
    "expectedCells",
    "failedModelCount",
    "featureCount",
    "groupOrder",
    "inspectedFlagCount",
    "levelCount",
    "missingCells",
    "multiPhaseCellCount",
    "numericalRank",
    "observedCells",
    "order",
    "partitionCount",
    "recordedFlagCount",
    "repeatedCellCount",
    "repeatedRowCount",
    "rowCount",
    "spacingCount",
    "targetCount",
    "trainRowCount",
    "transformationCount",
    "transitionEdgeCount",
}


@pytest.fixture
def application() -> QApplication:
    existing = QApplication.instance()
    return existing if isinstance(existing, QApplication) else QApplication([])


@pytest.fixture
def runtime(tmp_path: Path, application: QApplication) -> Iterator[QmlApplicationRuntime]:
    del application
    workspace = initialize_workspace(tmp_path / "workspace")
    created = create_qml_runtime(
        settings=QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat),
        initial_workspace=workspace.root,
        application_arguments=[],
    )
    _wait_for_idle(created)
    yield created
    _wait_for_idle(created)
    assert created.close()
    assert created.warning_capture.runtime_warnings == ()


@pytest.fixture
def audit_view(runtime: QmlApplicationRuntime) -> Iterator[QQuickItem]:
    model = PreparationAuditModel(runtime.controller)
    model.replace(_projection())
    window = runtime.engine.rootObjects()[0]
    assert isinstance(window, QQuickWindow)
    window.setWidth(1440)
    window.setHeight(1200)
    component = QQmlComponent(runtime.engine)
    component.loadFromModule("Carnopy", "PreparationAuditView")
    assert component.status() == QQmlComponent.Status.Ready, _component_errors(component)
    created = component.createWithInitialProperties({"audit": model})
    assert isinstance(created, QQuickItem), _component_errors(component)
    created.setParent(window)
    created.setParentItem(window.contentItem())
    created.setWidth(1180)
    created.setZ(1000)
    _process_events()
    yield created


def _component_errors(component: QQmlComponent) -> str:
    return "\n".join(error.toString() for error in component.errors())


def _process_events() -> None:
    application = QCoreApplication.instance()
    assert application is not None
    for _ in range(6):
        application.processEvents()


def _wait_for_idle(runtime: QmlApplicationRuntime) -> None:
    if not runtime.controller.request_coordinator.is_busy:
        _process_events()
        return
    loop = QEventLoop()
    runtime.controller.request_coordinator.busy_changed.connect(
        lambda busy: None if busy else loop.quit()
    )
    QTimer.singleShot(15_000, loop.quit)
    loop.exec()
    _process_events()
    assert not runtime.controller.request_coordinator.is_busy


def _item(root: QQuickItem, object_name: str) -> QQuickItem:
    pending = [root]
    while pending:
        candidate = pending.pop()
        if candidate.objectName() == object_name:
            return candidate
        pending.extend(candidate.childItems())
    raise AssertionError(f"missing visual item: {object_name}")


def _row(roles: tuple[str, ...], **values: object) -> dict[str, object]:
    row: dict[str, object] = {}
    for role in roles:
        if role in _BOOLEAN_ROLES:
            row[role] = False
        elif role in _REAL_ROLES:
            row[role] = 0.0
        elif role in _INTEGER_ROLES:
            row[role] = 0
        elif role == "groupColumns":
            row[role] = []
        else:
            row[role] = ""
    row.update(values)
    return row


def _projection() -> PreparationAuditProjection:
    return PreparationAuditProjection(
        available=True,
        quality_status="completed_with_failures",
        quality_errors=(),
        scenario_evidence_available=True,
        leakage_evidence_available=True,
        duplicate_state_evidence_available=True,
        grid_evidence_available=True,
        matrix_evidence_available=True,
        baseline_evidence_available=True,
        quality_overview=(
            _row(
                QUALITY_OVERVIEW_ROLES,
                status="completed_with_failures",
                eligibleRowCount=8,
                excludedRowCount=1,
                eligibleRowCountAvailable=True,
                excludedRowCountAvailable=True,
                recordedFlagCount=2,
                inspectedFlagCount=2,
                recordedFlagCountAvailable=True,
                inspectedFlagCountAvailable=True,
                flagCountMatches=True,
                scenarioStatus="completed",
                matrixStatus="completed",
                baselineStatus="completed_with_failures",
                duplicateStatus="completed",
                gridStatus="completed",
            ),
        ),
        scenarios=(
            _row(
                SCENARIO_ROLES,
                name="holdout",
                kind="shuffle",
                rowCount=8,
                partitionCount=2,
                transformationCount=1,
                leakageAvailable=True,
            ),
        ),
        partitions=(_row(PARTITION_ROLES, scenario="holdout", partition="train", rowCount=6),),
        leakage_audits=(
            _row(
                LEAKAGE_ROLES,
                scenario="holdout",
                identityColumn="source_state_hash",
                duplicateStateGroupCount=1,
            ),
        ),
        duplicate_state_checks=(
            _row(
                DUPLICATE_STATE_ROLES,
                status="completed",
                groupColumns=["fluid", "temperature", "pressure"],
                countsAvailable=True,
                duplicateGroupCount=1,
                duplicateRowCount=2,
            ),
        ),
        grid_groups=(
            _row(
                GRID_GROUP_ROLES,
                sourceRunId="run-1",
                sourceFluid="Propane",
                backendModel="heos",
                rowCount=8,
                expectedCells=9,
                observedCells=8,
                missingCells=1,
                coverageFraction=8 / 9,
                coverageAvailable=True,
                phaseBoundaryStatus="completed",
            ),
        ),
        grid_spacing=(
            _row(
                GRID_SPACING_ROLES,
                coordinate="source_temperature_K",
                levelCount=3,
                minimum=300.0,
                minimumAvailable=True,
                maximum=320.0,
                maximumAvailable=True,
                spacingCount=2,
                minimumSpacing=10.0,
                minimumSpacingAvailable=True,
                maximumSpacing=10.0,
                maximumSpacingAvailable=True,
                medianSpacing=10.0,
                medianSpacingAvailable=True,
                spacingRatio=1.0,
                spacingRatioAvailable=True,
                uniformSpacing=True,
                uniformSpacingAvailable=True,
            ),
        ),
        grid_phase_counts=(_row(GRID_PHASE_ROLES, phase="gas", count=5),),
        matrix_checks=(
            _row(
                MATRIX_CHECK_ROLES,
                scenario="holdout",
                fitPartition="train",
                status="completed",
                rowCount=6,
                featureCount=4,
                targetCount=2,
                numericalRank=2,
                numericalRankAvailable=True,
                featureRankFraction=0.5,
                featureRankFractionAvailable=True,
                effectiveRank=1.4,
                effectiveRankAvailable=True,
                effectiveRankFraction=0.35,
                effectiveRankFractionAvailable=True,
                conditionNumber=3.0,
                conditionNumberAvailable=True,
            ),
        ),
        matrix_feature_flags=(
            _row(
                MATRIX_FEATURE_FLAG_ROLES,
                scenario="holdout",
                fitPartition="train",
                kind="near_constant_feature",
                field="temperature",
                relativeSpread=1e-14,
                relativeSpreadAvailable=True,
            ),
        ),
        singular_values=(
            _row(
                SINGULAR_VALUE_ROLES,
                scenario="holdout",
                fitPartition="train",
                singularValue=3.0,
                explainedVarianceRatio=0.9,
            ),
        ),
        correlated_feature_pairs=(
            _row(
                CORRELATED_PAIR_ROLES,
                scenario="holdout",
                fitPartition="train",
                left="pressure",
                right="pressure_copy",
                correlation=1.0,
            ),
        ),
        feature_target_correlations=(
            _row(
                FEATURE_TARGET_CORRELATION_ROLES,
                scenario="holdout",
                fitPartition="train",
                feature="pressure",
                target="mass_density",
                correlation=0.75,
            ),
        ),
        baseline_checks=(
            _row(
                BASELINE_CHECK_ROLES,
                scenario="holdout",
                status="completed_with_failures",
                library="scikit-learn",
                libraryVersion="1.8.0",
                featureCount=1,
                targetCount=1,
                trainRowCount=6,
                trainRowCountAvailable=True,
                evaluationPartitionCount=1,
                evaluationRowCount=2,
                completedModelCount=1,
                failedModelCount=1,
                policy="diagnostic metrics only",
            ),
        ),
        baseline_metrics=(
            _row(
                BASELINE_METRIC_ROLES,
                scenario="holdout",
                model="ridge",
                target="mass_density",
                partition="test",
                meanAbsoluteError=0.1,
                rootMeanSquaredError=0.2,
                rSquaredAvailable=False,
                actualMinimum=1.0,
                actualMaximum=2.0,
                predictionMinimum=1.1,
                predictionMaximum=1.9,
            ),
        ),
        baseline_failures=(
            _row(
                BASELINE_FAILURE_ROLES,
                scenario="holdout",
                model="hist_gradient_boosting",
                target="mass_density",
                errorType="ValueError",
                message="not enough rows",
            ),
        ),
    )


def test_preparation_audit_view_presents_every_typed_evidence_model(
    runtime: QmlApplicationRuntime,
    audit_view: QQuickItem,
) -> None:
    expected_counts = {
        "preparationAuditScenariosList": 1,
        "preparationAuditPartitionsList": 1,
        "preparationAuditLeakageList": 1,
        "preparationAuditDuplicateStatesList": 1,
        "preparationAuditGridGroupsList": 1,
        "preparationAuditGridSpacingList": 1,
        "preparationAuditGridPhasesList": 1,
        "preparationAuditMatrixChecksList": 1,
        "preparationAuditMatrixFlagsList": 1,
        "preparationAuditSingularValuesList": 1,
        "preparationAuditCorrelatedPairsList": 1,
        "preparationAuditFeatureTargetList": 1,
        "preparationAuditBaselineChecksList": 1,
        "preparationAuditBaselineMetricsList": 1,
        "preparationAuditBaselineFailuresList": 1,
    }
    for object_name, count in expected_counts.items():
        assert _item(audit_view, object_name).property("count") == count

    assert _item(audit_view, "preparationAuditStatus").property("label") == (
        "Completed with failures"
    )
    assert _item(audit_view, "preparationAuditOverviewGrid").property("maximumColumns") == 2
    assert runtime.warning_capture.runtime_warnings == ()


def test_preparation_audit_view_switches_sections_and_stacks_at_narrow_width(
    runtime: QmlApplicationRuntime,
    audit_view: QQuickItem,
) -> None:
    audit_view.setProperty("selectedSection", 1)
    _process_events()
    assert _item(audit_view, "preparationAuditSectionStack").property("currentIndex") == 1
    assert _item(audit_view, "preparationAuditMatrixChecksList").isVisible()

    audit_view.setProperty("selectedSection", 2)
    audit_view.setWidth(720)
    _process_events()
    assert _item(audit_view, "preparationAuditSectionStack").property("currentIndex") == 2
    assert _item(audit_view, "preparationAuditBaselineMetricsList").isVisible()
    assert _item(audit_view, "preparationAuditOverviewGrid").property("maximumColumns") == 1
    assert _item(audit_view, "preparationAuditMatrixGrid").property("maximumColumns") == 1
    assert _item(audit_view, "preparationAuditBaselineGrid").property("maximumColumns") == 1
    assert runtime.warning_capture.runtime_warnings == ()


def test_preparation_audit_view_keeps_unavailable_evidence_explicit(
    runtime: QmlApplicationRuntime,
    audit_view: QQuickItem,
) -> None:
    model = audit_view.property("audit")
    assert isinstance(model, PreparationAuditModel)

    model.clear()
    _process_events()

    assert _item(audit_view, "preparationAuditStatus").property("label") == "Unavailable"
    assert _item(audit_view, "preparationAuditScenariosList").property("count") == 0
    assert not _item(audit_view, "preparationAuditScenariosList").isVisible()
    assert runtime.warning_capture.runtime_warnings == ()


def test_preparation_audit_qml_resource_and_typed_boundary_are_explicit() -> None:
    qml_root = ROOT / "src/carnopy/app/qml/Carnopy"
    source = (qml_root / "components/PreparationAuditView.qml").read_text(encoding="utf-8")
    qmldir = (qml_root / "qmldir").read_text(encoding="utf-8")

    assert "PreparationAuditView 1.0 components/PreparationAuditView.qml" in qmldir
    assert "qml/Carnopy/components/PreparationAuditView.qml" in MANDATORY_QML_FILES
    assert "required property var audit" in source
    assert "root.audit.matrixChecks" in source
    assert "root.audit.baselineMetrics" in source
    assert "ListView" in source
    assert "reuseItems: true" in source
    assert "inspectionController" not in source
    assert "JSON" not in source
    assert "yaml" not in source.casefold()
