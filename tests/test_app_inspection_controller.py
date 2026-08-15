from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QEventLoop, QObject, QTimer, Signal
from PySide6.QtWidgets import QApplication

from carnopy.app.client import WorkerClient
from carnopy.app.inspection_controller import (
    SOURCE_PAGE_SIZE,
    InspectionController,
    discover_workspace_sources,
)
from carnopy.app.request_coordinator import DesktopRequestCoordinator, RequestSession
from carnopy.app.workspace import initialize_workspace

REVISION = "a" * 64


class StubSession(QObject):
    completed = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.request_id = uuid4()


class StubOutcome:
    def __init__(
        self,
        request_id: UUID,
        *,
        result: dict[str, object] | None = None,
        failure: dict[str, object] | None = None,
    ) -> None:
        self.request_id = request_id
        self.result_payload = result
        self.failure_payload = failure


class StubCoordinator(QObject):
    busy_changed = Signal(bool)

    def __init__(self) -> None:
        super().__init__()
        self.is_busy = False
        self.session: StubSession | None = None

    def start_request(
        self,
        _owner: str,
        _request_type: str,
        _payload: dict[str, object],
    ) -> RequestSession:
        if self.is_busy:
            raise RuntimeError("request already active")
        self.session = StubSession()
        self.is_busy = True
        self.busy_changed.emit(True)
        return cast(RequestSession, self.session)

    def succeed(self, payload: dict[str, object]) -> None:
        session = self.session
        assert session is not None
        session.completed.emit(StubOutcome(session.request_id, result=payload))
        self.session = None
        self.is_busy = False
        self.busy_changed.emit(False)

    def fail(self, payload: dict[str, object]) -> None:
        session = self.session
        assert session is not None
        session.completed.emit(StubOutcome(session.request_id, failure=payload))
        self.session = None
        self.is_busy = False
        self.busy_changed.emit(False)


def controller_for() -> tuple[InspectionController, DesktopRequestCoordinator]:
    coordinator = DesktopRequestCoordinator(WorkerClient())
    return InspectionController(coordinator), coordinator


def stub_controller_for() -> tuple[InspectionController, StubCoordinator]:
    coordinator = StubCoordinator()
    return InspectionController(cast(DesktopRequestCoordinator, coordinator)), coordinator


def prepare_payload(
    controller: InspectionController,
    source: Path,
    payload: dict[str, object],
) -> None:
    controller._clear_inspection(source=source.resolve(), state="loading")
    controller._accept_inspection_payload(
        {
            "source": str(source.resolve()),
            "revision": REVISION,
            "plot_context": None,
            "tables": [],
            "arrays": [],
            **payload,
        }
    )


def preparation_profile(
    source: Path,
    *,
    revision: str = REVISION,
    source_kind: str = "dataset_run",
) -> dict[str, object]:
    field = {
        "name": "temperature",
        "column": "temperature_K",
        "unit": "K",
        "source": "coordinate",
        "reference_dependent": False,
    }
    return {
        "profile_schema_version": 1,
        "source_path": str(source.resolve()),
        "source_kind": source_kind,
        "inspection_revision": revision,
        "source_identity": {"source_kind": source_kind},
        "completion": {
            "status": "completed",
            "partial": False,
            "included_child_models": [],
            "missing_child_models": [],
        },
        "available_models": ["heos"],
        "declared_models": [],
        "reference_model": "heos",
        "numeric_candidates": [field],
        "target_candidates": [dict(field)],
        "categorical_candidates": [
            {
                "name": "fluid",
                "column": "fluid",
                "unit": None,
                "source": "categorical",
                "reference_dependent": False,
            }
        ],
        "auxiliary_candidates": [
            {
                "name": "run_id",
                "column": "run_id",
                "unit": None,
                "source": "auxiliary",
                "reference_dependent": False,
            }
        ],
        "observed_category_values": {"fluid": ["Propane"]},
        "derived_features": [
            {
                "name": "specific_volume",
                "status": "ready",
                "available": True,
                "ready_row_count": 2,
                "source_row_count": 2,
                "reason": "",
                "reason_codes": [],
                "missing_dependencies": [],
                "dependencies": ["mass_density"],
                "unit": "m^3/kg",
            }
        ],
        "model_holdout": {
            "available": False,
            "reason": "Model holdout scenarios require a model-sweep source.",
        },
        "reference_context": {
            "compatible": True,
            "compatible_context": {
                "reference_state_policy": "coolprop_DEF",
                "backend": "coolprop",
                "backend_model": "heos",
            },
            "contexts": [
                {
                    "artifact": "dataset.parquet",
                    "run_id": "run",
                    "backend": "coolprop",
                    "backend_model": "heos",
                    "reference_state_policy": "coolprop_DEF",
                    "reference_state_backend_model": "heos",
                    "reference_state_targets": ["HEOS::Propane"],
                }
            ],
            "reason_code": "",
            "reason": "",
        },
    }


