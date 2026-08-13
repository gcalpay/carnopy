from __future__ import annotations

import hashlib
import os
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication, QEvent, QObject, Signal

from carnopy.app.client import TransportOutcome, WorkerClient
from carnopy.app.config_controller import ConfigurationController
from carnopy.app.config_document import (
    ConfigurationDocument,
    new_document,
    serialize_configuration,
    sha256_bytes,
)
from carnopy.app.inspection_controller import InspectionController
from carnopy.app.protocol import EventType, RequestType, WorkerEvent
from carnopy.app.request_coordinator import DesktopRequestCoordinator
from carnopy.app.workflow_controller import (
    PreparationWorkflowController,
    SweepWorkflowController,
)
from carnopy.app.workspace import Workspace, initialize_workspace


class StubTransport(QObject):
    event_received = Signal(object)
    transport_finished = Signal(object)
    stderr_received = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.is_busy = False
        self.request_id: UUID | None = None
        self.request_type: RequestType | None = None
        self.payload: dict[str, object] | None = None
        self.raise_on_start = False
        self.cancelled: list[UUID] = []
        self.force_stopped: list[UUID] = []

    def start_request(
        self,
        request_id: UUID,
        request_type: RequestType,
        payload: Mapping[str, object] | None = None,
    ) -> None:
        if self.raise_on_start:
            raise RuntimeError("simulated start failure")
        if self.is_busy:
            raise RuntimeError("transport is already busy")
        self.is_busy = True
        self.request_id = request_id
        self.request_type = request_type
        self.payload = dict(payload or {})

    def send_cancel(self, request_id: UUID) -> bool:
        accepted = self.is_busy and request_id == self.request_id
        if accepted:
            self.cancelled.append(request_id)
        return accepted

    def force_stop(self, request_id: UUID) -> bool:
        accepted = self.is_busy and request_id == self.request_id
        if accepted:
            self.force_stopped.append(request_id)
        return accepted

    def shutdown(self) -> None:
        if self.is_busy:
            raise RuntimeError("transport is busy")

    def emit_event(self, event_type: EventType, payload: dict[str, object]) -> None:
        request_id = self.request_id
        assert request_id is not None
        self.event_received.emit(
            WorkerEvent(request_id=request_id, type=event_type, payload=payload)
        )

    def finish(
        self,
        *,
        payload: dict[str, object] | None = None,
        terminal_type: EventType = "result",
        force_stopped: bool = False,
    ) -> None:
        request_id = self.request_id
        request_type = self.request_type
        assert request_id is not None
        assert request_type is not None
        terminal = WorkerEvent(
            request_id=request_id,
            type=terminal_type,
            payload=dict(payload or {}),
        )
        self.is_busy = False
        self.request_id = None
        self.request_type = None
        self.transport_finished.emit(
            TransportOutcome(
                request_id=request_id,
                request_type=request_type,
                terminal_event=terminal,
                client_failure=None,
                stderr="",
                exit_code=9 if force_stopped else 0,
                exit_status="crash" if force_stopped else "normal",
                force_stopped=force_stopped,
            )
        )


@pytest.fixture(scope="module")
def application() -> Iterator[QCoreApplication]:
    existing = QCoreApplication.instance()
    app = existing if isinstance(existing, QCoreApplication) else QCoreApplication([])
    yield app
    if type(app) is QCoreApplication:
        app.quit()
        app.deleteLater()
        QCoreApplication.sendPostedEvents(app, QEvent.Type.DeferredDelete)


def coordinator_for() -> tuple[DesktopRequestCoordinator, StubTransport]:
    transport = StubTransport()
    return DesktopRequestCoordinator(cast(WorkerClient, transport)), transport


def _config(workspace: Workspace, name: str = "workflow.yaml") -> Path:
    path = workspace.configs / name
    path.write_text("schema_version: 2\n", encoding="utf-8")
    return path


def _sweep_payload() -> dict[str, Any]:
    return {
        "schema_version": 2,
        "document_type": "model_sweep",
        "backend": {
            "name": "coolprop",
            "models": ["heos", "pr", "srk"],
            "reference_model": "heos",
        },
        "mode": "property_table",
        "fluids": ["Propane"],
        "grid": {
            "temperature": {
                "kind": "linspace",
                "start": 280.0,
                "stop": 340.0,
                "num": 5,
                "unit": "K",
            },
            "pressure": {
                "kind": "linspace",
                "start": 1.0,
                "stop": 5.0,
                "num": 5,
                "unit": "bar",
            },
        },
        "properties": ["mass_density"],
        "outputs": {"dataset_formats": ["csv", "parquet"]},
    }


def _sweep_capabilities() -> dict[str, Any]:
    return {
        "model": "heos",
        "models": ["heos", "pr", "srk"],
        "modes": ["property_table", "saturation_table", "vapor_mass_fraction_table"],
        "units_by_axis": {
            "temperature": ["K"],
            "pressure": ["bar"],
            "vapor_mass_fraction": ["1"],
        },
        "dataset_formats": ["csv", "parquet"],
        "fluids": [{"name": "Propane", "aliases": ["R290"]}],
        "property_catalog": [
            {
                "name": "mass_density",
                "supported_models": ["heos", "pr", "srk"],
            }
        ],
        "reference_dependent_fields": [],
        "visualization": {"categorical_values": {}},
    }


def _saved_sweep_document(workspace: Workspace) -> ConfigurationDocument:
    value = _sweep_payload()
    content = serialize_configuration(value)
    path = workspace.configs / "sweep.yaml"
    path.write_bytes(content)
    return ConfigurationDocument(
        value,
        source_path=path,
        source_sha256=sha256_bytes(content),
        workspace_owned=True,
    )


def _preparation_payload(*, safetensors: bool = False) -> dict[str, Any]:
    outputs: dict[str, Any] = {"formats": ["parquet"]}
    if safetensors:
        outputs = {
            "formats": ["parquet"],
            "parquet": True,
            "arrays": {"formats": ["safetensors"], "dtype": "float32"},
        }
    return {
        "schema_version": 1,
        "document_type": "preparation",
        "source_policy": {"allow_partial_sweep": False},
        "features": {
            "numeric": ["temperature", "pressure", "mass_density"],
            "derived": ["specific_volume"],
        },
        "categorical_features": [
            {
                "field": "phase",
                "encoding": "one_hot",
                "categories": "observed",
            }
        ],
        "targets": ["specific_enthalpy"],
        "auxiliary": ["fluid", "backend_model", "phase", "run_id", "case_id"],
        "outputs": outputs,
    }


def _saved_preparation_document(
    workspace: Workspace,
    *,
    safetensors: bool = False,
) -> ConfigurationDocument:
    value = _preparation_payload(safetensors=safetensors)
    content = serialize_configuration(value)
    path = workspace.configs / "preparation.yaml"
    path.write_bytes(content)
    return ConfigurationDocument(
        value,
        source_path=path,
        source_sha256=sha256_bytes(content),
        workspace_owned=True,
    )


def _finish_load(transport: StubTransport, path: Path) -> str:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    transport.finish(
        payload={
            "config": {"schema_version": 2},
            "source_name": str(path),
            "source_sha256": digest,
        }
    )
    return digest


def _finish_plan(
    transport: StubTransport,
    *,
    digest: str,
    plan_id: str = "b" * 64,
    source_revision: dict[str, object] | None = None,
    preparation_projection: dict[str, object] | None = None,
) -> None:
    payload: dict[str, object] = {
        "plan_id": plan_id,
        "configuration_sha256": digest,
    }
    if source_revision is not None:
        payload["source_revision"] = source_revision
        payload.update(
            preparation_projection
            if preparation_projection is not None
            else _empty_preparation_plan_projection()
        )
    transport.finish(payload=payload)


def _empty_preparation_plan_projection() -> dict[str, object]:
    return {
        "source_row_count": 0,
        "eligible_row_count": 0,
        "excluded_row_count": 0,
        "resolved_semantics": {},
        "reference_state": {
            "selected_reference_dependent_fields": [],
            "requires_context_compatibility": False,
            "compatible": True,
            "contexts": [],
        },
        "exclusion_reason_counts": {},
        "categories": {},
        "scenarios": [],
        "outputs": {
            "formats": ["parquet"],
            "array_feasibility": [{"scope": "table", "status": "not_requested"}],
        },
        "matrix_diagnostics": None,
        "baseline_feasibility": None,
        "dependency_readiness": {},
    }


