from __future__ import annotations

import copy
from collections.abc import Callable

import pytest

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


def _payload() -> dict[str, object]:
    return {
        "source_kind": "preparation",
        "summary": {
            "row_counts": {"source": 9, "eligible": 8, "excluded": 1},
            "scenarios": {
                "status": "completed",
                "scenario_count": 1,
                "partition_count": 2,
                "scenarios": [
                    {
                        "name": "holdout",
                        "kind": "shuffle",
                        "partition_counts": {"test": 2, "train": 6},
                        "transformations": [
                            {
                                "field": "pressure",
                                "methods": ["standard"],
                            }
                        ],
                    }
                ],
            },
            "quality": {
                "errors": [],
                "summary": {
                    "status": "completed",
                    "row_counts": {"eligible": 8, "excluded": 1},
                    "quality_flags": {
                        "artifact": "data/quality_flags.parquet",
                        "row_count": 2,
                    },
                    "flags_row_count": 2,
                    "duplicate_state_candidates": {
                        "status": "completed",
                        "group_columns": ["fluid", "temperature", "pressure"],
                        "duplicate_group_count": 1,
                        "duplicate_row_count": 2,
                        "conflicting_target_group_count": 0,
                    },
                    "structured_grid": {
                        "status": "completed",
                        "groups": [
                            {
                                "group": {
                                    "source_run_id": "run-1",
                                    "source_fluid": "Propane",
                                    "backend_model": "heos",
                                },
                                "row_count": 8,
                                "expected_cells": 9,
                                "observed_cells": 8,
                                "missing_cells": 1,
                                "coverage_fraction": 8 / 9,
                                "repeated_cell_count": 1,
                                "repeated_row_count": 1,
                                "coordinate_spacing": {
                                    "source_pressure_Pa": {
                                        "level_count": 3,
                                        "minimum": 100000.0,
                                        "maximum": 300000.0,
                                        "spacing_count": 2,
                                        "minimum_spacing": 100000.0,
                                        "maximum_spacing": 100000.0,
                                        "median_spacing": 100000.0,
                                        "maximum_to_minimum_spacing_ratio": 1.0,
                                        "uniform_spacing": True,
                                    },
                                    "source_temperature_K": {
                                        "level_count": 3,
                                        "minimum": 300.0,
                                        "maximum": 320.0,
                                        "spacing_count": 2,
                                        "minimum_spacing": 10.0,
                                        "maximum_spacing": 10.0,
                                        "median_spacing": 10.0,
                                        "maximum_to_minimum_spacing_ratio": 1.0,
                                        "uniform_spacing": True,
                                    },
                                },
                                "phase_boundaries": {
                                    "status": "completed",
                                    "phase_counts": {"liquid": 3, "gas": 5},
                                    "multi_phase_cell_count": 1,
                                    "transition_edge_count": 2,
                                },
                            }
                        ],
                    },
                    "matrix_diagnostics": {
                        "status": "completed",
                        "fits": [
                            {
                                "scenario": "holdout",
                                "fit_partition": "train",
                                "row_count": 6,
                                "feature_columns": [
                                    "pressure",
                                    "pressure_copy",
                                    "constant",
                                    "almost_constant",
                                ],
                                "target_columns": ["mass_density", "constant_target"],
                                "correlation_threshold": 0.99,
                                "near_constant_relative_spread_threshold": 1e-12,
                                "standardization": "population mean and std",
                                "status": "completed",
                                "constant_feature_columns": ["constant"],
                                "near_constant_feature_columns": [
                                    {"field": "almost_constant", "relative_spread": 1e-14}
                                ],
                                "variable_feature_columns": [
                                    "pressure",
                                    "pressure_copy",
                                    "almost_constant",
                                ],
                                "singular_values": [3.0, 1.0],
                                "explained_variance_ratio": [0.9, 0.1],
                                "numerical_rank": 2,
                                "rank_tolerance": 1e-14,
                                "rank_tolerance_definition": "defined tolerance",
                                "feature_rank_fraction": 2 / 3,
                                "effective_rank": 1.4,
                                "effective_rank_fraction": 1.4 / 3,
                                "condition_number": 3.0,
                                "condition_number_is_infinite": False,
                                "highly_correlated_feature_pairs": [
                                    {
                                        "left": "pressure",
                                        "right": "pressure_copy",
                                        "correlation": 1.0,
                                    }
                                ],
                                "constant_target_columns": ["constant_target"],
                                "feature_target_correlations": [
                                    {
                                        "feature": "pressure",
                                        "target": "mass_density",
                                        "correlation": 0.75,
                                    }
                                ],
                            }
                        ],
                    },
                    "baseline_diagnostics": {
                        "status": "completed_with_failures",
                        "fits": [
                            {
                                "scenario": "holdout",
                                "status": "completed_with_failures",
                                "library": "scikit-learn",
                                "library_version": "1.8.0",
                                "feature_columns": ["pressure"],
                                "target_columns": ["mass_density"],
                                "train_row_count": 6,
                                "evaluation_row_counts": {"test": 2},
                                "models": [
                                    {
                                        "model": "ridge",
                                        "target": "mass_density",
                                        "status": "completed",
                                        "metrics": {
                                            "test": {
                                                "mean_absolute_error": 0.1,
                                                "root_mean_squared_error": 0.2,
                                                "r_squared": None,
                                                "actual_minimum": 1.0,
                                                "actual_maximum": 2.0,
                                                "prediction_minimum": 1.1,
                                                "prediction_maximum": 1.9,
                                            }
                                        },
                                    },
                                    {
                                        "model": "hist_gradient_boosting",
                                        "target": "mass_density",
                                        "status": "failed",
                                        "error_type": "ValueError",
                                        "message": "not enough rows",
                                    },
                                ],
                                "policy": "diagnostic metrics only",
                            }
                        ],
                    },
                },
            },
        },
        "preparation_audit": {
            "audit_schema_version": 1,
            "scenario_details": [
                {
                    "name": "holdout",
                    "state_leakage": {
                        "identity_column": "source_state_hash",
                        "duplicate_state_group_count": 1,
                        "cross_partition_group_count": 0,
                    },
                }
            ],
        },
    }


