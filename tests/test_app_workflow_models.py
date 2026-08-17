from __future__ import annotations

import os
import subprocess
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import Qt

from carnopy.app.workflow_models import (
    CODE_ROLE,
    DOCUMENT_KIND_ROLE,
    FIELD_ID_ROLE,
    ITEM_KEY_ROLE,
    MESSAGE_ROLE,
    NESTED_ROW_ROLE,
    ORIGIN_ROLE,
    PATH_ROLE,
    SECTION_ROLE,
    SEVERITY_ROLE,
    PreparationPlanProjection,
    WorkflowIssue,
    WorkflowIssueModel,
    WorkflowListModel,
)


def _preparation_plan_payload() -> dict[str, object]:
    return {
        "source_row_count": 10,
        "eligible_row_count": 8,
        "excluded_row_count": 2,
        "resolved_semantics": {
            "specific_volume": {
                "column": "specific_volume",
                "unit": "m^3/kg",
                "kind": "numeric",
                "source": "derived",
                "formula": "1 / mass_density",
                "dependencies": ["mass_density"],
                "reference_state_safe": True,
                "array_export_allowed": True,
            },
            "pressure": {
                "column": "pressure_pa",
                "unit": "Pa",
                "kind": "numeric",
                "source": "coordinate",
            },
        },
        "reference_state": {
            "selected_reference_dependent_fields": ["specific_enthalpy"],
            "requires_context_compatibility": True,
            "compatible": True,
            "compatible_context": {
                "reference_state_policy": "coolprop_DEF",
                "backend": "coolprop",
                "backend_model": "heos",
            },
            "contexts": [
                {
                    "artifact": "dataset.parquet",
                    "run_id": "run-1",
                    "backend": "coolprop",
                    "backend_model": "heos",
                    "reference_state_policy": "coolprop_DEF",
                    "reference_state_backend_model": "heos",
                    "reference_state_targets": ["specific_enthalpy"],
                }
            ],
        },
        "exclusion_reason_counts": {"missing_required_value": 2},
        "categories": {"phase": ["gas", "liquid"]},
        "scenarios": [
            {
                "name": "shuffle",
                "kind": "shuffle",
                "partition_counts": {"test": 2, "train": 6},
                "transformations": [
                    {
                        "field": "pressure",
                        "methods": ["log10", "standard"],
                        "output_column": "pressure__log10__standard",
                        "fit_partition": "train",
                        "steps": [
                            {"method": "log10"},
                            {"method": "standard", "mean": 1.0, "std": 0.5},
                        ],
                    }
                ],
                "state_leakage": {
                    "identity_column": "source_state_hash",
                    "duplicate_state_group_count": 1,
                    "cross_partition_group_count": 0,
                },
            }
        ],
        "outputs": {
            "formats": ["parquet", "npy"],
            "array_feasibility": [
                {
                    "scope": "scenario:shuffle:train",
                    "status": "ready",
                    "dtype": "float32",
                    "formats": ["npy"],
                    "feature_shape": [6, 2],
                    "target_shape": [6, 1],
                    "auxiliary_shapes": {"fluid": [6]},
                    "float_conversion": {
                        "features": {
                            "pressure": {
                                "max_abs_error": 0.25,
                                "max_rel_error": 0.01,
                                "mean_abs_error": 0.1,
                            }
                        }
                    },
                }
            ],
        },
        "matrix_diagnostics": [
            {
                "scenario": "shuffle",
                "fit_partition": "train",
                "status": "completed",
                "row_count": 6,
                "feature_columns": ["pressure", "specific_volume"],
                "target_columns": ["specific_enthalpy"],
                "constant_feature_columns": [],
                "near_constant_feature_columns": [],
                "variable_feature_columns": ["pressure", "specific_volume"],
                "numerical_rank": 2,
                "effective_rank": 1.8,
                "condition_number": 3.0,
                "condition_number_is_infinite": False,
                "highly_correlated_feature_pairs": [],
                "feature_target_correlations": [
                    {
                        "feature": "pressure",
                        "target": "specific_enthalpy",
                        "correlation": 0.75,
                    }
                ],
            }
        ],
        "baseline_feasibility": [
            {
                "scenario": "shuffle",
                "status": "ready",
                "library": "scikit-learn",
                "library_version": "1.8.0",
                "feature_columns": ["pressure", "specific_volume"],
                "target_columns": ["specific_enthalpy"],
                "train_shapes": {"features": [6, 2], "targets": [6, 1]},
                "evaluation_shapes": {"test": {"features": [2, 2], "targets": [2, 1]}},
                "estimators": [
                    {
                        "model": "ridge",
                        "target": "specific_enthalpy",
                        "estimator_type": "Pipeline",
                    }
                ],
                "fit_performed": False,
            }
        ],
        "dependency_readiness": {
            "numpy": {"available": True, "version": "2.4.0"},
            "safetensors": {"available": False, "version": None},
        },
    }