def _rich_preparation_plan_projection() -> dict[str, object]:
    return {
        "source_row_count": 4,
        "eligible_row_count": 3,
        "excluded_row_count": 1,
        "resolved_semantics": {
            "pressure": {
                "column": "pressure",
                "unit": "Pa",
                "kind": "numeric",
                "source": "coordinate",
            },
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
                    "run_id": "run",
                    "backend": "coolprop",
                    "backend_model": "heos",
                    "reference_state_policy": "coolprop_DEF",
                    "reference_state_backend_model": "heos",
                    "reference_state_targets": ["specific_enthalpy"],
                }
            ],
        },
        "exclusion_reason_counts": {"missing_required_value": 1},
        "categories": {"phase": ["gas", "liquid"]},
        "scenarios": [
            {
                "name": "shuffle",
                "kind": "shuffle",
                "partition_counts": {"train": 2, "test": 1},
                "transformations": [
                    {
                        "field": "pressure",
                        "methods": ["standard"],
                        "output_column": "pressure__standard",
                        "fit_partition": "train",
                        "steps": [{"method": "standard", "mean": 2.0, "std": 1.0}],
                    }
                ],
                "state_leakage": {
                    "identity_column": "source_state_hash",
                    "duplicate_state_group_count": 0,
                    "cross_partition_group_count": 0,
                },
            }
        ],
        "outputs": {
            "formats": ["parquet", "npy"],
            "array_feasibility": [
                {
                    "scope": "table",
                    "status": "ready",
                    "dtype": "float32",
                    "formats": ["npy"],
                    "feature_shape": [3, 2],
                    "target_shape": [3, 1],
                    "auxiliary_shapes": {},
                    "float_conversion": {
                        "features": {
                            "pressure": {
                                "max_abs_error": 0.25,
                                "max_rel_error": 0.01,
                                "mean_abs_error": 0.1,
                            }
                        },
                        "targets": {},
                    },
                }
            ],
        },
        "matrix_diagnostics": [
            {
                "scenario": "shuffle",
                "fit_partition": "train",
                "status": "completed",
                "row_count": 2,
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
                "feature_target_correlations": [],
            }
        ],
        "baseline_feasibility": None,
        "dependency_readiness": {"numpy": {"available": True, "version": "2.4.0"}},
    }


def _finish_execution(
    transport: StubTransport,
    output_directory: Path,
    *,
    run_id: str = "workflow-run",
) -> None:
    transport.finish(
        payload={
            "run_id": run_id,
            "output_directory": str(output_directory),
            "status": "completed",
        }
    )


def _accept_preparation_inspection(
    inspection: InspectionController,
    source: Path,
    *,
    revision: str,
    complete_profile: bool = True,
) -> dict[str, object]:
    descriptor: dict[str, object] = {
        "source_path": str(source.resolve()),
        "source_kind": "dataset_run",
        "inspection_revision": revision,
        "controls": {},
        "tables": [],
    }
    numeric_names = (
        ["temperature", "pressure", "mass_density", "specific_enthalpy"]
        if complete_profile
        else ["pressure", "specific_enthalpy"]
    )
    numeric_candidates = [
        {
            "name": name,
            "column": name,
            "unit": "K" if name == "temperature" else None,
            "source": ("coordinate" if name in {"temperature", "pressure"} else "property"),
            "reference_dependent": name == "specific_enthalpy",
        }
        for name in numeric_names
    ]
    profile: dict[str, object] = {
        "profile_schema_version": 1,
        "source_path": str(source.resolve()),
        "source_kind": "dataset_run",
        "inspection_revision": revision,
        "source_identity": {"source_kind": "dataset_run"},
        "completion": {
            "status": "completed",
            "partial": False,
            "included_child_models": [],
            "missing_child_models": [],
        },
        "available_models": ["heos"],
        "declared_models": [],
        "reference_model": "heos",
        "numeric_candidates": numeric_candidates,
        "target_candidates": numeric_candidates,
        "categorical_candidates": [
            {
                "name": "phase",
                "column": "phase",
                "unit": None,
                "source": "categorical",
                "reference_dependent": False,
            }
        ],
        "auxiliary_candidates": [
            {
                "name": name,
                "column": name,
                "unit": None,
                "source": "auxiliary",
                "reference_dependent": False,
            }
            for name in ("fluid", "backend_model", "phase", "run_id", "case_id")
        ],
        "observed_category_values": {"phase": ["gas", "liquid"]},
        "derived_features": [
            {
                "name": "specific_volume",
                "status": "ready" if complete_profile else "unavailable",
                "available": complete_profile,
                "reason": "" if complete_profile else "Density is unavailable.",
                "ready_row_count": 10 if complete_profile else 0,
                "source_row_count": 10,
                "reason_codes": [] if complete_profile else ["missing_dependency"],
                "missing_dependencies": [] if complete_profile else ["mass_density"],
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
                    "reference_state_targets": [],
                }
            ],
            "reason_code": "",
            "reason": "",
        },
    }
    inspection._clear_inspection(source=source.resolve(), state="loading")
    inspection._accept_inspection_payload(
        {
            "source": str(source.resolve()),
            "source_kind": "dataset",
            "revision": revision,
            "summary": {},
            "tables": [],
            "arrays": [],
            "plot_context": None,
            "preparation_eligible": True,
            "preparation_ineligible_reason": "",
            "preparation_source_descriptor": descriptor,
            "preparation_profile": profile,
        }
    )
    return descriptor


def test_sweep_planning_uses_the_global_configuration_snapshot(
    tmp_path: Path,
    application: QCoreApplication,
) -> None:
    del application
    workspace = initialize_workspace(tmp_path / "workspace")
    coordinator, transport = coordinator_for()
    configuration = ConfigurationController(coordinator)
    configuration.set_workspace(workspace)
    assert transport.request_type == "describe_capabilities"
    transport.finish(payload=_sweep_capabilities())
    document = _saved_sweep_document(workspace)
    assert configuration.open_document(document)

    controller = SweepWorkflowController(
        coordinator,
        configuration_controller=configuration,
    )
    controller.set_workspace(workspace)
    saved_bytes = document.yaml_bytes
    digest = sha256_bytes(saved_bytes)

    assert controller.loaded_config is None
    assert controller.config_path is None
    assert controller.config_sha256 == ""
    assert controller.can_plan
    assert controller.plan_blocking_reasons.issues == ()
    assert controller.plan()
    assert transport.request_type == "plan_sweep"
    assert transport.payload == {
        "config_path": str(document.source_path),
        "expected_config_sha256": digest,
        "configs_root": str(workspace.configs),
    }
    _finish_plan(transport, digest=digest)

    assert controller.get_plan_current()
    assert controller.can_execute
    accepted_plan = controller.current_plan
    output = workspace.outputs / "sweep-output"
    output.mkdir()
    assert controller.execute()
    assert transport.payload == {
        "config_path": str(document.source_path),
        "expected_config_sha256": digest,
        "configs_root": str(workspace.configs),
        "expected_plan_id": "b" * 64,
        "output_root": str(workspace.outputs),
    }
    _finish_execution(transport, output)
    assert controller.get_result_relation() == "current"

    assert configuration.sweep_draft.set_reference_model("pr")
    assert configuration.get_dirty()
    assert controller.current_plan == accepted_plan
    assert not controller.get_plan_current()
    assert not controller.can_plan
    assert not controller.can_execute
    assert controller.get_result_relation() == "stale"
    assert [issue.code for issue in controller.execution_blocking_reasons.issues] == [
        "plan_configuration_changed",
        "saved_configuration_unavailable",
    ]

    assert configuration.sweep_draft.set_reference_model("heos")
    assert not configuration.get_dirty()
    assert controller.get_plan_current()
    assert controller.can_execute
    assert controller.get_result_relation() == "current"

    assert configuration.sweep_draft.begin_add_comparison()
    assert not controller.get_plan_current()
    assert not controller.can_plan
    assert not controller.can_execute
    assert controller.get_result_relation() == "stale"
    assert configuration.sweep_draft.cancel_comparison()
    assert controller.get_plan_current()
    assert controller.get_result_relation() == "current"

    dataset = _sweep_payload()
    dataset["document_type"] = "dataset"
    dataset["backend"] = {"name": "coolprop", "model": "heos"}
    assert configuration.open_document(new_document(dataset))
    assert configuration.get_document_kind() == "dataset"
    assert not controller.get_plan_current()
    assert not controller.can_plan
    assert controller.get_result_relation() == "unrelated"
    [reason] = controller.plan_blocking_reasons.issues
    assert reason.code == "saved_configuration_required"

    assert configuration.open_document(document)
    assert controller.get_plan_current()
    assert controller.get_result_relation() == "current"
    assert controller.plan()
    assert not configuration.get_can_edit()
    assert configuration.sweep_draft.set_reference_model("pr")
    _finish_plan(transport, digest=digest, plan_id="c" * 64)

    assert controller.state == "failed"
    assert controller.failure["code"] == "stale_plan"
    assert controller.current_plan == accepted_plan
    assert not controller.get_plan_current()
    assert configuration.sweep_draft.set_reference_model("heos")
    assert controller.get_plan_current()
    coordinator.shutdown()