def test_projection_flattens_finalized_audit_evidence_deterministically() -> None:
    projection = PreparationAuditProjection.from_worker_payload(_payload())

    assert projection.available is True
    assert projection.quality_status == "completed"
    assert projection.quality_errors == ()
    assert projection.scenario_evidence_available is True
    assert projection.leakage_evidence_available is True
    assert projection.duplicate_state_evidence_available is True
    assert projection.grid_evidence_available is True
    assert projection.matrix_evidence_available is True
    assert projection.baseline_evidence_available is True
    assert projection.quality_overview[0] == {
        "status": "completed",
        "eligibleRowCount": 8,
        "excludedRowCount": 1,
        "eligibleRowCountAvailable": True,
        "excludedRowCountAvailable": True,
        "recordedFlagCount": 2,
        "inspectedFlagCount": 2,
        "recordedFlagCountAvailable": True,
        "inspectedFlagCountAvailable": True,
        "flagCountMatches": True,
        "errorCount": 0,
        "scenarioStatus": "completed",
        "matrixStatus": "completed",
        "baselineStatus": "completed_with_failures",
        "duplicateStatus": "completed",
        "gridStatus": "completed",
    }
    assert [row["partition"] for row in projection.partitions] == ["train", "test"]
    assert projection.scenarios[0]["leakageAvailable"] is True
    assert projection.leakage_audits[0]["crossPartitionGroupCount"] == 0
    assert projection.grid_spacing[0]["coordinate"] == "source_temperature_K"
    assert [row["phase"] for row in projection.grid_phase_counts] == ["gas", "liquid"]
    assert [row["kind"] for row in projection.matrix_feature_flags] == [
        "constant_feature",
        "constant_target",
        "near_constant_feature",
    ]
    assert projection.singular_values[1]["explainedVarianceRatio"] == pytest.approx(0.1)
    assert projection.correlated_feature_pairs[0]["left"] == "pressure"
    assert projection.feature_target_correlations[0]["target"] == "mass_density"
    assert projection.baseline_checks[0]["failedModelCount"] == 1
    assert projection.baseline_metrics[0]["rSquaredAvailable"] is False
    assert projection.baseline_failures[0]["message"] == "not enough rows"


