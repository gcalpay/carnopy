from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

QUALITY_OVERVIEW_ROLES = (
    "status",
    "eligibleRowCount",
    "excludedRowCount",
    "eligibleRowCountAvailable",
    "excludedRowCountAvailable",
    "recordedFlagCount",
    "inspectedFlagCount",
    "recordedFlagCountAvailable",
    "inspectedFlagCountAvailable",
    "flagCountMatches",
    "errorCount",
    "scenarioStatus",
    "matrixStatus",
    "baselineStatus",
    "duplicateStatus",
    "gridStatus",
)
SCENARIO_ROLES = (
    "name",
    "kind",
    "order",
    "rowCount",
    "partitionCount",
    "transformationCount",
    "leakageAvailable",
)
PARTITION_ROLES = ("scenario", "partition", "order", "rowCount")
LEAKAGE_ROLES = (
    "scenario",
    "identityColumn",
    "duplicateStateGroupCount",
    "crossPartitionGroupCount",
)
DUPLICATE_STATE_ROLES = (
    "status",
    "groupColumns",
    "identityColumn",
    "countsAvailable",
    "duplicateGroupCount",
    "duplicateRowCount",
    "conflictingTargetGroupCount",
)
GRID_GROUP_ROLES = (
    "order",
    "sourceRunId",
    "sourceFluid",
    "backendModel",
    "rowCount",
    "expectedCells",
    "observedCells",
    "missingCells",
    "coverageFraction",
    "coverageAvailable",
    "repeatedCellCount",
    "repeatedRowCount",
    "phaseBoundaryStatus",
    "multiPhaseCellCount",
    "transitionEdgeCount",
)
GRID_SPACING_ROLES = (
    "groupOrder",
    "coordinate",
    "order",
    "levelCount",
    "minimum",
    "minimumAvailable",
    "maximum",
    "maximumAvailable",
    "spacingCount",
    "minimumSpacing",
    "minimumSpacingAvailable",
    "maximumSpacing",
    "maximumSpacingAvailable",
    "medianSpacing",
    "medianSpacingAvailable",
    "spacingRatio",
    "spacingRatioAvailable",
    "uniformSpacing",
    "uniformSpacingAvailable",
)
GRID_PHASE_ROLES = ("groupOrder", "phase", "count")
MATRIX_CHECK_ROLES = (
    "scenario",
    "fitPartition",
    "order",
    "status",
    "rowCount",
    "featureCount",
    "targetCount",
    "correlationThreshold",
    "correlationThresholdAvailable",
    "nearConstantThreshold",
    "nearConstantThresholdAvailable",
    "numericalRank",
    "numericalRankAvailable",
    "featureRankFraction",
    "featureRankFractionAvailable",
    "effectiveRank",
    "effectiveRankAvailable",
    "effectiveRankFraction",
    "effectiveRankFractionAvailable",
    "conditionNumber",
    "conditionNumberAvailable",
    "conditionNumberInfinite",
    "rankTolerance",
    "rankToleranceAvailable",
    "rankToleranceDefinition",
)
MATRIX_FEATURE_FLAG_ROLES = (
    "scenario",
    "fitPartition",
    "kind",
    "field",
    "order",
    "relativeSpread",
    "relativeSpreadAvailable",
)
SINGULAR_VALUE_ROLES = (
    "scenario",
    "fitPartition",
    "order",
    "singularValue",
    "explainedVarianceRatio",
)
CORRELATED_PAIR_ROLES = (
    "scenario",
    "fitPartition",
    "order",
    "left",
    "right",
    "correlation",
)
FEATURE_TARGET_CORRELATION_ROLES = (
    "scenario",
    "fitPartition",
    "order",
    "feature",
    "target",
    "correlation",
)
BASELINE_CHECK_ROLES = (
    "scenario",
    "order",
    "status",
    "library",
    "libraryVersion",
    "featureCount",
    "targetCount",
    "trainRowCount",
    "trainRowCountAvailable",
    "evaluationPartitionCount",
    "evaluationRowCount",
    "completedModelCount",
    "failedModelCount",
    "policy",
)
BASELINE_METRIC_ROLES = (
    "scenario",
    "model",
    "target",
    "partition",
    "order",
    "meanAbsoluteError",
    "rootMeanSquaredError",
    "rSquared",
    "rSquaredAvailable",
    "actualMinimum",
    "actualMaximum",
    "predictionMinimum",
    "predictionMaximum",
)
BASELINE_FAILURE_ROLES = (
    "scenario",
    "model",
    "target",
    "order",
    "errorType",
    "message",
)

_PARTITION_ORDER = {"all": 0, "train": 1, "validation": 2, "test": 3}
_GRID_COORDINATE_ORDER = {"source_temperature_K": 0, "source_pressure_Pa": 1}