def test_preparation_planning_uses_global_configuration_and_bound_source(
    tmp_path: Path,
    application: QCoreApplication,
) -> None:
    del application
    workspace = initialize_workspace(tmp_path / "workspace")
    coordinator, transport = coordinator_for()
    configuration = ConfigurationController(coordinator)
    configuration.set_workspace(workspace)
    assert transport.request_type == "describe_capabilities"
    transport.finish(payload=_sweep_capabilities())
    document = _saved_preparation_document(workspace)
    assert configuration.open_document(document)
    inspection = InspectionController(coordinator)
    controller = PreparationWorkflowController(
        coordinator,
        inspection,
        configuration_controller=configuration,
    )
    controller.set_workspace(workspace)
    source = workspace.outputs / "dataset-run"
    source.mkdir()
    revision = "a" * 64
    descriptor = _accept_preparation_inspection(
        inspection,
        source,
        revision=revision,
    )
    assert controller.bind_inspected_source()
    bound = controller.bound_source_snapshot()
    assert bound is not None
    assert configuration.preparation_draft.apply_source_profile(bound[3])
    digest = sha256_bytes(document.yaml_bytes)

    assert controller.loaded_config is None
    assert controller.config_path is None
    assert controller.config_sha256 == ""
    assert controller.can_plan
    assert controller.plan_blocking_reasons.issues == ()
    assert controller.plan()
    assert transport.request_type == "plan_preparation"
    assert transport.payload == {
        "config_path": str(document.source_path),
        "expected_config_sha256": digest,
        "configs_root": str(workspace.configs),
        "source_path": str(source.resolve()),
        "inspection_revision": revision,
        "inspection_descriptor": descriptor,
    }
    _finish_plan(
        transport,
        digest=digest,
        source_revision={
            "inspection_revision": revision,
            "inspection_descriptor": descriptor,
            "consumed_source": {},
        },
    )

    assert controller.get_plan_current()
    assert controller.can_execute
    assert configuration.preparation_draft.set_allow_partial_sweep(True)
    assert configuration.get_dirty()
    assert not controller.get_plan_current()
    assert not controller.can_plan
    assert configuration.preparation_draft.set_allow_partial_sweep(False)
    assert not configuration.get_dirty()
    assert controller.get_plan_current()
    coordinator.shutdown()


def test_preparation_planning_blocks_source_and_dependency_issues_before_worker(
    tmp_path: Path,
    application: QCoreApplication,
) -> None:
    del application
    workspace = initialize_workspace(tmp_path / "workspace")
    coordinator, transport = coordinator_for()
    configuration = ConfigurationController(coordinator)
    configuration.set_workspace(workspace)
    transport.finish(payload=_sweep_capabilities())
    document = _saved_preparation_document(workspace, safetensors=True)
    assert configuration.open_document(document)
    inspection = InspectionController(coordinator)
    controller = PreparationWorkflowController(
        coordinator,
        inspection,
        configuration_controller=configuration,
    )
    controller.set_workspace(workspace)
    source = workspace.outputs / "dataset-run"
    source.mkdir()
    first_revision = "a" * 64
    _accept_preparation_inspection(
        inspection,
        source,
        revision=first_revision,
        complete_profile=False,
    )
    assert controller.bind_inspected_source()
    bound = controller.bound_source_snapshot()
    assert bound is not None
    assert configuration.preparation_draft.apply_source_profile(bound[3])

    assert not controller.can_plan
    assert [issue.code for issue in controller.plan_blocking_reasons.issues] == [
        "preparation_source_incompatible",
        "preparation_dependency_unavailable",
    ]
    source_issue, dependency_issue = controller.plan_blocking_reasons.issues
    assert source_issue.origin == "source"
    assert source_issue.field_id == "preparation.source"
    assert dependency_issue.origin == "dependency"
    assert dependency_issue.field_id == "preparation.outputs"
    assert not controller.plan()
    assert transport.request_type is None
    assert controller.get_failure_code() == "plan_unavailable"
    assert "unavailable in the bound source" in controller.get_failure_message()

    second_revision = "c" * 64
    descriptor = _accept_preparation_inspection(
        inspection,
        source,
        revision=second_revision,
    )
    assert controller.bind_inspected_source()
    bound = controller.bound_source_snapshot()
    assert bound is not None
    assert configuration.preparation_draft.apply_source_profile(bound[3])
    [reason] = controller.plan_blocking_reasons.issues
    assert reason.code == "preparation_dependency_unavailable"
    assert not controller.plan()
    assert transport.request_type is None
    assert "carnopy[ml]" in controller.get_failure_message()

    configuration.preparation_draft.apply_capabilities(
        {
            "workflows": {
                "preparation": {
                    "safetensors": {"available": True},
                    "baseline_diagnostics": {"available": False},
                }
            }
        }
    )
    assert controller.can_plan
    assert controller.plan()
    digest = sha256_bytes(document.yaml_bytes)
    _finish_plan(
        transport,
        digest=digest,
        source_revision={
            "inspection_revision": second_revision,
            "inspection_descriptor": descriptor,
            "consumed_source": {},
        },
    )
    assert controller.can_execute

    configuration.preparation_draft.apply_capabilities(_sweep_capabilities())
    assert not controller.can_execute
    assert [issue.code for issue in controller.execution_blocking_reasons.issues] == [
        "preparation_dependency_unavailable"
    ]
    coordinator.shutdown()