def test_projection_rows_exactly_match_their_stable_role_contracts() -> None:
    projection = PreparationAuditProjection.from_worker_payload(_payload())
    collections: tuple[
        tuple[tuple[dict[str, object], ...], tuple[str, ...]],
        ...,
    ] = (
        (projection.quality_overview, QUALITY_OVERVIEW_ROLES),
        (projection.scenarios, SCENARIO_ROLES),
        (projection.partitions, PARTITION_ROLES),
        (projection.leakage_audits, LEAKAGE_ROLES),
        (projection.duplicate_state_checks, DUPLICATE_STATE_ROLES),
        (projection.grid_groups, GRID_GROUP_ROLES),
        (projection.grid_spacing, GRID_SPACING_ROLES),
        (projection.grid_phase_counts, GRID_PHASE_ROLES),
        (projection.matrix_checks, MATRIX_CHECK_ROLES),
        (projection.matrix_feature_flags, MATRIX_FEATURE_FLAG_ROLES),
        (projection.singular_values, SINGULAR_VALUE_ROLES),
        (projection.correlated_feature_pairs, CORRELATED_PAIR_ROLES),
        (projection.feature_target_correlations, FEATURE_TARGET_CORRELATION_ROLES),
        (projection.baseline_checks, BASELINE_CHECK_ROLES),
        (projection.baseline_metrics, BASELINE_METRIC_ROLES),
        (projection.baseline_failures, BASELINE_FAILURE_ROLES),
    )

    for rows, roles in collections:
        assert rows
        assert set(rows[0]) == set(roles)


def test_projection_represents_legacy_quality_absence_without_fabricating_rows() -> None:
    projection = PreparationAuditProjection.from_worker_payload(
        {
            "source_kind": "preparation",
            "summary": {
                "quality": {"artifacts": {"report": None, "flags": None}, "summary": {}},
            },
        }
    )

    assert projection.available is False
    assert projection.quality_status == "absent"
    assert projection.scenario_evidence_available is False
    assert projection.leakage_evidence_available is False
    assert projection.quality_overview[0]["status"] == "absent"
    assert projection.scenarios == ()
    assert projection.matrix_checks == ()
    assert projection.baseline_checks == ()


def test_projection_accepts_current_not_requested_and_skipped_sections() -> None:
    payload = _payload()
    summary = _summary(payload)
    summary["scenarios"] = None
    del payload["preparation_audit"]
    quality = _quality_summary(summary)
    quality["duplicate_state_candidates"] = {
        "status": "skipped_missing_identity_columns",
        "group_columns": [],
    }
    quality["structured_grid"] = {
        "status": "skipped_unsupported_mode",
        "source_mode": "saturation",
        "reason": "source sampler metadata is unavailable",
    }
    quality["matrix_diagnostics"] = {"status": "not_requested", "fits": []}
    quality["baseline_diagnostics"] = {"status": "not_requested", "fits": []}

    projection = PreparationAuditProjection.from_worker_payload(payload)

    assert projection.available is True
    assert projection.scenarios == ()
    assert projection.duplicate_state_checks[0]["countsAvailable"] is False
    assert projection.grid_groups == ()
    assert projection.matrix_checks == ()
    assert projection.baseline_checks == ()
    assert projection.quality_overview[0]["gridStatus"] == "skipped_unsupported_mode"


