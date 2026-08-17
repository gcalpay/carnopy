from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from carnopy.app.preparation_audit import PreparationAuditProjection
from carnopy.app.preparation_audit_models import PreparationAuditModel


def audit_payload() -> dict[str, object]:
    return {
        "source_kind": "preparation",
        "summary": {
            "row_counts": {"source": 2, "eligible": 2, "excluded": 0},
            "scenarios": {
                "status": "completed",
                "scenario_count": 1,
                "partition_count": 2,
                "scenarios": [
                    {
                        "name": "shuffle",
                        "kind": "shuffle",
                        "partition_counts": {"test": 1, "train": 1},
                        "transformations": [],
                    }
                ],
            },
            "quality": {
                "errors": ["one advisory artifact issue"],
                "summary": {
                    "status": "completed",
                    "row_counts": {"eligible": 2, "excluded": 0},
                    "quality_flags": {"row_count": 1},
                    "flags_row_count": 1,
                    "duplicate_state_candidates": {
                        "status": "skipped_missing_identity_columns",
                        "group_columns": [],
                    },
                    "structured_grid": {
                        "status": "skipped_unsupported_mode",
                        "source_mode": "saturation",
                    },
                    "matrix_diagnostics": {"status": "not_requested", "fits": []},
                    "baseline_diagnostics": {"status": "not_requested", "fits": []},
                },
            },
        },
        "preparation_audit": {
            "audit_schema_version": 1,
            "scenario_details": [
                {
                    "name": "shuffle",
                    "state_leakage": {
                        "identity_column": "source_state_hash",
                        "duplicate_state_group_count": 0,
                        "cross_partition_group_count": 0,
                    },
                }
            ],
        },
    }


def test_audit_model_owns_typed_rows_and_section_availability() -> None:
    projection = PreparationAuditProjection.from_worker_payload(audit_payload())
    model = PreparationAuditModel()

    model.replace(projection)

    assert model.get_available()
    assert model.get_quality_status() == "completed"
    assert model.property("available") is True
    assert model.property("qualityStatus") == "completed"
    assert model.property("scenariosModel") is model.scenarios
    assert model.property("leakageAudits") is model.leakage_audits
    assert model.get_scenario_evidence_available()
    assert model.get_leakage_evidence_available()
    assert model.quality_overview.get(0)["flagCountMatches"] is True
    assert [row["partition"] for row in model.partitions.rows()] == ["train", "test"]
    assert model.leakage_audits.get(0)["crossPartitionGroupCount"] == 0
    assert model.matrix_checks.get_count() == 0
    assert model.matrix_checks.get_available()
    assert model.baseline_checks.get_count() == 0
    assert model.baseline_checks.get_available()


def test_audit_model_clear_removes_rows_and_availability() -> None:
    model = PreparationAuditModel()
    model.replace(PreparationAuditProjection.from_worker_payload(audit_payload()))

    model.clear()

    assert not model.get_available()
    assert model.get_quality_status() == ""
    assert not model.get_scenario_evidence_available()
    assert not model.get_leakage_evidence_available()
    for child in model._models():
        assert child.get_count() == 0
        assert not child.get_available()