def test_preparation_plan_projects_typed_evidence_and_retains_it_while_stale(
    tmp_path: Path,
    application: QCoreApplication,
) -> None:
    del application
    workspace = initialize_workspace(tmp_path / "workspace")
    replacement_workspace = initialize_workspace(tmp_path / "replacement-workspace")
    coordinator, transport = coordinator_for()
    configuration = ConfigurationController(coordinator)
    configuration.set_workspace(workspace)
    transport.finish(payload=_sweep_capabilities())
    document = _saved_preparation_document(workspace)
    assert configuration.open_document(document)
    inspection = InspectionController(coordinator)
    controller = PreparationWorkflowController(
        coordinator,
        inspection,
        configuration_controller=configuration,
    )
    controller.set_workspace(workspace)
    source = workspace.outputs / "dataset-run"
    source.mkdir()
    revision = "a" * 64
    descriptor = _accept_preparation_inspection(
        inspection,
        source,
        revision=revision,
    )
    assert controller.bind_inspected_source()
    bound = controller.bound_source_snapshot()
    assert bound is not None
    assert configuration.preparation_draft.apply_source_profile(bound[3])
    digest = sha256_bytes(document.yaml_bytes)

    assert controller.plan()
    _finish_plan(
        transport,
        digest=digest,
        source_revision={
            "inspection_revision": revision,
            "inspection_descriptor": descriptor,
            "consumed_source": {},
        },
        preparation_projection=_rich_preparation_plan_projection(),
    )

    plan = controller.preparation_plan_model
    assert plan.get_source_row_count() == 4
    assert plan.get_eligible_row_count() == 3
    assert plan.get_excluded_row_count() == 1
    assert plan.get_reference_context_required()
    assert plan.get_reference_context_compatible()
    assert plan.get_reference_policy() == "coolprop_DEF"
    assert plan.semantic_fields.rows()[0]["name"] == "pressure"
    assert plan.exclusion_reasons.rows() == ({"reason": "missing_required_value", "count": 1},)
    assert plan.scenarios.get(0)["rowCount"] == 3
    assert [row["partition"] for row in plan.partitions.rows()] == [
        "train",
        "test",
    ]
    assert plan.transformations.get(0)["fitPartition"] == "train"
    assert plan.leakage_audits.get(0)["crossPartitionGroupCount"] == 0
    assert plan.array_feasibility.get(0)["featureColumns"] == 2
    assert plan.array_conversion_errors.get(0)["field"] == "pressure"
    assert plan.matrix_diagnostics.get(0)["numericalRank"] == 2
    assert plan.dependencies.get(0) == {
        "name": "numpy",
        "available": True,
        "version": "2.4.0",
    }
    assert controller.property("preparationPlan") is plan
    assert plan.property("semanticFields") is plan.semantic_fields
    accepted_plan = controller.current_plan
    accepted_semantics = plan.semantic_fields.rows()

    assert configuration.preparation_draft.set_allow_partial_sweep(True)
    assert not controller.get_plan_current()
    assert controller.current_plan == accepted_plan
    assert plan.semantic_fields.rows() == accepted_semantics
    assert configuration.preparation_draft.set_allow_partial_sweep(False)
    assert controller.get_plan_current()

    assert controller.plan()
    transport.finish(
        payload={
            "plan_id": "c" * 64,
            "configuration_sha256": digest,
            "source_revision": {
                "inspection_revision": revision,
                "inspection_descriptor": descriptor,
                "consumed_source": {},
            },
        }
    )
    assert controller.get_failure_code() == "stale_plan"
    assert "source row count" in controller.get_failure_message()
    assert controller.current_plan == accepted_plan
    assert plan.semantic_fields.rows() == accepted_semantics

    controller.set_workspace(replacement_workspace)
    assert controller.current_plan is None
    assert plan.get_source_row_count() == 0
    assert plan.semantic_fields.rows() == ()
    assert plan.scenarios.rows() == ()
    coordinator.shutdown()


def test_preparation_execution_retains_global_snapshot_and_bound_source_during_edits(
    tmp_path: Path,
    application: QCoreApplication,
) -> None:
    del application
    workspace = initialize_workspace(tmp_path / "workspace")
    coordinator, transport = coordinator_for()
    configuration = ConfigurationController(coordinator)
    configuration.set_workspace(workspace)
    transport.finish(payload=_sweep_capabilities())
    document = _saved_preparation_document(workspace)
    assert configuration.open_document(document)
    inspection = InspectionController(coordinator)
    controller = PreparationWorkflowController(
        coordinator,
        inspection,
        configuration_controller=configuration,
    )
    controller.set_workspace(workspace)
    source = workspace.outputs / "dataset-run"
    source.mkdir()
    revision = "a" * 64
    descriptor = _accept_preparation_inspection(
        inspection,
        source,
        revision=revision,
    )
    assert controller.bind_inspected_source()
    bound = controller.bound_source_snapshot()
    assert bound is not None
    assert configuration.preparation_draft.apply_source_profile(bound[3])
    saved_bytes = document.yaml_bytes
    digest = sha256_bytes(saved_bytes)
    assert controller.plan()
    _finish_plan(
        transport,
        digest=digest,
        source_revision={
            "inspection_revision": revision,
            "inspection_descriptor": descriptor,
            "consumed_source": {},
        },
    )

    output = workspace.outputs / "preparation-output"
    finalized: list[Path] = []
    controller.output_finalized.connect(finalized.append)
    assert controller.execute()
    expected_payload = {
        "config_path": str(document.source_path),
        "expected_config_sha256": digest,
        "configs_root": str(workspace.configs),
        "expected_plan_id": "b" * 64,
        "output_root": str(workspace.outputs),
        "source_path": str(source.resolve()),
        "inspection_revision": revision,
        "inspection_descriptor": descriptor,
    }
    assert transport.request_type == "execute_preparation"
    assert transport.payload == expected_payload
    transport.emit_event("accepted", {})
    transport.emit_event("phase", {"name": "preparation", "cancellable": True})
    transport.emit_event("progress", {"completed": 4, "total": 10})

    replacement = workspace.outputs / "replacement-run"
    replacement.mkdir()
    _accept_preparation_inspection(
        inspection,
        replacement,
        revision="c" * 64,
    )
    assert configuration.get_can_edit()
    assert configuration.preparation_draft.set_allow_partial_sweep(True)
    assert configuration.preparation_draft.begin_add_scenario()
    assert configuration.get_dirty()
    assert not controller.bind_inspected_source()
    assert controller.get_bound_source_path() == str(source.resolve())
    assert controller.get_operation_active()
    assert transport.payload == expected_payload

    _finish_execution(transport, output, run_id="preparation-run")

    assert controller.state == "succeeded"
    assert finalized == [output]
    assert controller.get_result_output_directory() == str(output)
    assert controller.get_result_relation() == "stale"
    assert configuration.preparation_draft.get_has_active_scenario_edit()
    assert controller.get_progress_completed() == 4
    assert controller.get_progress_total() == 10
    coordinator.shutdown()


def test_preparation_execution_uses_shared_cancel_force_and_finalization_policy(
    tmp_path: Path,
    application: QCoreApplication,
) -> None:
    del application
    workspace = initialize_workspace(tmp_path / "workspace")
    coordinator, transport = coordinator_for()
    configuration = ConfigurationController(coordinator)
    configuration.set_workspace(workspace)
    transport.finish(payload=_sweep_capabilities())
    document = _saved_preparation_document(workspace)
    assert configuration.open_document(document)
    inspection = InspectionController(coordinator)
    controller = PreparationWorkflowController(
        coordinator,
        inspection,
        configuration_controller=configuration,
    )
    controller.set_workspace(workspace)
    source = workspace.outputs / "dataset-run"
    source.mkdir()
    revision = "a" * 64
    descriptor = _accept_preparation_inspection(
        inspection,
        source,
        revision=revision,
    )
    assert controller.bind_inspected_source()
    bound = controller.bound_source_snapshot()
    assert bound is not None
    assert configuration.preparation_draft.apply_source_profile(bound[3])
    digest = sha256_bytes(document.yaml_bytes)
    assert controller.plan()
    _finish_plan(
        transport,
        digest=digest,
        source_revision={
            "inspection_revision": revision,
            "inspection_descriptor": descriptor,
            "consumed_source": {},
        },
    )

    assert controller.execute()
    request_id = transport.request_id
    assert request_id is not None
    transport.emit_event("accepted", {})
    transport.emit_event("phase", {"name": "preparation", "cancellable": True})
    assert controller.get_cancellation_available()
    assert controller.cancel()
    assert transport.cancelled == [request_id]
    coordinator._enable_delayed_force_stop()
    assert controller.get_force_stop_available()
    assert controller.force_stop()
    assert transport.force_stopped == [request_id]
    transport.finish(
        terminal_type="error",
        payload={
            "category": "process",
            "code": "force_stopped",
            "message": "worker process was force-stopped",
        },
        force_stopped=True,
    )
    assert controller.state == "force_stopped"

    assert controller.execute()
    transport.emit_event("accepted", {})
    transport.emit_event(
        "phase",
        {
            "name": "finalization",
            "cancellable": False,
            "termination_protected": True,
        },
    )
    assert controller.get_protected_finalization()
    assert not controller.cancel()
    coordinator._enable_delayed_force_stop()
    assert not controller.get_force_stop_available()
    assert not controller.force_stop()
    _finish_execution(transport, workspace.outputs / "finalized-preparation")
    assert controller.state == "succeeded"
    assert not controller.get_operation_active()
    coordinator.shutdown()