def test_projection_retains_verified_flag_count_when_report_is_unavailable() -> None:
    projection = PreparationAuditProjection.from_worker_payload(
        {
            "source_kind": "preparation",
            "summary": {
                "quality": {
                    "errors": [],
                    "summary": {"status": "unavailable", "flags_row_count": 3},
                },
            },
        }
    )

    assert projection.available is True
    assert projection.quality_overview[0]["inspectedFlagCount"] == 3
    assert projection.quality_overview[0]["recordedFlagCountAvailable"] is False
    assert projection.quality_overview[0]["flagCountMatches"] is False


def test_projection_does_not_invent_unavailable_scenario_leakage() -> None:
    payload = _payload()
    del payload["preparation_audit"]

    projection = PreparationAuditProjection.from_worker_payload(payload)

    assert projection.scenarios[0]["leakageAvailable"] is False
    assert projection.leakage_audits == ()


def test_projection_detaches_list_roles_from_worker_payload() -> None:
    payload = _payload()
    projection = PreparationAuditProjection.from_worker_payload(payload)
    groups = cast_string_list(
        cast_dict(_quality_summary(_summary(payload))["duplicate_state_candidates"])[
            "group_columns"
        ]
    )
    groups.clear()

    assert projection.duplicate_state_checks[0]["groupColumns"] == [
        "fluid",
        "temperature",
        "pressure",
    ]


def test_projection_preserves_verified_report_when_flags_are_inconsistent() -> None:
    payload = _payload()
    summary = _summary(payload)
    quality = _quality_summary(summary)
    quality["flags_row_count"] = 1
    cast_errors = cast_string_list(_quality(summary)["errors"])
    cast_errors.append("quality flags artifact row count is inconsistent")

    projection = PreparationAuditProjection.from_worker_payload(payload)

    assert projection.available is True
    assert projection.quality_overview[0]["flagCountMatches"] is False
    assert projection.quality_overview[0]["errorCount"] == 1


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda payload: cast_dict(_summary(payload)["row_counts"]).update({"eligible": 7}),
            "eligible row counts are inconsistent",
        ),
        (
            lambda payload: cast_dict(_summary(payload)["scenarios"]).update({"scenario_count": 2}),
            "scenario count is inconsistent",
        ),
        (
            lambda payload: cast_dict(
                cast_list(cast_dict(_summary(payload)["scenarios"])["scenarios"])[0][
                    "partition_counts"
                ]
            ).update({"train": 5}),
            "does not contain every eligible row",
        ),
        (
            lambda payload: cast_list(cast_dict(payload["preparation_audit"])["scenario_details"])[
                0
            ].update({"name": "unknown"}),
            "do not match the scenario summary",
        ),
        (
            lambda payload: cast_dict(
                cast_list(
                    cast_dict(_quality_summary(_summary(payload))["matrix_diagnostics"])["fits"]
                )[0]
            ).update({"explained_variance_ratio": [1.0]}),
            "singular values and variance ratios differ",
        ),
    ],
)
def test_projection_rejects_inconsistent_worker_evidence(
    mutate: Callable[[dict[str, object]], None],
    message: str,
) -> None:
    payload = copy.deepcopy(_payload())
    mutate(payload)

    with pytest.raises(ValueError, match=message):
        PreparationAuditProjection.from_worker_payload(payload)


def _summary(payload: dict[str, object]) -> dict[str, object]:
    return cast_dict(payload["summary"])


def _quality(summary: dict[str, object]) -> dict[str, object]:
    return cast_dict(summary["quality"])


def _quality_summary(summary: dict[str, object]) -> dict[str, object]:
    return cast_dict(_quality(summary)["summary"])


def cast_dict(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    return value


def cast_list(value: object) -> list[dict[str, object]]:
    assert isinstance(value, list)
    assert all(isinstance(item, dict) for item in value)
    return value


def cast_string_list(value: object) -> list[str]:
    assert isinstance(value, list)
    assert all(isinstance(item, str) for item in value)
    return value