@dataclass(frozen=True)
class PreparationAuditProjection:
    """Detached typed rows from one finalized Preparation inspection."""

    available: bool
    quality_status: str
    quality_errors: tuple[str, ...]
    scenario_evidence_available: bool
    leakage_evidence_available: bool
    duplicate_state_evidence_available: bool
    grid_evidence_available: bool
    matrix_evidence_available: bool
    baseline_evidence_available: bool
    quality_overview: tuple[dict[str, object], ...]
    scenarios: tuple[dict[str, object], ...]
    partitions: tuple[dict[str, object], ...]
    leakage_audits: tuple[dict[str, object], ...]
    duplicate_state_checks: tuple[dict[str, object], ...]
    grid_groups: tuple[dict[str, object], ...]
    grid_spacing: tuple[dict[str, object], ...]
    grid_phase_counts: tuple[dict[str, object], ...]
    matrix_checks: tuple[dict[str, object], ...]
    matrix_feature_flags: tuple[dict[str, object], ...]
    singular_values: tuple[dict[str, object], ...]
    correlated_feature_pairs: tuple[dict[str, object], ...]
    feature_target_correlations: tuple[dict[str, object], ...]
    baseline_checks: tuple[dict[str, object], ...]
    baseline_metrics: tuple[dict[str, object], ...]
    baseline_failures: tuple[dict[str, object], ...]

    @classmethod
    def from_worker_payload(
        cls,
        payload: Mapping[str, object],
    ) -> PreparationAuditProjection:
        if payload.get("source_kind") != "preparation":
            raise ValueError("Preparation audit source kind must be preparation")
        summary = _mapping(payload.get("summary"), "inspection summary")
        quality = _optional_mapping(summary.get("quality"), "quality evidence")
        errors = tuple(_optional_ordered_text_list(quality.get("errors"), "quality errors"))
        quality_summary = _optional_mapping(quality.get("summary"), "quality summary")
        quality_status = _status(quality_summary.get("status"), default="absent")

        scenario_evidence, scenario_evidence_available = _scenario_evidence(payload)
        raw_scenarios = summary.get("scenarios")
        scenarios, partitions, leakage_audits, scenario_status = _scenario_rows(
            raw_scenarios,
            scenario_evidence,
            evidence_available=scenario_evidence_available,
        )
        raw_duplicates = quality_summary.get("duplicate_state_candidates")
        duplicate_rows, duplicate_status = _duplicate_state_rows(raw_duplicates)
        raw_grid = quality_summary.get("structured_grid")
        grid_groups, grid_spacing, grid_phases, grid_status = _grid_rows(raw_grid)
        raw_matrix = quality_summary.get("matrix_diagnostics")
        (
            matrix_checks,
            matrix_feature_flags,
            singular_values,
            correlated_pairs,
            target_correlations,
            matrix_status,
        ) = _matrix_rows(raw_matrix)
        raw_baseline = quality_summary.get("baseline_diagnostics")
        baseline_checks, baseline_metrics, baseline_failures, baseline_status = _baseline_rows(
            raw_baseline
        )

        eligible, eligible_available = _optional_nonnegative_integer(
            _optional_mapping(quality_summary.get("row_counts"), "quality row counts").get(
                "eligible"
            ),
            "eligible row count",
        )
        excluded, excluded_available = _optional_nonnegative_integer(
            _optional_mapping(quality_summary.get("row_counts"), "quality row counts").get(
                "excluded"
            ),
            "excluded row count",
        )
        expected_eligible_rows = _validate_inspection_row_counts(
            summary,
            eligible=eligible,
            eligible_available=eligible_available,
            excluded=excluded,
            excluded_available=excluded_available,
        )
        _validate_cross_section_identities(
            scenarios=scenarios,
            leakage_audits=leakage_audits,
            matrix_checks=matrix_checks,
            baseline_checks=baseline_checks,
            expected_eligible_rows=expected_eligible_rows,
        )
        quality_flags = _optional_mapping(quality_summary.get("quality_flags"), "quality flags")
        recorded_flags, recorded_available = _optional_nonnegative_integer(
            quality_flags.get("row_count"), "recorded quality-flag count"
        )
        inspected_flags, inspected_available = _optional_nonnegative_integer(
            quality_summary.get("flags_row_count"), "inspected quality-flag count"
        )
        counts_match = (
            recorded_flags == inspected_flags
            if recorded_available and inspected_available
            else False
        )
        overview = (
            {
                "status": quality_status,
                "eligibleRowCount": eligible,
                "excludedRowCount": excluded,
                "eligibleRowCountAvailable": eligible_available,
                "excludedRowCountAvailable": excluded_available,
                "recordedFlagCount": recorded_flags,
                "inspectedFlagCount": inspected_flags,
                "recordedFlagCountAvailable": recorded_available,
                "inspectedFlagCountAvailable": inspected_available,
                "flagCountMatches": counts_match,
                "errorCount": len(errors),
                "scenarioStatus": scenario_status,
                "matrixStatus": matrix_status,
                "baselineStatus": baseline_status,
                "duplicateStatus": duplicate_status,
                "gridStatus": grid_status,
            },
        )
        available = bool(
            quality_status not in {"absent", "unavailable"}
            or errors
            or scenarios
            or duplicate_rows
            or grid_groups
            or matrix_checks
            or baseline_checks
            or recorded_available
            or inspected_available
        )
        return cls(
            available=available,
            quality_status=quality_status,
            quality_errors=errors,
            scenario_evidence_available=raw_scenarios is not None,
            leakage_evidence_available=scenario_evidence_available,
            duplicate_state_evidence_available=raw_duplicates is not None,
            grid_evidence_available=raw_grid is not None,
            matrix_evidence_available=raw_matrix is not None,
            baseline_evidence_available=raw_baseline is not None,
            quality_overview=overview,
            scenarios=scenarios,
            partitions=partitions,
            leakage_audits=leakage_audits,
            duplicate_state_checks=duplicate_rows,
            grid_groups=grid_groups,
            grid_spacing=grid_spacing,
            grid_phase_counts=grid_phases,
            matrix_checks=matrix_checks,
            matrix_feature_flags=matrix_feature_flags,
            singular_values=singular_values,
            correlated_feature_pairs=correlated_pairs,
            feature_target_correlations=target_correlations,
            baseline_checks=baseline_checks,
            baseline_metrics=baseline_metrics,
            baseline_failures=baseline_failures,
        )