def test_sweep_execution_retains_its_global_snapshot_while_the_draft_changes(
    tmp_path: Path,
    application: QCoreApplication,
) -> None:
    del application
    workspace = initialize_workspace(tmp_path / "workspace")
    coordinator, transport = coordinator_for()
    configuration = ConfigurationController(coordinator)
    configuration.set_workspace(workspace)
    transport.finish(payload=_sweep_capabilities())
    document = _saved_sweep_document(workspace)
    assert configuration.open_document(document)
    controller = SweepWorkflowController(
        coordinator,
        configuration_controller=configuration,
    )
    controller.set_workspace(workspace)
    saved_bytes = document.yaml_bytes
    digest = sha256_bytes(saved_bytes)
    assert controller.plan()
    _finish_plan(transport, digest=digest)

    finalized: list[Path] = []
    controller.output_finalized.connect(finalized.append)
    output = workspace.outputs / "sweep-output"
    output.mkdir()
    assert controller.execute()
    active_request_id = transport.request_id
    assert active_request_id is not None
    assert transport.payload == {
        "config_path": str(document.source_path),
        "expected_config_sha256": digest,
        "configs_root": str(workspace.configs),
        "expected_plan_id": "b" * 64,
        "output_root": str(workspace.outputs),
    }
    transport.emit_event("accepted", {})
    transport.emit_event("phase", {"name": "models", "cancellable": True})
    transport.emit_event("progress", {"completed": 1, "total": 3})

    assert configuration.get_can_edit()
    assert configuration.sweep_draft.set_reference_model("pr")
    assert configuration.get_dirty()
    assert controller.get_operation_active()
    assert controller.get_progress_completed() == 1
    assert controller.get_progress_total() == 3

    _finish_execution(transport, output, run_id="sweep-run")

    assert controller.state == "succeeded"
    assert finalized == [output]
    assert controller.get_result_output_directory() == str(output)
    assert controller.get_result_relation() == "stale"
    [record] = coordinator_for_job_records(workspace)
    assert record["request_id"] == str(active_request_id)
    assert record["status"] == "completed"
    assert record["phase"] == "models"
    assert record["progress"] == {"completed": 1, "total": 3}
    assert record["configuration"] == {
        "relative_path": "configs/sweep.yaml",
        "yaml_snapshot": saved_bytes.decode("utf-8"),
        "sha256": digest,
    }
    summary = record["summary"]
    assert isinstance(summary, dict)
    assert summary["output_directory"] == str(output)
    coordinator.shutdown()


def test_sweep_execution_cancel_force_stop_and_finalization_policy_use_one_session(
    tmp_path: Path,
    application: QCoreApplication,
) -> None:
    del application
    workspace = initialize_workspace(tmp_path / "workspace")
    config = _config(workspace)
    coordinator, transport = coordinator_for()
    controller = SweepWorkflowController(coordinator)
    controller.set_workspace(workspace)
    assert controller.load_config(config)
    digest = _finish_load(transport, config)
    assert controller.plan()
    _finish_plan(transport, digest=digest)

    assert controller.execute()
    request_id = transport.request_id
    assert request_id is not None
    transport.emit_event("accepted", {})
    transport.emit_event("phase", {"name": "models", "cancellable": True})
    assert controller.get_cancellation_available()
    assert controller.cancel()
    assert controller.state == "cancellation_requested"
    assert transport.cancelled == [request_id]
    assert not controller.get_cancellation_available()
    coordinator._enable_delayed_force_stop()
    assert controller.get_force_stop_available()
    assert controller.force_stop()
    assert controller.state == "force_stopping"
    assert transport.force_stopped == [request_id]
    transport.finish(
        terminal_type="error",
        payload={
            "category": "process",
            "code": "force_stopped",
            "message": "worker process was force-stopped",
        },
        force_stopped=True,
    )
    assert controller.state == "force_stopped"
    assert not controller.get_operation_active()

    assert controller.execute()
    transport.emit_event("accepted", {})
    transport.emit_event(
        "phase",
        {
            "name": "finalization",
            "cancellable": False,
            "termination_protected": True,
        },
    )
    assert controller.get_protected_finalization()
    assert not controller.cancel()
    coordinator._enable_delayed_force_stop()
    assert not controller.get_force_stop_available()
    assert not controller.force_stop()
    output = workspace.outputs / "finalized-sweep"
    _finish_execution(transport, output)
    assert controller.state == "succeeded"
    assert controller.get_result_output_directory() == str(output)
    assert sorted(str(record["status"]) for record in coordinator_for_job_records(workspace)) == [
        "completed",
        "force_stopped",
    ]
    coordinator.shutdown()


def test_sweep_controller_persists_only_execution_with_plan_identity(
    tmp_path: Path,
    application: QCoreApplication,
) -> None:
    del application
    workspace = initialize_workspace(tmp_path / "workspace")
    config = _config(workspace)
    coordinator, transport = coordinator_for()
    controller = SweepWorkflowController(coordinator)
    controller.set_workspace(workspace)

    assert controller.load_config(config)
    digest = _finish_load(transport, config)
    assert controller.state == "ready"
    assert controller.can_plan

    assert controller.plan()
    _finish_plan(transport, digest=digest)
    assert controller.state == "planned"
    assert controller.can_execute

    output = workspace.outputs / "sweep-output"
    finalized: list[Path] = []
    controller.output_finalized.connect(finalized.append)
    assert controller.execute()
    transport.finish(
        payload={
            "sweep_run_id": "sweep-run",
            "output_directory": str(output),
            "sweep_status": "completed",
        }
    )

    assert controller.state == "succeeded"
    assert finalized == [output]
    assert controller.get_has_result()
    assert controller.get_result_relation() == "current"
    assert controller.get_result_output_directory() == str(output)
    [record] = coordinator_for_job_records(workspace)
    assert record["owner"] == "sweep"
    assert record["operation"] == "execute_sweep"
    assert record["plan_identity"] == {
        "plan_id": "b" * 64,
        "plan_schema_version": None,
        "fingerprint": None,
    }
    coordinator.shutdown()


def test_finalized_result_survives_later_failed_and_cancelled_attempts(
    tmp_path: Path,
    application: QCoreApplication,
) -> None:
    del application
    workspace = initialize_workspace(tmp_path / "workspace")
    config = _config(workspace)
    coordinator, transport = coordinator_for()
    controller = SweepWorkflowController(coordinator)
    controller.set_workspace(workspace)

    assert not controller.get_has_result()
    assert controller.get_result_relation() == "unavailable"
    assert controller.get_result_output_directory() == ""
    assert controller.load_config(config)
    digest = _finish_load(transport, config)
    assert controller.plan()
    _finish_plan(transport, digest=digest)

    first_output = workspace.outputs / "first-output"
    first_output.mkdir()
    assert controller.execute()
    _finish_execution(transport, first_output, run_id="first-run")
    first_result = controller.result
    assert controller.get_result_relation() == "current"

    assert controller.execute()
    assert controller.result == first_result
    assert controller.get_result_relation() == "current"
    transport.finish(
        terminal_type="error",
        payload={
            "category": "execution",
            "code": "execution_failed",
            "message": "simulated later failure",
        },
    )
    assert controller.state == "failed"
    assert controller.result == first_result
    assert controller.get_result_relation() == "current"
    assert controller.get_result_output_directory() == str(first_output)

    assert controller.execute()
    assert controller.result == first_result
    transport.finish(
        terminal_type="cancelled",
        payload={"code": "cancelled", "message": "simulated cancellation"},
    )
    assert controller.state == "cancelled"
    assert controller.result == first_result
    assert controller.get_result_relation() == "current"

    second_output = workspace.outputs / "second-output"
    second_output.mkdir()
    assert controller.execute()
    _finish_execution(transport, second_output, run_id="second-run")
    assert controller.result != first_result
    assert controller.get_result_relation() == "current"
    assert controller.get_result_output_directory() == str(second_output)
    coordinator.shutdown()