def finalized_preparation_audit_payload(source: Path) -> dict[str, object]:
    return {
        "source_kind": "preparation",
        "summary": {
            "source": str(source.resolve()),
            "status": "completed",
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
                "errors": [],
                "summary": {
                    "status": "completed",
                    "row_counts": {"eligible": 2, "excluded": 0},
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


def test_workspace_sources_are_direct_bounded_and_newest_first(tmp_path: Path) -> None:
    workspace = initialize_workspace(tmp_path / "workspace")
    for index in range(25):
        path = workspace.outputs / f"source-{index:02d}.csv"
        path.write_text("value\n1\n", encoding="utf-8")
        os.utime(path, ns=(index + 1, index + 1))
    nested = workspace.outputs / "unknown"
    nested.mkdir()
    (nested / "nested.csv").write_text("value\n1\n", encoding="utf-8")
    (workspace.outputs / "linked.csv").symlink_to(workspace.outputs / "source-00.csv")

    candidates = discover_workspace_sources(workspace.outputs)
    assert len(candidates) == 25
    assert [item.path.name for item in candidates[:3]] == [
        "source-24.csv",
        "source-23.csv",
        "source-22.csv",
    ]

    controller, coordinator = controller_for()
    controller.set_workspace(workspace)
    assert controller.workspace_sources_model.get_count() == SOURCE_PAGE_SIZE
    assert controller.get_has_more_workspace_sources()
    controller.reveal_more_sources()
    assert controller.workspace_sources_model.get_count() == 25
    assert not controller.get_has_more_workspace_sources()
    coordinator.shutdown()


def test_generated_run_sources_have_human_readable_identity(tmp_path: Path) -> None:
    workspace = initialize_workspace(tmp_path / "workspace")
    run = workspace.outputs / "20260729T205138Z_property_7718e16a"
    run.mkdir()
    (run / "metadata.json").write_text("{}", encoding="utf-8")

    controller, coordinator = controller_for()
    controller.set_workspace(workspace)

    assert controller.get_workspace_outputs_url() == workspace.outputs.resolve().as_uri()
    assert controller.workspace_sources_model.rows() == (
        {
            "path": str(run.resolve()),
            "name": "Property table · 2026-07-29 20:51 UTC",
            "detail": "Run 7718e16a · dataset run",
            "kindHint": "dataset run",
            "modifiedNs": run.stat().st_mtime_ns,
            "issue": "",
            "inspectable": True,
        },
    )
    coordinator.shutdown()


def test_dataset_projection_keeps_failure_aggregates_independent(tmp_path: Path) -> None:
    source = tmp_path / "dataset.parquet"
    source.touch()
    controller, coordinator = controller_for()
    prepare_payload(
        controller,
        source,
        {
            "source_kind": "dataset",
            "summary": {
                "source": {
                    "requested_path": str(source),
                    "dataset_path": str(source),
                    "format": "parquet",
                    "sha256": "b" * 64,
                    "integrity": "verified",
                },
                "identity": {"mode": "property_table", "run_id": "run"},
                "backend": {"name": "coolprop", "version": "8.0", "model": "heos"},
                "rows": {"total": 7, "valid": 4, "invalid": 3},
                "columns": [
                    {"name": "temperature_K", "dtype": "float64"},
                    {"name": "pressure_Pa", "dtype": "float64"},
                ],
                "phase_counts": {"gas": 4, "liquid": 3},
                "failure_counts": {
                    "layer": {"backend": 3},
                    "code": {"property_failed": 2, "state_failed": 1},
                    "property": {"dynamic_viscosity": 2},
                },
            },
        },
    )

    assert controller.failure_layer_counts_model.rows() == (
        {"failureLayer": "backend", "count": 3},
    )
    assert controller.failure_code_counts_model.rows() == (
        {"code": "property_failed", "count": 2},
        {"code": "state_failed", "count": 1},
    )
    assert controller.failure_property_counts_model.rows() == (
        {"property": "dynamic_viscosity", "count": 2},
    )
    assert tuple(row["key"] for row in controller.row_summary_model.rows()) == (
        "total",
        "valid",
        "invalid",
    )
    assert controller.get_integrity_label() == "Verified recorded artifact"
    coordinator.shutdown()


def test_preparation_eligibility_is_explicit_and_revision_bound(tmp_path: Path) -> None:
    eligible_source = tmp_path / "generated-run"
    eligible_source.mkdir()
    descriptor = {
        "source_path": str(eligible_source.resolve()),
        "source_kind": "dataset_run",
        "inspection_revision": REVISION,
        "controls": {},
        "tables": [],
    }
    controller, coordinator = controller_for()
    prepare_payload(
        controller,
        eligible_source,
        {
            "source_kind": "dataset",
            "summary": {},
            "preparation_eligible": True,
            "preparation_ineligible_reason": "",
            "preparation_source_descriptor": descriptor,
            "preparation_profile": preparation_profile(eligible_source),
        },
    )

    assert controller.get_preparation_eligible()
    assert controller.get_preparation_ineligible_reason() == ""
    assert controller.preparation_source_snapshot() == (
        eligible_source.resolve(),
        REVISION,
        descriptor,
    )
    assert controller.get_preparation_profile_available()
    assert controller.get_preparation_profile_current()
    assert controller.preparation_profile_snapshot() == preparation_profile(eligible_source)

    standalone = tmp_path / "standalone.csv"
    standalone.touch()
    reason = "standalone CSV and Parquet files cannot be used as preparation sources"
    prepare_payload(
        controller,
        standalone,
        {
            "source_kind": "dataset",
            "summary": {},
            "preparation_eligible": False,
            "preparation_ineligible_reason": reason,
            "preparation_source_descriptor": None,
            "preparation_profile": None,
        },
    )

    assert not controller.get_preparation_eligible()
    assert controller.get_preparation_ineligible_reason() == reason
    assert controller.preparation_source_snapshot() is None
    assert controller.preparation_profile_snapshot() is None
    coordinator.shutdown()


def test_preparation_profile_projects_qml_safe_typed_state(tmp_path: Path) -> None:
    source = tmp_path / "generated-run"
    source.mkdir()
    descriptor = {
        "source_path": str(source.resolve()),
        "source_kind": "dataset_run",
        "inspection_revision": REVISION,
        "controls": {},
        "tables": [],
    }
    profile = preparation_profile(source)
    controller, coordinator = controller_for()

    prepare_payload(
        controller,
        source,
        {
            "source_kind": "dataset",
            "summary": {},
            "preparation_eligible": True,
            "preparation_ineligible_reason": "",
            "preparation_source_descriptor": descriptor,
            "preparation_profile": profile,
        },
    )

    assert controller.get_preparation_profile_source_kind() == "dataset_run"
    assert controller.get_preparation_profile_revision() == REVISION
    assert controller.get_preparation_completion_status() == "completed"
    assert not controller.get_preparation_partial_source()
    assert controller.get_preparation_reference_model() == "heos"
    assert not controller.get_preparation_model_holdout_available()
    assert controller.get_preparation_model_holdout_reason()
    assert controller.get_preparation_reference_context_compatible()
    assert controller.get_preparation_reference_context_reason_code() == ""
    assert controller.get_preparation_reference_context_reason() == ""
    assert controller.preparation_models_model.rows() == (
        {
            "name": "heos",
            "available": True,
            "declared": False,
            "missing": False,
            "reference": True,
        },
    )
    assert controller.preparation_numeric_candidates_model.rows() == (
        {
            "name": "temperature",
            "column": "temperature_K",
            "unit": "K",
            "source": "coordinate",
            "referenceDependent": False,
        },
    )
    assert (
        controller.preparation_target_candidates_model.rows()
        == controller.preparation_numeric_candidates_model.rows()
    )
    assert controller.preparation_categorical_candidates_model.rows()[0]["name"] == "fluid"
    assert controller.preparation_auxiliary_candidates_model.rows()[0]["name"] == "run_id"
    assert controller.preparation_observed_categories_model.rows() == (
        {"field": "fluid", "values": ["Propane"], "count": 1},
    )
    assert controller.preparation_derived_features_model.rows()[0] == {
        "name": "specific_volume",
        "status": "ready",
        "available": True,
        "readyRowCount": 2,
        "sourceRowCount": 2,
        "reason": "",
        "reasonCodes": [],
        "missingDependencies": [],
        "dependencies": ["mass_density"],
        "unit": "m^3/kg",
    }
    assert controller.preparation_reference_contexts_model.rows()[0]["artifact"] == (
        "dataset.parquet"
    )

    snapshot = controller.preparation_profile_snapshot()
    assert snapshot is not None
    cast(dict[str, list[str]], snapshot["observed_category_values"])["fluid"].append("n-Butane")
    assert controller.preparation_profile_snapshot() == profile
    controller._mark_stale("preview became stale")
    assert controller.get_preparation_profile_available()
    assert not controller.get_preparation_profile_current()
    assert controller.preparation_profile_snapshot() is None
    coordinator.shutdown()


@pytest.mark.parametrize(
    ("profile_key", "profile_value", "expected_issue"),
    [
        ("source_path", "/another/source", "source path"),
        ("source_kind", "model_sweep", "source kind"),
        ("inspection_revision", "b" * 64, "revision"),
    ],
)
def test_preparation_profile_identity_mismatch_is_rejected(
    tmp_path: Path,
    profile_key: str,
    profile_value: object,
    expected_issue: str,
) -> None:
    source = tmp_path / "generated-run"
    source.mkdir()
    descriptor = {
        "source_path": str(source.resolve()),
        "source_kind": "dataset_run",
        "inspection_revision": REVISION,
        "controls": {},
        "tables": [],
    }
    profile = preparation_profile(source)
    profile[profile_key] = profile_value
    controller, coordinator = controller_for()

    prepare_payload(
        controller,
        source,
        {
            "source_kind": "dataset",
            "summary": {},
            "preparation_eligible": True,
            "preparation_ineligible_reason": "",
            "preparation_source_descriptor": descriptor,
            "preparation_profile": profile,
        },
    )

    assert controller.get_state() == "failed"
    assert expected_issue in controller.get_issue()
    assert not controller.get_preparation_eligible()
    assert not controller.get_preparation_profile_available()
    assert controller.preparation_models_model.get_count() == 0
    coordinator.shutdown()


def test_eligible_inspection_without_profile_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "generated-run"
    source.mkdir()
    controller, coordinator = controller_for()

    prepare_payload(
        controller,
        source,
        {
            "source_kind": "dataset",
            "summary": {},
            "preparation_eligible": True,
            "preparation_ineligible_reason": "",
            "preparation_source_descriptor": {
                "source_path": str(source.resolve()),
                "source_kind": "dataset_run",
                "inspection_revision": REVISION,
            },
        },
    )

    assert controller.get_state() == "failed"
    assert "required typed fields" in controller.get_issue()
    assert controller.preparation_profile_snapshot() is None
    coordinator.shutdown()


def test_arrays_project_each_logical_array_with_its_own_dtype(tmp_path: Path) -> None:
    source = tmp_path / "preparation"
    source.mkdir()
    controller, coordinator = controller_for()
    prepare_payload(
        controller,
        source,
        {
            "source_kind": "preparation",
            "summary": {
                "source": str(source),
                "status": "complete",
                "row_counts": {"source": 12, "eligible": 10, "excluded": 2},
                "quality": {"errors": []},
            },
            "arrays": [
                {
                    "path": "data/features.npz",
                    "format": "npz",
                    "dtype": "float32",
                    "sha256": "c" * 64,
                    "arrays": {
                        "features": {"shape": [10, 3], "dtype": "float32"},
                        "category_codes": {"shape": [10], "dtype": "int64"},
                    },
                },
                {
                    "path": "data/legacy.npy",
                    "format": "npy",
                    "dtype": "float64",
                    "sha256": "d" * 64,
                },
            ],
        },
    )

    assert controller.arrays_model.rows() == (
        {
            "artifactId": "data/features.npz",
            "artifactLabel": "features.npz",
            "format": "npz",
            "artifactSha256": "c" * 64,
            "arrayName": "features",
            "shape": [10, 3],
            "shapeDisplay": "10 x 3",
            "dtype": "float32",
            "metadataAvailable": True,
            "issue": "",
        },
        {
            "artifactId": "data/features.npz",
            "artifactLabel": "features.npz",
            "format": "npz",
            "artifactSha256": "c" * 64,
            "arrayName": "category_codes",
            "shape": [10],
            "shapeDisplay": "10",
            "dtype": "int64",
            "metadataAvailable": True,
            "issue": "",
        },
        {
            "artifactId": "data/legacy.npy",
            "artifactLabel": "legacy.npy",
            "format": "npy",
            "artifactSha256": "d" * 64,
            "arrayName": "",
            "shape": [],
            "shapeDisplay": "",
            "dtype": "",
            "metadataAvailable": False,
            "issue": "Logical array metadata is unavailable for this legacy artifact.",
        },
    )
    coordinator.shutdown()


def test_preparation_audit_is_owned_by_controller_and_cleared_when_stale(
    tmp_path: Path,
) -> None:
    source = tmp_path / "preparation"
    source.mkdir()
    controller, coordinator = controller_for()

    prepare_payload(controller, source, finalized_preparation_audit_payload(source))

    audit = controller.preparation_audit_model
    assert controller.get_state() == "ready"
    assert controller.property("preparationAudit") is audit
    assert audit.get_available()
    assert audit.get_scenario_evidence_available()
    assert audit.get_leakage_evidence_available()
    assert audit.scenarios.rows()[0]["name"] == "shuffle"
    assert [row["partition"] for row in audit.partitions.rows()] == ["train", "test"]
    assert audit.leakage_audits.rows()[0]["crossPartitionGroupCount"] == 0
    assert audit.matrix_checks.get_available()
    assert audit.baseline_checks.get_available()

    controller._mark_stale("inspection revision changed")

    assert controller.get_state() == "stale"
    assert not audit.get_available()
    assert audit.scenarios.get_count() == 0
    assert audit.leakage_audits.get_count() == 0
    assert not controller.preparation_quality_errors_model.get_available()
    coordinator.shutdown()


def test_inconsistent_preparation_audit_is_rejected_before_projection(tmp_path: Path) -> None:
    source = tmp_path / "preparation"
    source.mkdir()
    controller, coordinator = controller_for()
    payload = finalized_preparation_audit_payload(source)
    audit = cast(dict[str, object], payload["preparation_audit"])
    audit["audit_schema_version"] = 2

    prepare_payload(controller, source, payload)

    assert controller.get_state() == "failed"
    assert "unsupported schema version" in controller.get_issue()
    assert not controller.preparation_audit_model.get_available()
    assert controller.preparation_audit_model.scenarios.get_count() == 0
    coordinator.shutdown()


def test_nonpreparation_inspection_cannot_attach_preparation_audit(tmp_path: Path) -> None:
    source = tmp_path / "dataset.parquet"
    source.touch()
    controller, coordinator = controller_for()

    prepare_payload(
        controller,
        source,
        {
            "source_kind": "dataset",
            "summary": {},
            "preparation_audit": {
                "audit_schema_version": 1,
                "scenario_details": [],
            },
        },
    )

    assert controller.get_state() == "failed"
    assert "attached Preparation audit to another source" in controller.get_issue()
    assert not controller.preparation_audit_model.get_available()
    coordinator.shutdown()


def test_first_table_preview_is_queued_after_explicit_inspection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application = QApplication.instance()
    if not isinstance(application, QApplication):
        application = QApplication([])
    source = tmp_path / "dataset.parquet"
    source.touch()
    controller, coordinator = controller_for()
    requested: list[int] = []
    monkeypatch.setattr(
        controller,
        "request_preview_page",
        lambda offset: requested.append(offset) or True,
    )
    controller._clear_inspection(source=source.resolve(), state="loading")
    controller._accept_inspection_payload(
        {
            "source": str(source.resolve()),
            "source_kind": "dataset",
            "revision": REVISION,
            "summary": {},
            "tables": [
                {
                    "id": "dataset",
                    "label": "Dataset",
                    "format": "parquet",
                    "sha256": "e" * 64,
                }
            ],
            "arrays": [],
            "plot_context": None,
        }
    )

    assert requested == []
    application.processEvents()
    assert requested == [0]
    coordinator.shutdown()


def test_obsolete_inspection_failure_cannot_replace_a_newer_source_context(
    tmp_path: Path,
) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    controller, coordinator = stub_controller_for()

    assert controller.inspect_source(str(first))
    controller._source = second.resolve()
    controller._requested_inspection_source = second.resolve()
    controller._state = "loading"
    coordinator.fail({"message": "obsolete inspection failed"})

    assert controller.get_source_path() == str(second.resolve())
    assert controller.get_state() == "loading"
    assert controller.get_issue() == ""


def test_obsolete_preview_failure_cannot_stale_a_newer_preview_context(
    tmp_path: Path,
) -> None:
    source = tmp_path / "dataset.parquet"
    controller, coordinator = stub_controller_for()
    controller._source = source.resolve()
    controller._state = "ready"
    controller._revision = REVISION
    controller._selected_table_id = "dataset"

    assert controller._request_preview_block(0, 0)
    controller._revision = "b" * 64
    controller._selected_table_id = "replacement"
    controller._preview_state = "ready"
    coordinator.fail({"message": "obsolete preview failed"})

    assert controller.get_state() == "ready"
    assert controller.get_preview_state() == "ready"
    assert controller.get_selected_table_id() == "replacement"
    assert controller.get_issue() == ""


def test_preview_payload_must_match_the_requested_worker_block(tmp_path: Path) -> None:
    source = tmp_path / "dataset.parquet"
    controller, coordinator = stub_controller_for()
    controller._source = source.resolve()
    controller._state = "ready"
    controller._revision = REVISION
    controller._selected_table_id = "dataset"

    assert controller._request_preview_block(500, 500)
    coordinator.succeed(
        {
            "table_id": "dataset",
            "block_offset": 0,
            "columns": ["temperature_K"],
            "rows": [[300.0]],
        }
    )

    assert controller.get_state() == "stale"
    assert controller.get_preview_state() == "stale"
    assert "no longer matches" in controller.get_issue()


def test_real_worker_inspection_automatically_loads_first_bounded_preview(
    tmp_path: Path,
) -> None:
    import pandas as pd

    application = QApplication.instance()
    if not isinstance(application, QApplication):
        application = QApplication([])
    source = tmp_path / "dataset-run"
    source.mkdir()
    dataset = source / "dataset.parquet"
    pd.DataFrame(
        {
            "run_id": ["run"],
            "case_id": [0],
            "mode": ["property_table"],
            "fluid": ["Propane"],
            "backend": ["coolprop"],
            "backend_model": ["heos"],
            "backend_version": ["8.0"],
            "phase": ["gas"],
            "backend_phase": ["gas"],
            "valid": [True],
            "failure_layer": [None],
            "failure_code": [None],
            "failure_message": [None],
            "failure_property": [None],
            "backend_error_type": [None],
            "backend_error_message": [None],
            "temperature_K": [300.0],
            "pressure_Pa": [101325.0],
        }
    ).to_parquet(dataset, index=False)
    (source / "metadata.json").write_text(
        json.dumps(
            {
                "run_id": "run",
                "run_status": "completed",
                "backend": "coolprop",
                "backend_model": "heos",
                "reference_state_policy": "coolprop_DEF",
                "reference_state_backend_model": "heos",
                "reference_state_targets": ["HEOS::Propane"],
                "canonical_units": {"temperature_K": "K", "pressure_Pa": "Pa"},
                "artifact_hashes": {
                    "dataset.parquet": hashlib.sha256(dataset.read_bytes()).hexdigest()
                },
            }
        ),
        encoding="utf-8",
    )
    controller, coordinator = controller_for()

    assert controller.inspect_source(str(source))
    loop = QEventLoop()

    def quit_when_ready() -> None:
        if controller.get_state() == "ready" and controller.get_preview_state() == "ready":
            loop.quit()

    controller.state_changed.connect(quit_when_ready)
    QTimer.singleShot(15_000, loop.quit)
    quit_when_ready()
    if loop.isRunning() or controller.get_preview_state() != "ready":
        loop.exec()
    application.processEvents()

    assert controller.get_state() == "ready"
    assert controller.get_source_kind() == "dataset"
    assert controller.get_selected_table_id() == "dataset"
    assert controller.get_preview_state() == "ready"
    assert controller.get_preparation_profile_current()
    assert controller.get_preparation_profile_source_kind() == "dataset_run"
    assert controller.get_preparation_reference_context_compatible()
    assert [row["name"] for row in controller.preparation_numeric_candidates_model.rows()] == [
        "temperature",
        "pressure",
    ]
    assert controller.table_model.total_rows == 1
    assert controller.table_model.first_row == 1
    assert controller.table_model.last_row == 1
    coordinator.shutdown()


def test_importing_inspection_controller_keeps_worker_only_modules_unloaded() -> None:
    code = """
import sys
import carnopy.app.inspection_controller
for name in (
    "carnopy.app.source_inspection",
    "carnopy.app.table_preview",
    "pandas",
    "pyarrow",
    "numpy",
    "CoolProp",
    "matplotlib",
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


def test_desktop_controller_owns_the_single_inspection_controller(
    tmp_path: Path,
) -> None:
    from PySide6.QtCore import QSettings

    from carnopy.app.desktop_controller import DesktopController

    desktop = DesktopController(
        settings=QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    )
    assert desktop.get_inspection_controller() is desktop.inspection_controller
    assert desktop.inspection_controller.coordinator is desktop.request_coordinator
    assert cast(object, desktop.inspection_controller.parent()) is desktop
    assert desktop.shutdown()