def _scenario_evidence(
    payload: Mapping[str, object],
) -> tuple[dict[str, Mapping[str, object]], bool]:
    audit = payload.get("preparation_audit")
    if audit is None:
        return {}, False
    audit_mapping = _mapping(audit, "private audit evidence")
    if audit_mapping.get("audit_schema_version") != 1:
        raise ValueError("Preparation audit evidence has an unsupported schema version")
    result: dict[str, Mapping[str, object]] = {}
    for item in _mapping_list(audit_mapping.get("scenario_details"), "scenario details"):
        name = _nonempty_text(item.get("name"), "scenario-detail name")
        if name in result:
            raise ValueError(f"Preparation audit scenario detail {name!r} is duplicated")
        result[name] = item
    return result, True


def _scenario_rows(
    value: object,
    evidence: Mapping[str, Mapping[str, object]],
    *,
    evidence_available: bool,
) -> tuple[
    tuple[dict[str, object], ...],
    tuple[dict[str, object], ...],
    tuple[dict[str, object], ...],
    str,
]:
    if value is None:
        if evidence:
            raise ValueError("Preparation audit scenario details have no scenario summary")
        return (), (), (), "not_configured"
    summary = _mapping(value, "scenario summary")
    status = _status(summary.get("status"), default="unreported")
    items = _mapping_list(summary.get("scenarios"), "scenarios")
    declared_count = _nonnegative_integer(summary.get("scenario_count"), "scenario count")
    if declared_count != len(items):
        raise ValueError("Preparation audit scenario count is inconsistent")
    rows: list[dict[str, object]] = []
    partitions: list[dict[str, object]] = []
    leakage: list[dict[str, object]] = []
    names: set[str] = set()
    for order, item in enumerate(items):
        name = _nonempty_text(item.get("name"), "scenario name")
        if name in names:
            raise ValueError(f"Preparation audit scenario {name!r} is duplicated")
        names.add(name)
        counts = _mapping(item.get("partition_counts"), f"partitions for scenario {name}")
        partition_rows = _partition_rows(name, counts)
        partitions.extend(partition_rows)
        transformations = _mapping_list(item.get("transformations"), "scenario transformations")
        detail = evidence.get(name)
        leakage_available = detail is not None and detail.get("state_leakage") is not None
        if leakage_available:
            assert detail is not None
            leakage.append(_leakage_row(name, detail.get("state_leakage")))
        rows.append(
            {
                "name": name,
                "kind": _nonempty_text(item.get("kind"), "scenario kind"),
                "order": order,
                "rowCount": sum(cast(int, row["rowCount"]) for row in partition_rows),
                "partitionCount": len(partition_rows),
                "transformationCount": len(transformations),
                "leakageAvailable": leakage_available,
            }
        )
    unknown_details = sorted(set(evidence) - names)
    missing_details = sorted(names - set(evidence)) if evidence_available else []
    if unknown_details or missing_details:
        raise ValueError(
            "Preparation audit scenario details do not match the scenario summary: "
            + ", ".join([*unknown_details, *missing_details])
        )
    declared_partitions = _nonnegative_integer(
        summary.get("partition_count"), "scenario partition count"
    )
    if declared_partitions != len(partitions):
        raise ValueError("Preparation audit scenario partition count is inconsistent")
    return tuple(rows), tuple(partitions), tuple(leakage), status


