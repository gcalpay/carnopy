from __future__ import annotations

from PySide6.QtCore import Property, QObject, Signal

from carnopy.app.inspection_models import InspectionListModel
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


class PreparationAuditModel(QObject):
    """Own the fixed QML-safe models for one accepted Preparation audit."""

    changed = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._projection: PreparationAuditProjection | None = None
        self.quality_overview = InspectionListModel(QUALITY_OVERVIEW_ROLES, self)
        self.scenarios = InspectionListModel(SCENARIO_ROLES, self)
        self.partitions = InspectionListModel(PARTITION_ROLES, self)
        self.leakage_audits = InspectionListModel(LEAKAGE_ROLES, self)
        self.duplicate_state_checks = InspectionListModel(DUPLICATE_STATE_ROLES, self)
        self.grid_groups = InspectionListModel(GRID_GROUP_ROLES, self)
        self.grid_spacing = InspectionListModel(GRID_SPACING_ROLES, self)
        self.grid_phase_counts = InspectionListModel(GRID_PHASE_ROLES, self)
        self.matrix_checks = InspectionListModel(MATRIX_CHECK_ROLES, self)
        self.matrix_feature_flags = InspectionListModel(MATRIX_FEATURE_FLAG_ROLES, self)
        self.singular_values = InspectionListModel(SINGULAR_VALUE_ROLES, self)
        self.correlated_feature_pairs = InspectionListModel(CORRELATED_PAIR_ROLES, self)
        self.feature_target_correlations = InspectionListModel(
            FEATURE_TARGET_CORRELATION_ROLES,
            self,
        )
        self.baseline_checks = InspectionListModel(BASELINE_CHECK_ROLES, self)
        self.baseline_metrics = InspectionListModel(BASELINE_METRIC_ROLES, self)
        self.baseline_failures = InspectionListModel(BASELINE_FAILURE_ROLES, self)

    def replace(self, projection: PreparationAuditProjection) -> None:
        self._projection = projection
        rows = (
            (self.quality_overview, projection.quality_overview, projection.available),
            (self.scenarios, projection.scenarios, projection.scenario_evidence_available),
            (self.partitions, projection.partitions, projection.scenario_evidence_available),
            (
                self.leakage_audits,
                projection.leakage_audits,
                projection.leakage_evidence_available,
            ),
            (
                self.duplicate_state_checks,
                projection.duplicate_state_checks,
                projection.duplicate_state_evidence_available,
            ),
            (self.grid_groups, projection.grid_groups, projection.grid_evidence_available),
            (self.grid_spacing, projection.grid_spacing, projection.grid_evidence_available),
            (
                self.grid_phase_counts,
                projection.grid_phase_counts,
                projection.grid_evidence_available,
            ),
            (self.matrix_checks, projection.matrix_checks, projection.matrix_evidence_available),
            (
                self.matrix_feature_flags,
                projection.matrix_feature_flags,
                projection.matrix_evidence_available,
            ),
            (
                self.singular_values,
                projection.singular_values,
                projection.matrix_evidence_available,
            ),
            (
                self.correlated_feature_pairs,
                projection.correlated_feature_pairs,
                projection.matrix_evidence_available,
            ),
            (
                self.feature_target_correlations,
                projection.feature_target_correlations,
                projection.matrix_evidence_available,
            ),
            (
                self.baseline_checks,
                projection.baseline_checks,
                projection.baseline_evidence_available,
            ),
            (
                self.baseline_metrics,
                projection.baseline_metrics,
                projection.baseline_evidence_available,
            ),
            (
                self.baseline_failures,
                projection.baseline_failures,
                projection.baseline_evidence_available,
            ),
        )
        for model, values, available in rows:
            model.set_rows(values, available=available)
        self.changed.emit()

    def clear(self) -> None:
        had_projection = self._projection is not None
        self._projection = None
        for model in self._models():
            model.clear()
        if had_projection:
            self.changed.emit()

    def _models(self) -> tuple[InspectionListModel, ...]:
        return (
            self.quality_overview,
            self.scenarios,
            self.partitions,
            self.leakage_audits,
            self.duplicate_state_checks,
            self.grid_groups,
            self.grid_spacing,
            self.grid_phase_counts,
            self.matrix_checks,
            self.matrix_feature_flags,
            self.singular_values,
            self.correlated_feature_pairs,
            self.feature_target_correlations,
            self.baseline_checks,
            self.baseline_metrics,
            self.baseline_failures,
        )

    def get_available(self) -> bool:
        return bool(self._projection is not None and self._projection.available)

    available = Property(bool, get_available, notify=changed)

    def get_quality_status(self) -> str:
        return "" if self._projection is None else self._projection.quality_status

    qualityStatus = Property(str, get_quality_status, notify=changed)

    def get_scenario_evidence_available(self) -> bool:
        return bool(self._projection is not None and self._projection.scenario_evidence_available)

    scenarioEvidenceAvailable = Property(
        bool,
        get_scenario_evidence_available,
        notify=changed,
    )

    def get_leakage_evidence_available(self) -> bool:
        return bool(self._projection is not None and self._projection.leakage_evidence_available)

    leakageEvidenceAvailable = Property(
        bool,
        get_leakage_evidence_available,
        notify=changed,
    )

    qualityOverview = Property(QObject, lambda self: self.quality_overview, constant=True)
    scenariosModel = Property(QObject, lambda self: self.scenarios, constant=True)
    partitionsModel = Property(QObject, lambda self: self.partitions, constant=True)
    leakageAudits = Property(QObject, lambda self: self.leakage_audits, constant=True)
    duplicateStateChecks = Property(
        QObject,
        lambda self: self.duplicate_state_checks,
        constant=True,
    )
    gridGroups = Property(QObject, lambda self: self.grid_groups, constant=True)
    gridSpacing = Property(QObject, lambda self: self.grid_spacing, constant=True)
    gridPhaseCounts = Property(QObject, lambda self: self.grid_phase_counts, constant=True)
    matrixChecks = Property(QObject, lambda self: self.matrix_checks, constant=True)
    matrixFeatureFlags = Property(
        QObject,
        lambda self: self.matrix_feature_flags,
        constant=True,
    )
    singularValues = Property(QObject, lambda self: self.singular_values, constant=True)
    correlatedFeaturePairs = Property(
        QObject,
        lambda self: self.correlated_feature_pairs,
        constant=True,
    )
    featureTargetCorrelations = Property(
        QObject,
        lambda self: self.feature_target_correlations,
        constant=True,
    )
    baselineChecks = Property(QObject, lambda self: self.baseline_checks, constant=True)
    baselineMetrics = Property(QObject, lambda self: self.baseline_metrics, constant=True)
    baselineFailures = Property(QObject, lambda self: self.baseline_failures, constant=True)