def test_sweep_result_relation_uses_saved_identity_and_clears_with_workspace(
    tmp_path: Path,
    application: QCoreApplication,
) -> None:
    del application
    workspace = initialize_workspace(tmp_path / "workspace")
    config = _config(workspace)
    original_bytes = config.read_bytes()
    coordinator, transport = coordinator_for()
    controller = SweepWorkflowController(coordinator)
    controller.set_workspace(workspace)

    assert controller.load_config(config)
    digest = _finish_load(transport, config)
    assert controller.plan()
    _finish_plan(transport, digest=digest)
    output = workspace.outputs / "sweep-output"
    output.mkdir()
    assert controller.execute()
    _finish_execution(transport, output)
    finalized_result = controller.result

    config.write_text("schema_version: 2\nchanged: true\n", encoding="utf-8")
    controller.state_changed.emit()
    assert controller.result == finalized_result
    assert controller.get_result_relation() == "stale"

    config.write_bytes(original_bytes)
    assert controller.get_result_relation() == "current"

    replacement = workspace.configs / "replacement.yaml"
    replacement.write_text("schema_version: 2\nchanged: true\n", encoding="utf-8")
    assert controller.load_config(replacement)
    _finish_load(transport, replacement)
    assert controller.result == finalized_result
    assert controller.get_result_relation() == "stale"

    assert controller.load_config(config)
    assert _finish_load(transport, config) == digest
    assert controller.result == finalized_result
    assert controller.get_result_relation() == "current"

    controller.set_workspace(initialize_workspace(tmp_path / "other-workspace"))
    assert controller.result is None
    assert not controller.get_has_result()
    assert controller.get_result_relation() == "unavailable"
    assert controller.get_result_output_directory() == ""
    coordinator.shutdown()


def test_failed_workflow_load_retains_previous_plan_as_stale(
    tmp_path: Path,
    application: QCoreApplication,
) -> None:
    del application
    workspace = initialize_workspace(tmp_path / "workspace")
    config = _config(workspace)
    coordinator, transport = coordinator_for()
    controller = SweepWorkflowController(coordinator)
    controller.set_workspace(workspace)

    assert controller.load_config(config)
    digest = _finish_load(transport, config)
    assert controller.plan()
    _finish_plan(transport, digest=digest)
    assert controller.can_execute

    assert controller.load_config(workspace.configs / "missing.yaml")
    transport.finish(
        terminal_type="error",
        payload={
            "category": "config",
            "code": "invalid_config",
            "message": "configuration is invalid",
        },
    )

    assert controller.state == "failed"
    assert controller.current_plan is not None
    assert controller.get_has_plan()
    assert controller.get_plan_id() == "b" * 64
    assert not controller.get_plan_current()
    assert controller.loaded_config is None
    assert controller.config_path is None
    assert controller.config_sha256 == ""
    assert controller.validation is None
    assert not controller.can_plan
    assert not controller.can_execute
    assert [issue.code for issue in controller.execution_blocking_reasons.issues] == [
        "plan_configuration_changed",
        "saved_configuration_required",
    ]
    coordinator.shutdown()


def test_sweep_plan_currentness_follows_exact_saved_configuration_identity(
    tmp_path: Path,
    application: QCoreApplication,
) -> None:
    del application
    workspace = initialize_workspace(tmp_path / "workspace")
    config = _config(workspace)
    original_bytes = config.read_bytes()
    coordinator, transport = coordinator_for()
    controller = SweepWorkflowController(coordinator)
    controller.set_workspace(workspace)

    assert controller.load_config(config)
    digest = _finish_load(transport, config)
    assert controller.plan()
    _finish_plan(transport, digest=digest)

    assert controller.get_has_plan()
    assert controller.get_plan_id() == "b" * 64
    assert controller.get_plan_current()
    assert controller.can_execute

    config.write_text("schema_version: 2\nchanged: true\n", encoding="utf-8")
    controller.state_changed.emit()
    assert not controller.get_plan_current()
    assert not controller.can_execute
    assert [issue.code for issue in controller.execution_blocking_reasons.issues] == [
        "saved_configuration_unavailable"
    ]

    config.write_bytes(original_bytes)
    assert controller.get_plan_current()
    assert controller.can_execute

    replacement = workspace.configs / "replacement.yaml"
    replacement.write_text("schema_version: 2\nchanged: true\n", encoding="utf-8")
    assert controller.load_config(replacement)
    replacement_digest = _finish_load(transport, replacement)
    assert replacement_digest != digest
    assert controller.get_has_plan()
    assert not controller.get_plan_current()
    assert [issue.code for issue in controller.execution_blocking_reasons.issues] == [
        "plan_configuration_changed"
    ]

    assert controller.load_config(config)
    assert _finish_load(transport, config) == digest
    assert controller.get_plan_current()
    assert controller.can_execute

    controller.set_workspace(initialize_workspace(tmp_path / "other-workspace"))
    assert not controller.get_has_plan()
    assert not controller.get_plan_current()
    coordinator.shutdown()


def test_cancelled_replan_keeps_the_last_semantically_current_plan(
    tmp_path: Path,
    application: QCoreApplication,
) -> None:
    del application
    workspace = initialize_workspace(tmp_path / "workspace")
    config = _config(workspace)
    coordinator, transport = coordinator_for()
    controller = SweepWorkflowController(coordinator)
    controller.set_workspace(workspace)

    assert controller.load_config(config)
    digest = _finish_load(transport, config)
    assert controller.plan()
    _finish_plan(transport, digest=digest)
    accepted_plan = controller.current_plan

    assert controller.plan()
    assert controller.current_plan == accepted_plan
    assert controller.get_plan_current()
    assert not controller.can_execute
    transport.finish(
        terminal_type="cancelled",
        payload={"code": "cancelled", "message": "planning cancelled"},
    )

    assert controller.state == "cancelled"
    assert controller.current_plan == accepted_plan
    assert controller.get_plan_current()
    assert controller.can_execute
    coordinator.shutdown()


def test_changed_saved_bytes_prevent_a_plan_response_from_replacing_the_last_plan(
    tmp_path: Path,
    application: QCoreApplication,
) -> None:
    del application
    workspace = initialize_workspace(tmp_path / "workspace")
    config = _config(workspace)
    original_bytes = config.read_bytes()
    coordinator, transport = coordinator_for()
    controller = SweepWorkflowController(coordinator)
    controller.set_workspace(workspace)

    assert controller.load_config(config)
    digest = _finish_load(transport, config)
    assert controller.plan()
    _finish_plan(transport, digest=digest)
    accepted_plan = controller.current_plan

    assert controller.plan()
    config.write_text("schema_version: 2\nchanged: true\n", encoding="utf-8")
    _finish_plan(transport, digest=digest, plan_id="c" * 64)

    assert controller.state == "failed"
    assert controller.failure["code"] == "stale_plan"
    assert controller.current_plan == accepted_plan
    assert controller.get_plan_id() == "b" * 64
    assert not controller.get_plan_current()

    config.write_bytes(original_bytes)
    assert controller.get_plan_current()
    assert controller.can_execute
    coordinator.shutdown()


@pytest.mark.parametrize("failure_code", ["stale_plan", "source_changed"])
def test_worker_semantic_failure_retains_but_rejects_the_plan(
    tmp_path: Path,
    application: QCoreApplication,
    failure_code: str,
) -> None:
    del application
    workspace = initialize_workspace(tmp_path / "workspace")
    config = _config(workspace)
    coordinator, transport = coordinator_for()
    controller = SweepWorkflowController(coordinator)
    controller.set_workspace(workspace)

    assert controller.load_config(config)
    digest = _finish_load(transport, config)
    assert controller.plan()
    _finish_plan(transport, digest=digest)
    accepted_plan = controller.current_plan

    assert controller.execute()
    transport.finish(
        terminal_type="error",
        payload={
            "category": "config",
            "code": failure_code,
            "message": "execution-time planning produced a different identity",
        },
    )

    assert controller.state == "failed"
    assert controller.current_plan == accepted_plan
    assert controller.get_has_plan()
    assert not controller.get_plan_current()
    assert not controller.can_execute
    [reason] = controller.execution_blocking_reasons.issues
    assert reason.code == "plan_rejected_by_worker"
    assert reason.origin == "plan"
    assert reason.message == "execution-time planning produced a different identity"
    coordinator.shutdown()