def _partition_rows(
    scenario: str,
    counts: Mapping[str, object],
) -> tuple[dict[str, object], ...]:
    values = [
        (
            _nonempty_text(name, "partition name"),
            _nonnegative_integer(count, "partition row count"),
        )
        for name, count in counts.items()
    ]
    values.sort(key=lambda item: (_PARTITION_ORDER.get(item[0], len(_PARTITION_ORDER)), item[0]))
    return tuple(
        {"scenario": scenario, "partition": name, "order": order, "rowCount": count}
        for order, (name, count) in enumerate(values)
    )


def _leakage_row(scenario: str, value: object) -> dict[str, object]:
    leakage = _mapping(value, f"leakage evidence for scenario {scenario}")
    return {
        "scenario": scenario,
        "identityColumn": _nonempty_text(leakage.get("identity_column"), "leakage identity"),
        "duplicateStateGroupCount": _nonnegative_integer(
            leakage.get("duplicate_state_group_count"), "duplicate state group count"
        ),
        "crossPartitionGroupCount": _nonnegative_integer(
            leakage.get("cross_partition_group_count"), "cross-partition group count"
        ),
    }


def _duplicate_state_rows(value: object) -> tuple[tuple[dict[str, object], ...], str]:
    if value is None:
        return (), "unreported"
    summary = _mapping(value, "duplicate-state evidence")
    status = _status(summary.get("status"), default="unreported")
    row = {
        "status": status,
        "groupColumns": _optional_string_list(summary.get("group_columns"), "duplicate groups"),
        "identityColumn": _optional_text(summary.get("identity_column"), "duplicate identity"),
        "countsAvailable": status == "completed",
        "duplicateGroupCount": _optional_count_value(
            summary.get("duplicate_group_count"), "duplicate group count"
        ),
        "duplicateRowCount": _optional_count_value(
            summary.get("duplicate_row_count"), "duplicate row count"
        ),
        "conflictingTargetGroupCount": _optional_count_value(
            summary.get("conflicting_target_group_count"), "conflicting target group count"
        ),
    }
    return (row,), status


def _grid_rows(
    value: object,
) -> tuple[
    tuple[dict[str, object], ...],
    tuple[dict[str, object], ...],
    tuple[dict[str, object], ...],
    str,
]:
    if value is None:
        return (), (), (), "unreported"
    summary = _mapping(value, "structured-grid evidence")
    status = _status(summary.get("status"), default="unreported")
    raw_groups = summary.get("groups")
    if status != "completed":
        if raw_groups is not None and raw_groups != []:
            raise ValueError("Preparation audit skipped structured grid must not contain groups")
        return (), (), (), status
    groups = _mapping_list(raw_groups, "structured-grid groups")
    group_rows: list[dict[str, object]] = []
    spacing_rows: list[dict[str, object]] = []
    phase_rows: list[dict[str, object]] = []
    for order, item in enumerate(groups):
        identity = _mapping(item.get("group"), "structured-grid group identity")
        coverage, coverage_available = _optional_number(
            item.get("coverage_fraction"), "grid coverage fraction"
        )
        phase = _mapping(item.get("phase_boundaries"), "grid phase-boundary evidence")
        phase_status = _status(phase.get("status"), default="unreported")
        group_rows.append(
            {
                "order": order,
                "sourceRunId": _nonempty_text(identity.get("source_run_id"), "grid run ID"),
                "sourceFluid": _nonempty_text(identity.get("source_fluid"), "grid fluid"),
                "backendModel": _nonempty_text(identity.get("backend_model"), "grid model"),
                "rowCount": _nonnegative_integer(item.get("row_count"), "grid row count"),
                "expectedCells": _nonnegative_integer(
                    item.get("expected_cells"), "expected grid cells"
                ),
                "observedCells": _nonnegative_integer(
                    item.get("observed_cells"), "observed grid cells"
                ),
                "missingCells": _nonnegative_integer(
                    item.get("missing_cells"), "missing grid cells"
                ),
                "coverageFraction": coverage,
                "coverageAvailable": coverage_available,
                "repeatedCellCount": _nonnegative_integer(
                    item.get("repeated_cell_count"), "repeated grid-cell count"
                ),
                "repeatedRowCount": _nonnegative_integer(
                    item.get("repeated_row_count"), "repeated grid-row count"
                ),
                "phaseBoundaryStatus": phase_status,
                "multiPhaseCellCount": _optional_count_value(
                    phase.get("multi_phase_cell_count"), "multi-phase cell count"
                ),
                "transitionEdgeCount": _optional_count_value(
                    phase.get("transition_edge_count"), "phase-transition edge count"
                ),
            }
        )
        spacing_rows.extend(_grid_spacing_rows(order, item.get("coordinate_spacing")))
        phase_counts = _optional_mapping(phase.get("phase_counts"), "grid phase counts")
        phase_rows.extend(
            {
                "groupOrder": order,
                "phase": _nonempty_text(name, "grid phase"),
                "count": _nonnegative_integer(count, "grid phase count"),
            }
            for name, count in sorted(phase_counts.items())
        )
    return tuple(group_rows), tuple(spacing_rows), tuple(phase_rows), status