def test_preparation_plan_projection_flattens_worker_evidence_deterministically() -> None:
    projection = PreparationPlanProjection.from_worker_payload(_preparation_plan_payload())

    assert (
        projection.source_row_count,
        projection.eligible_row_count,
        projection.excluded_row_count,
    ) == (10, 8, 2)
    assert projection.reference_context_required
    assert projection.reference_context_compatible
    assert projection.reference_policy == "coolprop_DEF"
    assert [row["name"] for row in projection.semantic_fields] == [
        "pressure",
        "specific_volume",
    ]
    assert projection.reference_fields == ({"name": "specific_enthalpy"},)
    assert projection.exclusion_reasons == ({"reason": "missing_required_value", "count": 2},)
    assert projection.categories == (
        {"field": "phase", "value": "gas"},
        {"field": "phase", "value": "liquid"},
    )
    assert projection.scenarios[0] == {
        "name": "shuffle",
        "kind": "shuffle",
        "order": 0,
        "rowCount": 8,
        "partitionCount": 2,
        "transformationCount": 1,
        "duplicateStateGroupCount": 1,
        "crossPartitionGroupCount": 0,
    }
    assert [row["partition"] for row in projection.partitions] == ["train", "test"]
    assert projection.transformations[0]["methods"] == ["log10", "standard"]
    assert projection.leakage_audits[0]["crossPartitionGroupCount"] == 0
    assert projection.array_scopes[0]["scopeKind"] == "scenario_partition"
    assert projection.array_scopes[0]["featureRows"] == 6
    assert projection.array_conversion_errors[0]["maxAbsoluteError"] == 0.25
    assert projection.array_auxiliary_shapes[0]["columnCount"] == 1
    assert projection.matrix_checks[0]["numericalRank"] == 2
    assert projection.matrix_checks[0]["featureTargetCorrelationCount"] == 1
    assert projection.baseline_checks[0]["evaluationRowCount"] == 2
    assert projection.baseline_estimators[0]["estimatorType"] == "Pipeline"
    assert [row["name"] for row in projection.dependencies] == [
        "numpy",
        "safetensors",
    ]


@pytest.mark.parametrize(
    ("change", "match"),
    [
        ({"eligible_row_count": 7}, "row counts are inconsistent"),
        ({"resolved_semantics": []}, "resolved_semantics must be"),
        ({"scenarios": [{}]}, "scenario name"),
        ({"matrix_diagnostics": {}}, "matrix diagnostics"),
    ],
)
def test_preparation_plan_projection_rejects_malformed_worker_evidence(
    change: dict[str, object],
    match: str,
) -> None:
    payload = _preparation_plan_payload()
    payload.update(change)

    with pytest.raises(ValueError, match=match):
        PreparationPlanProjection.from_worker_payload(payload)


def test_preparation_plan_projection_rejects_fitting_during_planning() -> None:
    payload = _preparation_plan_payload()
    baselines = payload["baseline_feasibility"]
    assert isinstance(baselines, list)
    baseline = baselines[0]
    assert isinstance(baseline, dict)
    baseline["fit_performed"] = True

    with pytest.raises(ValueError, match="must not report a fitted baseline"):
        PreparationPlanProjection.from_worker_payload(payload)