def test_workflow_terminal_activity_persistence_failure_is_reported(
    tmp_path: Path,
    application: QCoreApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del application
    from carnopy.app.jobs import JobStore

    workspace = initialize_workspace(tmp_path / "workspace")
    config = _config(workspace)
    coordinator, transport = coordinator_for()
    controller = SweepWorkflowController(coordinator)
    controller.set_workspace(workspace)

    assert controller.load_config(config)
    digest = _finish_load(transport, config)
    assert controller.plan()
    _finish_plan(transport, digest=digest)
    assert controller.execute()

    store = controller._store
    assert isinstance(store, JobStore)

    def fail_persistence(*_args: object, **_kwargs: object) -> None:
        raise OSError("disk unavailable")

    monkeypatch.setattr(store, "finish", fail_persistence)
    monkeypatch.setattr(store, "write", fail_persistence)
    transport.finish(payload={"output_directory": str(workspace.outputs / "sweep")})

    assert controller.state == "succeeded"
    assert "disk unavailable" in controller.activity_persistence_issue
    coordinator.shutdown()


def test_worker_start_failure_does_not_leak_activity_record_into_next_request(
    tmp_path: Path,
    application: QCoreApplication,
) -> None:
    del application
    from carnopy.app.jobs import JobStore

    workspace = initialize_workspace(tmp_path / "workspace")
    config = _config(workspace)
    coordinator, transport = coordinator_for()
    controller = SweepWorkflowController(coordinator)
    controller.set_workspace(workspace)

    assert controller.load_config(config)
    digest = _finish_load(transport, config)
    assert controller.plan()
    _finish_plan(transport, digest=digest)

    transport.raise_on_start = True
    assert not controller.execute()
    assert controller._active_snapshot is None
    assert controller._active_plan_context is None
    assert controller._active_record is None
    failed_records = JobStore(workspace.private_directory).load()
    [failed] = [item.data for item in failed_records if item.data is not None]
    assert failed["operation"] == "execute_sweep"
    assert failed["phase"] == "starting"

    transport.raise_on_start = False
    assert controller.load_config(config)
    transport.emit_event("phase", {"name": "validation", "cancellable": True})
    _finish_load(transport, config)

    records = JobStore(workspace.private_directory).load()
    failed_after = next(
        item.data
        for item in records
        if item.data is not None and item.data["operation"] == "execute_sweep"
    )
    assert failed_after is not None
    assert failed_after["phase"] == "starting"
    coordinator.shutdown()


def coordinator_for_job_records(workspace: Workspace) -> list[dict[str, object]]:
    from carnopy.app.jobs import JobStore

    records = JobStore(workspace.private_directory).load()
    return [cast(dict[str, object], item.data) for item in records if item.data is not None]


def test_preparation_binding_does_not_follow_inspection_and_cannot_change_during_plan(
    tmp_path: Path,
    application: QCoreApplication,
) -> None:
    del application
    workspace = initialize_workspace(tmp_path / "workspace")
    config = _config(workspace, "preparation.yaml")
    source = workspace.outputs / "dataset-run"
    source.mkdir()
    replacement = workspace.outputs / "replacement-run"
    replacement.mkdir()
    coordinator, transport = coordinator_for()
    inspection = InspectionController(coordinator)
    controller = PreparationWorkflowController(coordinator, inspection)
    controller.set_workspace(workspace)

    assert controller.load_config(config)
    digest = _finish_load(transport, config)
    old_revision = "a" * 64
    old_descriptor = _accept_preparation_inspection(
        inspection,
        source,
        revision=old_revision,
    )
    assert controller.get_inspected_source_available()
    assert not controller.get_can_plan()
    assert controller.bind_inspected_source()
    assert controller.get_bound_source_path() == str(source.resolve())
    assert controller.get_inspected_source_matches_binding()
    assert controller.plan()

    new_revision = "c" * 64
    new_descriptor = _accept_preparation_inspection(
        inspection,
        replacement,
        revision=new_revision,
    )
    assert controller.get_bound_source_path() == str(source.resolve())
    assert controller.get_inspected_source_available()
    assert not controller.get_inspected_source_matches_binding()
    assert not controller.bind_inspected_source()
    assert "worker operation is active" in controller.get_source_binding_issue()
    assert not controller.clear_bound_source()
    assert controller.get_bound_source_path() == str(source.resolve())
    _finish_plan(
        transport,
        digest=digest,
        source_revision={
            "inspection_revision": old_revision,
            "inspection_descriptor": old_descriptor,
            "consumed_source": {},
        },
    )

    assert controller.state == "planned"
    assert controller.get_plan_current()
    assert controller.bind_inspected_source()
    assert controller.current_plan is not None
    assert not controller.get_plan_current()
    assert controller._plan_context() == {
        "source_path": str(replacement.resolve()),
        "inspection_revision": new_revision,
        "inspection_descriptor": new_descriptor,
    }
    coordinator.shutdown()


def test_preparation_plan_currentness_uses_the_complete_inspection_context(
    tmp_path: Path,
    application: QCoreApplication,
) -> None:
    del application
    workspace = initialize_workspace(tmp_path / "workspace")
    config = _config(workspace, "preparation.yaml")
    source = workspace.outputs / "dataset-run"
    source.mkdir()
    replacement = workspace.outputs / "replacement-run"
    replacement.mkdir()
    coordinator, transport = coordinator_for()
    inspection = InspectionController(coordinator)
    controller = PreparationWorkflowController(coordinator, inspection)
    controller.set_workspace(workspace)

    assert controller.load_config(config)
    digest = _finish_load(transport, config)
    revision = "a" * 64
    descriptor = _accept_preparation_inspection(
        inspection,
        source,
        revision=revision,
    )
    assert controller.bind_inspected_source()
    assert controller.plan()
    _finish_plan(
        transport,
        digest=digest,
        source_revision={
            "inspection_revision": revision,
            "inspection_descriptor": descriptor,
            "consumed_source": {},
        },
    )

    accepted_plan = controller.current_plan
    assert controller.get_plan_current()
    assert controller.can_execute
    assert controller.bind_inspected_source()
    assert controller.current_plan == accepted_plan
    assert controller.get_plan_current()

    _accept_preparation_inspection(
        inspection,
        replacement,
        revision=revision,
    )
    assert controller.current_plan == accepted_plan
    assert controller.get_plan_current()
    assert controller.can_execute
    assert controller.get_bound_source_path() == str(source.resolve())

    assert controller.bind_inspected_source()
    assert not controller.get_plan_current()
    assert not controller.can_execute
    [reason] = controller.execution_blocking_reasons.issues
    assert reason.code == "plan_context_changed"
    assert reason.origin == "source"

    restored_descriptor = _accept_preparation_inspection(
        inspection,
        source,
        revision=revision,
    )
    assert restored_descriptor == descriptor
    assert controller.bind_inspected_source()
    assert controller.current_plan == accepted_plan
    assert controller.get_plan_current()
    assert controller.can_execute
    coordinator.shutdown()


def test_preparation_binding_refresh_clear_and_workspace_lifecycle_are_explicit(
    tmp_path: Path,
    application: QCoreApplication,
) -> None:
    del application
    workspace = initialize_workspace(tmp_path / "workspace")
    replacement_workspace = initialize_workspace(tmp_path / "replacement-workspace")
    config = _config(workspace, "preparation.yaml")
    source = workspace.outputs / "dataset-run"
    source.mkdir()
    coordinator, transport = coordinator_for()
    inspection = InspectionController(coordinator)
    controller = PreparationWorkflowController(coordinator, inspection)
    controller.set_workspace(workspace)

    assert controller.load_config(config)
    digest = _finish_load(transport, config)
    original_revision = "a" * 64
    original_descriptor = _accept_preparation_inspection(
        inspection,
        source,
        revision=original_revision,
    )
    assert controller.bind_inspected_source()
    snapshot = controller.bound_source_snapshot()
    assert snapshot is not None
    snapshot[2]["source_path"] = "mutated"
    snapshot[3]["source_identity"] = {"source_kind": "mutated"}
    restored_snapshot = controller.bound_source_snapshot()
    assert restored_snapshot is not None
    assert restored_snapshot[2] == original_descriptor
    assert restored_snapshot[3]["source_identity"] == {"source_kind": "dataset_run"}

    assert controller.plan()
    _finish_plan(
        transport,
        digest=digest,
        source_revision={
            "inspection_revision": original_revision,
            "inspection_descriptor": original_descriptor,
            "consumed_source": {},
        },
    )
    assert controller.get_plan_current()

    refreshed_revision = "c" * 64
    refreshed_descriptor = _accept_preparation_inspection(
        inspection,
        source,
        revision=refreshed_revision,
    )
    assert controller.get_bound_source_revision() == original_revision
    assert controller.get_bound_source_refresh_available()
    assert controller.get_inspected_source_available()
    assert controller.get_plan_current()
    assert controller.config_sha256 == digest

    assert controller.bind_inspected_source()
    assert controller.get_bound_source_revision() == refreshed_revision
    assert not controller.get_bound_source_refresh_available()
    assert not controller.get_plan_current()
    assert controller._plan_context()["inspection_descriptor"] == refreshed_descriptor
    assert controller.config_sha256 == digest

    assert controller.clear_bound_source()
    assert not controller.get_has_bound_source()
    assert controller.current_plan is not None
    assert not controller.get_plan_current()
    [reason] = controller.plan_blocking_reasons.issues
    assert reason.code == "preparation_source_unavailable"
    assert "use an inspected source" in reason.message

    assert controller.bind_inspected_source()
    controller.set_workspace(replacement_workspace)
    assert not controller.get_has_bound_source()
    assert controller.bound_source_snapshot() is None
    assert controller.current_plan is None
    coordinator.shutdown()


def test_preparation_result_keeps_the_source_context_used_by_execution(
    tmp_path: Path,
    application: QCoreApplication,
) -> None:
    del application
    workspace = initialize_workspace(tmp_path / "workspace")
    config = _config(workspace, "preparation.yaml")
    source = workspace.outputs / "dataset-run"
    source.mkdir()
    replacement = workspace.outputs / "replacement-run"
    replacement.mkdir()
    coordinator, transport = coordinator_for()
    inspection = InspectionController(coordinator)
    controller = PreparationWorkflowController(coordinator, inspection)
    controller.set_workspace(workspace)

    assert controller.load_config(config)
    digest = _finish_load(transport, config)
    revision = "a" * 64
    descriptor = _accept_preparation_inspection(
        inspection,
        source,
        revision=revision,
    )
    assert controller.bind_inspected_source()
    assert controller.plan()
    _finish_plan(
        transport,
        digest=digest,
        source_revision={
            "inspection_revision": revision,
            "inspection_descriptor": descriptor,
            "consumed_source": {},
        },
    )

    output = workspace.outputs / "preparation-output"
    output.mkdir()
    assert controller.execute()
    _accept_preparation_inspection(
        inspection,
        replacement,
        revision=revision,
    )
    assert not controller.bind_inspected_source()
    _finish_execution(transport, output)

    assert controller.state == "succeeded"
    assert controller.get_has_result()
    assert controller.get_result_output_directory() == str(output)
    assert controller.get_result_relation() == "current"
    record = next(
        item
        for item in coordinator_for_job_records(workspace)
        if item["operation"] == "execute_preparation"
    )
    assert record["preparation_source_identity"] == {
        "source_path": str(source.resolve()),
        "source_kind": "dataset_run",
        "inspection_revision": revision,
        "descriptor": descriptor,
        "source_identity": {"source_kind": "dataset_run"},
    }

    assert controller.bind_inspected_source()
    assert controller.get_result_relation() == "stale"

    restored_descriptor = _accept_preparation_inspection(
        inspection,
        source,
        revision=revision,
    )
    assert restored_descriptor == descriptor
    assert controller.bind_inspected_source()
    assert controller.get_result_relation() == "current"
    coordinator.shutdown()


def test_workflow_qml_projections_expose_existing_state_without_changing_eligibility(
    tmp_path: Path,
    application: QCoreApplication,
) -> None:
    del application
    workspace = initialize_workspace(tmp_path / "workspace")
    coordinator, _transport = coordinator_for()
    controller = SweepWorkflowController(coordinator)

    assert controller.get_workflow_kind() == "sweep"
    assert controller.get_document_kind() == "model_sweep"
    assert controller.get_workflow_state() == "unavailable"
    assert not controller.get_operation_active()
    assert not controller.get_can_plan()
    assert not controller.get_can_execute()
    assert [issue.code for issue in controller.plan_blocking_reasons.issues] == [
        "workspace_required"
    ]
    assert [issue.code for issue in controller.execution_blocking_reasons.issues] == [
        "current_plan_required",
        "workspace_required",
    ]

    controller.set_workspace(workspace)

    assert controller.get_workflow_state() == "ready"
    [reason] = controller.plan_blocking_reasons.issues
    assert reason.code == "saved_configuration_required"
    assert reason.origin == "local"
    assert reason.severity == "blocking"
    assert reason.document_kind == "model_sweep"
    assert reason.section == "configuration"
    assert reason.field_id == "sweep.configuration"
    coordinator.shutdown()


def test_workflow_operation_progress_and_protected_finalization_are_typed(
    tmp_path: Path,
    application: QCoreApplication,
) -> None:
    del application
    workspace = initialize_workspace(tmp_path / "workspace")
    config = _config(workspace)
    coordinator, transport = coordinator_for()
    controller = SweepWorkflowController(coordinator)
    controller.set_workspace(workspace)
    assert controller.load_config(config)
    digest = _finish_load(transport, config)
    assert controller.get_can_plan()
    assert controller.plan_blocking_reasons.issues == ()
    assert controller.plan()
    _finish_plan(transport, digest=digest)
    assert controller.get_can_execute()
    assert controller.execution_blocking_reasons.issues == ()

    assert controller.execute()
    assert controller.get_operation_active()
    assert controller.get_workflow_operation() == "execute"
    assert [issue.code for issue in controller.execution_blocking_reasons.issues] == [
        "operation_active"
    ]
    transport.emit_event("accepted", {})
    transport.emit_event(
        "phase",
        {"name": "generation", "cancellable": True},
    )
    transport.emit_event("progress", {"completed": 7, "total": 10})

    assert controller.get_workflow_state() == "running"
    assert controller.get_workflow_phase() == "generation"
    assert controller.get_progress_available()
    assert controller.get_progress_completed() == 7
    assert controller.get_progress_total() == 10
    assert controller.get_cancellation_available()
    assert not controller.get_force_stop_available()
    assert not controller.get_protected_finalization()

    transport.emit_event(
        "phase",
        {
            "name": "finalization",
            "cancellable": False,
            "termination_protected": True,
        },
    )

    assert controller.get_protected_finalization()
    assert not controller.get_cancellation_available()
    assert not controller.get_force_stop_available()
    transport.finish(payload={"output_directory": str(workspace.outputs / "sweep")})
    assert not controller.get_operation_active()
    assert not controller.get_protected_finalization()
    coordinator.shutdown()


def test_workflow_failure_and_preparation_source_blockers_are_typed(
    tmp_path: Path,
    application: QCoreApplication,
) -> None:
    del application
    workspace = initialize_workspace(tmp_path / "workspace")
    config = _config(workspace, "preparation.yaml")
    coordinator, transport = coordinator_for()
    inspection = InspectionController(coordinator)
    controller = PreparationWorkflowController(coordinator, inspection)
    controller.set_workspace(workspace)
    assert controller.load_config(config)
    _finish_load(transport, config)

    assert not controller.get_can_plan()
    [reason] = controller.plan_blocking_reasons.issues
    assert reason.code == "preparation_source_unavailable"
    assert reason.origin == "source"
    assert reason.document_kind == "preparation"
    assert reason.section == "source"
    assert reason.field_id == "preparation.source"

    assert not controller.plan()
    assert controller.get_workflow_state() == "failed"
    assert controller.get_failure_category() == "request"
    assert controller.get_failure_code() == "plan_unavailable"
    assert "use an inspected source" in controller.get_failure_message()
    coordinator.shutdown()