def _grid_spacing_rows(group_order: int, value: object) -> list[dict[str, object]]:
    spacing = _mapping(value, "grid coordinate spacing")
    coordinates = sorted(
        spacing,
        key=lambda name: (_GRID_COORDINATE_ORDER.get(name, len(_GRID_COORDINATE_ORDER)), name),
    )
    rows: list[dict[str, object]] = []
    for order, coordinate in enumerate(coordinates):
        item = _mapping(spacing[coordinate], f"spacing for {coordinate}")
        minimum, minimum_available = _optional_number(item.get("minimum"), "grid minimum")
        maximum, maximum_available = _optional_number(item.get("maximum"), "grid maximum")
        minimum_spacing, minimum_spacing_available = _optional_number(
            item.get("minimum_spacing"), "minimum grid spacing"
        )
        maximum_spacing, maximum_spacing_available = _optional_number(
            item.get("maximum_spacing"), "maximum grid spacing"
        )
        median_spacing, median_spacing_available = _optional_number(
            item.get("median_spacing"), "median grid spacing"
        )
        ratio, ratio_available = _optional_number(
            item.get("maximum_to_minimum_spacing_ratio"), "grid spacing ratio"
        )
        uniform, uniform_available = _optional_boolean(
            item.get("uniform_spacing"), "uniform grid-spacing state"
        )
        rows.append(
            {
                "groupOrder": group_order,
                "coordinate": coordinate,
                "order": order,
                "levelCount": _nonnegative_integer(item.get("level_count"), "grid level count"),
                "minimum": minimum,
                "minimumAvailable": minimum_available,
                "maximum": maximum,
                "maximumAvailable": maximum_available,
                "spacingCount": _nonnegative_integer(
                    item.get("spacing_count"), "grid spacing count"
                ),
                "minimumSpacing": minimum_spacing,
                "minimumSpacingAvailable": minimum_spacing_available,
                "maximumSpacing": maximum_spacing,
                "maximumSpacingAvailable": maximum_spacing_available,
                "medianSpacing": median_spacing,
                "medianSpacingAvailable": median_spacing_available,
                "spacingRatio": ratio,
                "spacingRatioAvailable": ratio_available,
                "uniformSpacing": uniform,
                "uniformSpacingAvailable": uniform_available,
            }
        )
    return rows