def test_workflow_issue_model_exposes_stable_typed_roles() -> None:
    issue = WorkflowIssue(
        origin="schema",
        severity="blocking",
        code="invalid_filter",
        message="A filter value is invalid.",
        document_kind="model_sweep",
        section="comparison_plots",
        field_id="sweep.comparison.active.filters",
        item_key="density-comparison",
        nested_row=2,
        path=("comparison_plots", "plots", 0, "filters", "pressure"),
    )
    model = WorkflowIssueModel()
    count_changes: list[None] = []
    model.count_changed.connect(lambda: count_changes.append(None))

    assert model.replace((issue,))
    assert model.get_count() == 1
    assert count_changes == [None]
    assert not model.replace((issue,))
    index = model.index(0, 0)
    assert model.data(index, int(Qt.ItemDataRole.DisplayRole)) == issue.message
    assert model.data(index, ORIGIN_ROLE) == "schema"
    assert model.data(index, SEVERITY_ROLE) == "blocking"
    assert model.data(index, CODE_ROLE) == "invalid_filter"
    assert model.data(index, MESSAGE_ROLE) == issue.message
    assert model.data(index, DOCUMENT_KIND_ROLE) == "model_sweep"
    assert model.data(index, SECTION_ROLE) == "comparison_plots"
    assert model.data(index, FIELD_ID_ROLE) == "sweep.comparison.active.filters"
    assert model.data(index, ITEM_KEY_ROLE) == "density-comparison"
    assert model.data(index, NESTED_ROW_ROLE) == 2
    assert model.data(index, PATH_ROLE) == [
        "comparison_plots",
        "plots",
        0,
        "filters",
        "pressure",
    ]
    assert {bytes(name).decode("utf-8") for name in model.roleNames().values()} == {
        "origin",
        "severity",
        "code",
        "message",
        "documentKind",
        "section",
        "fieldId",
        "itemKey",
        "nestedRow",
        "path",
    }


def test_workflow_issue_model_count_changes_only_when_length_changes() -> None:
    model = WorkflowIssueModel()
    changes: list[None] = []
    model.count_changed.connect(lambda: changes.append(None))
    first = WorkflowIssue(
        origin="local",
        severity="blocking",
        code="first",
        message="First",
        document_kind="preparation",
        section="plan",
    )
    replacement = WorkflowIssue(
        origin="plan",
        severity="advisory",
        code="replacement",
        message="Replacement",
        document_kind="preparation",
        section="plan",
    )

    assert model.replace((first,))
    assert model.replace((replacement,))
    assert changes == [None]
    assert model.issues == (replacement,)
    assert model.replace(())
    assert changes == [None, None]


def test_workflow_list_model_exposes_only_declared_detached_roles() -> None:
    model = WorkflowListModel(("name", "summary"))
    count_changes: list[None] = []
    model.count_changed.connect(lambda: count_changes.append(None))
    source = {"name": "first", "summary": "Initial", "ignored": "private"}

    assert model.replace((source,))
    source["name"] = "mutated"

    assert model.get_count() == 1
    assert model.get(0) == {"name": "first", "summary": "Initial"}
    assert model.rows() == ({"name": "first", "summary": "Initial"},)
    assert count_changes == [None]
    assert not model.replace(({"name": "first", "summary": "Initial"},))
    assert model.replace(({"name": "first", "summary": "Updated"},))
    assert count_changes == [None]
    assert model.clear()
    assert count_changes == [None, None]


def test_workflow_list_model_detaches_nested_row_values() -> None:
    model = WorkflowListModel(("values",))
    source = {"values": ["original"]}
    assert model.replace((source,))

    source["values"].append("source mutation")
    projected = model.get(0)
    projected["values"].append("consumer mutation")

    assert model.get(0) == {"values": ["original"]}


def test_workflow_models_import_is_qtcore_only_and_scientifically_isolated() -> None:
    code = """
import sys
import carnopy.app.workflow_models
for name in (
    "PySide6.QtWidgets", "CoolProp", "numpy", "pandas", "pyarrow", "matplotlib",
    "carnopy.cli", "carnopy.pipeline",
):
    if name in sys.modules:
        raise SystemExit(name)
"""
    completed = subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