def _matrix_rows(
    value: object,
) -> tuple[
    tuple[dict[str, object], ...],
    tuple[dict[str, object], ...],
    tuple[dict[str, object], ...],
    tuple[dict[str, object], ...],
    tuple[dict[str, object], ...],
    str,
]:
    if value is None:
        return (), (), (), (), (), "unreported"
    summary = _mapping(value, "matrix diagnostics")
    status = _status(summary.get("status"), default="unreported")
    fits = _mapping_list(summary.get("fits"), "matrix diagnostic fits")
    checks: list[dict[str, object]] = []
    flags: list[dict[str, object]] = []
    singular_rows: list[dict[str, object]] = []
    pair_rows: list[dict[str, object]] = []
    target_rows: list[dict[str, object]] = []
    for order, fit in enumerate(fits):
        scenario = _nullable_text(fit.get("scenario"), "matrix scenario")
        partition = _nonempty_text(fit.get("fit_partition"), "matrix fit partition")
        features = _string_list(fit.get("feature_columns"), "matrix feature columns")
        targets = _string_list(fit.get("target_columns"), "matrix target columns")
        numerical_rank, rank_available = _optional_nonnegative_integer(
            fit.get("numerical_rank"), "matrix numerical rank"
        )
        feature_fraction, feature_fraction_available = _optional_number(
            fit.get("feature_rank_fraction"), "feature-rank fraction"
        )
        effective_rank, effective_rank_available = _optional_number(
            fit.get("effective_rank"), "effective rank"
        )
        effective_fraction, effective_fraction_available = _optional_number(
            fit.get("effective_rank_fraction"), "effective-rank fraction"
        )
        condition, condition_available = _optional_number(
            fit.get("condition_number"), "condition number"
        )
        tolerance, tolerance_available = _optional_number(
            fit.get("rank_tolerance"), "rank tolerance"
        )
        correlation_threshold, correlation_threshold_available = _optional_number(
            fit.get("correlation_threshold"), "correlation threshold"
        )
        near_constant_threshold, near_constant_threshold_available = _optional_number(
            fit.get("near_constant_relative_spread_threshold"),
            "near-constant threshold",
        )
        checks.append(
            {
                "scenario": scenario,
                "fitPartition": partition,
                "order": order,
                "status": _status(fit.get("status"), default="unreported"),
                "rowCount": _nonnegative_integer(fit.get("row_count"), "matrix row count"),
                "featureCount": len(features),
                "targetCount": len(targets),
                "correlationThreshold": correlation_threshold,
                "correlationThresholdAvailable": correlation_threshold_available,
                "nearConstantThreshold": near_constant_threshold,
                "nearConstantThresholdAvailable": near_constant_threshold_available,
                "numericalRank": numerical_rank,
                "numericalRankAvailable": rank_available,
                "featureRankFraction": feature_fraction,
                "featureRankFractionAvailable": feature_fraction_available,
                "effectiveRank": effective_rank,
                "effectiveRankAvailable": effective_rank_available,
                "effectiveRankFraction": effective_fraction,
                "effectiveRankFractionAvailable": effective_fraction_available,
                "conditionNumber": condition,
                "conditionNumberAvailable": condition_available,
                "conditionNumberInfinite": _optional_boolean_value(
                    fit.get("condition_number_is_infinite"), "infinite condition-number state"
                ),
                "rankTolerance": tolerance,
                "rankToleranceAvailable": tolerance_available,
                "rankToleranceDefinition": _optional_text(
                    fit.get("rank_tolerance_definition"), "rank-tolerance definition"
                ),
            }
        )
        flags.extend(_matrix_feature_rows(scenario, partition, fit))
        singular = _optional_number_list(fit.get("singular_values"), "singular values")
        explained = _optional_number_list(
            fit.get("explained_variance_ratio"), "explained-variance ratios"
        )
        if len(singular) != len(explained):
            raise ValueError("Preparation audit singular values and variance ratios differ")
        singular_rows.extend(
            {
                "scenario": scenario,
                "fitPartition": partition,
                "order": index,
                "singularValue": singular_value,
                "explainedVarianceRatio": explained[index],
            }
            for index, singular_value in enumerate(singular)
        )
        pair_rows.extend(
            _correlated_pair_row(scenario, partition, index, item)
            for index, item in enumerate(
                _optional_mapping_list(
                    fit.get("highly_correlated_feature_pairs"), "correlated feature pairs"
                )
            )
        )
        target_rows.extend(
            _target_correlation_row(scenario, partition, index, item)
            for index, item in enumerate(
                _optional_mapping_list(
                    fit.get("feature_target_correlations"), "feature-target correlations"
                )
            )
        )
    return (
        tuple(checks),
        tuple(flags),
        tuple(singular_rows),
        tuple(pair_rows),
        tuple(target_rows),
        status,
    )


def _matrix_feature_rows(
    scenario: str,
    partition: str,
    fit: Mapping[str, object],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for kind, key in (
        ("constant_feature", "constant_feature_columns"),
        ("constant_target", "constant_target_columns"),
    ):
        rows.extend(
            {
                "scenario": scenario,
                "fitPartition": partition,
                "kind": kind,
                "field": field,
                "order": len(rows),
                "relativeSpread": 0.0,
                "relativeSpreadAvailable": False,
            }
            for field in _optional_string_list(fit.get(key), kind.replace("_", " "))
        )
    for item in _optional_mapping_list(
        fit.get("near_constant_feature_columns"), "near-constant features"
    ):
        rows.append(
            {
                "scenario": scenario,
                "fitPartition": partition,
                "kind": "near_constant_feature",
                "field": _nonempty_text(item.get("field"), "near-constant field"),
                "order": len(rows),
                "relativeSpread": _number(item.get("relative_spread"), "relative spread"),
                "relativeSpreadAvailable": True,
            }
        )
    return rows


def _correlated_pair_row(
    scenario: str,
    partition: str,
    order: int,
    item: Mapping[str, object],
) -> dict[str, object]:
    return {
        "scenario": scenario,
        "fitPartition": partition,
        "order": order,
        "left": _nonempty_text(item.get("left"), "correlated-pair left field"),
        "right": _nonempty_text(item.get("right"), "correlated-pair right field"),
        "correlation": _number(item.get("correlation"), "feature correlation"),
    }


def _target_correlation_row(
    scenario: str,
    partition: str,
    order: int,
    item: Mapping[str, object],
) -> dict[str, object]:
    return {
        "scenario": scenario,
        "fitPartition": partition,
        "order": order,
        "feature": _nonempty_text(item.get("feature"), "correlation feature"),
        "target": _nonempty_text(item.get("target"), "correlation target"),
        "correlation": _number(item.get("correlation"), "feature-target correlation"),
    }


def _baseline_rows(
    value: object,
) -> tuple[
    tuple[dict[str, object], ...],
    tuple[dict[str, object], ...],
    tuple[dict[str, object], ...],
    str,
]:
    if value is None:
        return (), (), (), "unreported"
    summary = _mapping(value, "baseline diagnostics")
    status = _status(summary.get("status"), default="unreported")
    fits = _mapping_list(summary.get("fits"), "baseline diagnostic fits")
    checks: list[dict[str, object]] = []
    metrics: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    for order, fit in enumerate(fits):
        scenario = _nonempty_text(fit.get("scenario"), "baseline scenario")
        feature_columns = _string_list(fit.get("feature_columns"), "baseline feature columns")
        target_columns = _string_list(fit.get("target_columns"), "baseline target columns")
        evaluations = _optional_mapping(
            fit.get("evaluation_row_counts"), "baseline evaluation row counts"
        )
        evaluation_counts = [
            _nonnegative_integer(count, f"baseline {partition} row count")
            for partition, count in sorted(
                evaluations.items(),
                key=lambda item: (
                    _PARTITION_ORDER.get(item[0], len(_PARTITION_ORDER)),
                    item[0],
                ),
            )
        ]
        models = _optional_mapping_list(fit.get("models"), "baseline models")
        train_rows, train_rows_available = _optional_nonnegative_integer(
            fit.get("train_row_count"), "baseline train row count"
        )
        completed_count = 0
        failure_count = 0
        metric_order = 0
        for model in models:
            model_name = _nonempty_text(model.get("model"), "baseline model")
            target = _nonempty_text(model.get("target"), "baseline target")
            model_status = _status(model.get("status"), default="unreported")
            if model_status == "completed":
                completed_count += 1
                model_metrics = _mapping(model.get("metrics"), "baseline metrics")
                if set(model_metrics) != set(evaluations):
                    raise ValueError(
                        "Preparation audit baseline metric partitions do not match "
                        "evaluation row counts"
                    )
                for partition, raw_metrics in sorted(
                    model_metrics.items(),
                    key=lambda item: (
                        _PARTITION_ORDER.get(item[0], len(_PARTITION_ORDER)),
                        item[0],
                    ),
                ):
                    metrics.append(
                        _baseline_metric_row(
                            scenario,
                            model_name,
                            target,
                            partition,
                            metric_order,
                            raw_metrics,
                        )
                    )
                    metric_order += 1
            elif model_status == "failed":
                failure_count += 1
                failures.append(
                    {
                        "scenario": scenario,
                        "model": model_name,
                        "target": target,
                        "order": len(failures),
                        "errorType": _nonempty_text(
                            model.get("error_type"), "baseline failure type"
                        ),
                        "message": _nonempty_text(model.get("message"), "baseline failure message"),
                    }
                )
            else:
                raise ValueError(
                    f"Preparation audit baseline model status {model_status!r} is invalid"
                )
        checks.append(
            {
                "scenario": scenario,
                "order": order,
                "status": _status(fit.get("status"), default="unreported"),
                "library": _optional_text(fit.get("library"), "baseline library"),
                "libraryVersion": _optional_text(
                    fit.get("library_version"), "baseline library version"
                ),
                "featureCount": len(feature_columns),
                "targetCount": len(target_columns),
                "trainRowCount": train_rows,
                "trainRowCountAvailable": train_rows_available,
                "evaluationPartitionCount": len(evaluation_counts),
                "evaluationRowCount": sum(evaluation_counts),
                "completedModelCount": completed_count,
                "failedModelCount": failure_count,
                "policy": _optional_text(fit.get("policy"), "baseline policy"),
            }
        )
    return tuple(checks), tuple(metrics), tuple(failures), status


def _baseline_metric_row(
    scenario: str,
    model: str,
    target: str,
    partition: object,
    order: int,
    value: object,
) -> dict[str, object]:
    item = _mapping(value, "baseline metric")
    r_squared, r_squared_available = _optional_number(item.get("r_squared"), "R-squared")
    return {
        "scenario": scenario,
        "model": model,
        "target": target,
        "partition": _nonempty_text(partition, "baseline metric partition"),
        "order": order,
        "meanAbsoluteError": _number(item.get("mean_absolute_error"), "mean absolute error"),
        "rootMeanSquaredError": _number(
            item.get("root_mean_squared_error"), "root mean squared error"
        ),
        "rSquared": r_squared,
        "rSquaredAvailable": r_squared_available,
        "actualMinimum": _number(item.get("actual_minimum"), "actual minimum"),
        "actualMaximum": _number(item.get("actual_maximum"), "actual maximum"),
        "predictionMinimum": _number(item.get("prediction_minimum"), "prediction minimum"),
        "predictionMaximum": _number(item.get("prediction_maximum"), "prediction maximum"),
    }


def _validate_inspection_row_counts(
    summary: Mapping[str, object],
    *,
    eligible: int,
    eligible_available: bool,
    excluded: int,
    excluded_available: bool,
) -> int | None:
    inspection_counts = _optional_mapping(summary.get("row_counts"), "inspection row counts")
    inspected_eligible = 0
    inspected_eligible_available = False
    for key, report_value, available in (
        ("eligible", eligible, eligible_available),
        ("excluded", excluded, excluded_available),
    ):
        inspected, inspected_available = _optional_nonnegative_integer(
            inspection_counts.get(key), f"inspection {key} row count"
        )
        if available and inspected_available and inspected != report_value:
            raise ValueError(f"Preparation audit {key} row counts are inconsistent")
        if key == "eligible":
            inspected_eligible = inspected
            inspected_eligible_available = inspected_available
    if eligible_available:
        return eligible
    if inspected_eligible_available:
        return inspected_eligible
    return None


def _validate_cross_section_identities(
    *,
    scenarios: tuple[dict[str, object], ...],
    leakage_audits: tuple[dict[str, object], ...],
    matrix_checks: tuple[dict[str, object], ...],
    baseline_checks: tuple[dict[str, object], ...],
    expected_eligible_rows: int | None,
) -> None:
    names = {cast(str, row["name"]) for row in scenarios}
    if expected_eligible_rows is not None:
        for row in scenarios:
            if row["rowCount"] != expected_eligible_rows:
                raise ValueError(
                    f"Preparation audit scenario {row['name']!r} does not contain every "
                    "eligible row"
                )
    for label, rows in (
        ("leakage", leakage_audits),
        ("matrix", matrix_checks),
        ("baseline", baseline_checks),
    ):
        for row in rows:
            scenario = row["scenario"]
            if scenario and scenario not in names:
                raise ValueError(
                    f"Preparation audit {label} scenario {scenario!r} is not finalized"
                )


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"Preparation audit {label} must be a string-keyed mapping")
    return cast(Mapping[str, object], value)


def _optional_mapping(value: object, label: str) -> Mapping[str, object]:
    return {} if value is None else _mapping(value, label)


def _mapping_list(value: object, label: str) -> list[Mapping[str, object]]:
    if not isinstance(value, list):
        raise ValueError(f"Preparation audit {label} must be a list")
    return [_mapping(item, f"{label} entry") for item in value]


def _optional_mapping_list(value: object, label: str) -> list[Mapping[str, object]]:
    return [] if value is None else _mapping_list(value, label)


def _string_list(value: object, label: str) -> list[str]:
    if (
        not isinstance(value, list)
        or not all(isinstance(item, str) and item for item in value)
        or len(set(value)) != len(value)
    ):
        raise ValueError(f"Preparation audit {label} must be unique non-empty text")
    return list(cast(list[str], value))


def _optional_string_list(value: object, label: str) -> list[str]:
    return [] if value is None else _string_list(value, label)


def _optional_ordered_text_list(value: object, label: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise ValueError(f"Preparation audit {label} must be non-empty text")
    return list(cast(list[str], value))


def _optional_number_list(value: object, label: str) -> list[float]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"Preparation audit {label} must be a list")
    return [_number(item, label) for item in value]


def _nonempty_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"Preparation audit {label} must be non-empty text")
    return value


def _optional_text(value: object, label: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError(f"Preparation audit {label} must be text or null")
    return value


def _nullable_text(value: object, label: str) -> str:
    return "" if value is None else _nonempty_text(value, label)


def _status(value: object, *, default: str) -> str:
    return default if value is None else _nonempty_text(value, "status")


def _nonnegative_integer(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"Preparation audit {label} must be a non-negative integer")
    return value


def _optional_nonnegative_integer(value: object, label: str) -> tuple[int, bool]:
    return (0, False) if value is None else (_nonnegative_integer(value, label), True)


def _optional_count_value(value: object, label: str) -> int:
    return _optional_nonnegative_integer(value, label)[0]


def _number(value: object, label: str) -> float:
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise ValueError(f"Preparation audit {label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"Preparation audit {label} must be finite")
    return result


def _optional_number(value: object, label: str) -> tuple[float, bool]:
    return (0.0, False) if value is None else (_number(value, label), True)


def _optional_boolean(value: object, label: str) -> tuple[bool, bool]:
    if value is None:
        return False, False
    if not isinstance(value, bool):
        raise ValueError(f"Preparation audit {label} must be boolean or null")
    return value, True


def _optional_boolean_value(value: object, label: str) -> bool:
    return _optional_boolean(value, label)[0]
