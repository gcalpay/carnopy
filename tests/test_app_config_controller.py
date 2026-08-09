from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
import yaml

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication, QEvent, QObject, Signal

from carnopy.app.config_controller import ConfigurationController, DatasetConfigController
from carnopy.app.config_document import (
    ConfigDocumentError,
    DatasetConfigDocument,
    new_document,
    serialize_configuration,
    serialize_dataset_config,
    sha256_bytes,
)
from carnopy.app.request_coordinator import DesktopRequestCoordinator, RequestSession
from carnopy.app.workspace import initialize_workspace
from carnopy.templates import template_text


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
        self.calls: list[tuple[str, str, dict[str, object]]] = []
        self.session: StubSession | None = None

    def start_request(
        self,
        owner: str,
        request_type: str,
        payload: dict[str, object],
    ) -> RequestSession:
        if self.is_busy:
            raise RuntimeError("request already active")
        self.calls.append((owner, request_type, payload))
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

    def shutdown(self) -> None:
        if self.is_busy:
            raise RuntimeError("cannot shut down while busy")

    @property
    def active_owner(self) -> str | None:
        return "configuration" if self.is_busy else None


@pytest.fixture(scope="module")
def application() -> QCoreApplication:
    existing = QCoreApplication.instance()
    app = existing if isinstance(existing, QCoreApplication) else QCoreApplication([])
    yield app
    if type(app) is QCoreApplication:
        app.quit()
        app.deleteLater()
        QCoreApplication.sendPostedEvents(app, QEvent.Type.DeferredDelete)


def capabilities() -> dict[str, Any]:
    fields = [
        {
            "name": name,
            "kind": "numeric",
            "axis_allowed": True,
            "group_allowed": name in {"temperature", "pressure"},
            "filter_allowed": name in {"temperature", "pressure"},
        }
        for name in ("temperature", "pressure", "mass_density", "specific_volume")
    ]
    fields.append(
        {
            "name": "fluid",
            "kind": "categorical",
            "axis_allowed": False,
            "group_allowed": False,
            "filter_allowed": False,
        }
    )
    return {
        "model": "heos",
        "models": ["heos", "pr", "srk"],
        "modes": [
            "property_table",
            "saturation_table",
            "vapor_mass_fraction_table",
        ],
        "units_by_axis": {
            "temperature": ["K", "degC"],
            "pressure": ["Pa", "bar"],
            "vapor_mass_fraction": ["1"],
        },
        "dataset_formats": ["csv", "parquet"],
        "fluids": [
            {"name": "Propane", "aliases": ["R290"]},
            {"name": "Cyclopentane", "aliases": []},
        ],
        "property_catalog": [{"name": "mass_density", "supported_models": ["heos", "pr", "srk"]}],
        "reference_dependent_fields": [],
        "visualization": {
            "plot_kinds": ["pv"],
            "formats": ["png", "svg"],
            "scales": ["linear", "log"],
            "kind_contracts": {
                "pv": {
                    "required": [],
                    "applicable": [
                        "filters",
                        "series",
                        "display_units",
                        "fluids",
                        "x_scale",
                        "y_scale",
                        "format",
                    ],
                }
            },
            "fields": fields,
            "display_units": {
                "temperature": ["K", "degC"],
                "pressure": ["Pa", "bar"],
            },
            "categorical_values": {},
        },
    }


def payload(*, visualization: bool = False) -> dict[str, Any]:
    value: dict[str, Any] = {
        "schema_version": 2,
        "document_type": "dataset",
        "backend": {"name": "coolprop", "model": "heos"},
        "mode": "property_table",
        "fluids": ["Propane"],
        "grid": {
            "temperature": {
                "kind": "linspace",
                "start": 20.0,
                "stop": 100.0,
                "num": 5,
                "unit": "degC",
            },
            "pressure": {
                "kind": "linspace",
                "start": 1.0,
                "stop": 20.0,
                "num": 5,
                "unit": "bar",
            },
        },
        "properties": ["mass_density"],
        "outputs": {"dataset_formats": ["csv", "parquet"]},
    }
    if visualization:
        value["visualization"] = {"plots": [{"name": "pressure-volume", "kind": "pv"}]}
    return value


def configured_controller(
    tmp_path: Path,
) -> tuple[DatasetConfigController, StubCoordinator]:
    coordinator = StubCoordinator()
    controller = DatasetConfigController(cast(DesktopRequestCoordinator, coordinator))
    workspace = initialize_workspace(tmp_path / "workspace")

    controller.set_workspace(workspace)
    assert coordinator.calls[-1][1] == "describe_capabilities"
    coordinator.succeed(capabilities())

    return controller, coordinator


def test_controller_owns_complete_merge_dirty_and_execution_gates(
    tmp_path: Path,
    application: QCoreApplication,
) -> None:
    del application
    controller, _coordinator = configured_controller(tmp_path)
    controller.open_document(new_document(payload(visualization=True)))

    assert controller.get_has_document()
    assert controller.get_locally_valid()
    assert controller.get_dirty()
    assert controller.document is not None
    assert controller.get_yaml_preview() == controller.document.yaml_text
    assert controller.document.payload["visualization"]["plots"] == [
        {"name": "pressure-volume", "kind": "pv"}
    ]
    assert controller.document.payload["visualization"] == {
        "format": "png",
        "plots": [{"name": "pressure-volume", "kind": "pv"}],
    }
    with pytest.raises(ConfigDocumentError, match="save the configuration"):
        controller.execution_snapshot()

    controller.dataset_draft.set_output_selected("csv", False)
    controller.dataset_draft.set_output_selected("parquet", False)

    assert not controller.get_locally_valid()
    assert controller.get_dirty()
    assert controller.get_yaml_preview() == ""
    assert not controller.get_yaml_available()
    assert controller.get_blocking_section() == "dataset"
    assert controller.get_blocking_field() == "dataset.outputs.dataset_formats"
    assert controller.get_blocking_row() == -1
    assert controller.get_blocking_issue()
    assert not controller.get_can_save()

    controller.dataset_draft.set_output_selected("parquet", True)
    assert controller.get_locally_valid()
    assert controller.get_yaml_available()
    assert controller.get_blocking_section() == "none"
    assert controller.get_blocking_field() == ""
    assert controller.get_blocking_row() == -1
    assert controller.get_blocking_issue() == ""
    assert controller.document.payload["outputs"] == {"dataset_formats": ["parquet"]}


def test_controller_validates_exact_yaml_before_writing_and_refreshes_baselines(
    tmp_path: Path,
    application: QCoreApplication,
) -> None:
    del application
    controller, coordinator = configured_controller(tmp_path)
    controller.open_document(new_document(payload(visualization=True)))
    destinations: list[str] = []
    saves: list[str] = []
    controller.save_path_requested.connect(destinations.append)
    controller.saveSucceeded.connect(saves.append)

    assert controller.request_save_as()
    assert destinations == [str(controller.workspace.configs / "dataset.yaml")]
    destination = controller.workspace.configs / "configured.yaml"
    expected = controller.get_yaml_preview()
    assert controller.save_path_selected(str(destination))

    owner, request_type, request_payload = coordinator.calls[-1]
    assert (owner, request_type) == ("configuration", "validate_dataset_config")
    assert request_payload == {
        "yaml_text": expected,
        "source_name": str(destination),
    }
    assert not destination.exists()

    coordinator.succeed({})

    assert destination.read_text(encoding="utf-8") == expected
    assert saves == [str(destination)]
    assert not controller.get_dirty()
    assert not controller.dataset_draft.get_dirty()
    assert not controller.visualization_draft.get_dirty()
    assert controller.execution_snapshot().path == destination


def test_standalone_validation_is_bound_to_one_exact_document_revision(
    tmp_path: Path,
    application: QCoreApplication,
) -> None:
    del application
    controller, coordinator = configured_controller(tmp_path)
    controller.open_document(new_document(payload()))
    expected = controller.get_yaml_preview()

    assert controller.get_worker_validation_state() == "not_run"
    assert controller.get_can_validate()
    assert controller.request_validation()
    assert controller.get_worker_validation_state() == "running"
    assert not controller.get_can_validate()
    assert coordinator.calls[-1] == (
        "configuration",
        "validate_dataset_config",
        {"yaml_text": expected, "source_name": "<gui>"},
    )

    assert controller.dataset_draft.add_fluid("Cyclopentane")
    assert controller.get_worker_validation_state() == "stale"
    assert controller.dataset_draft.remove_fluid(1)
    assert controller.document is not None
    assert controller.document.yaml_text == expected
    assert controller.get_worker_validation_state() == "stale"

    coordinator.succeed({})

    assert controller.get_worker_validation_state() == "stale"
    assert controller.get_can_validate()


def test_standalone_validation_classifies_structured_failures_without_issues(
    tmp_path: Path,
    application: QCoreApplication,
) -> None:
    del application
    controller, coordinator = configured_controller(tmp_path)
    controller.open_document(new_document(payload()))

    assert controller.request_validation()
    coordinator.fail(
        {
            "category": "config",
            "code": "invalid_config",
            "message": "worker rejected the exact YAML",
        }
    )

    assert controller.get_worker_validation_state() == "invalid"
    assert controller.get_worker_validation_issue() == "worker rejected the exact YAML"
    assert controller.get_worker_validation_issues() == []
    assert controller.get_can_save()

    assert controller.request_validation()
    coordinator.fail(
        {
            "category": "process",
            "code": "worker_exited",
            "message": "worker exited before validating",
        }
    )

    assert controller.get_worker_validation_state() == "failed"
    assert controller.get_worker_validation_issue() == "worker exited before validating"
    assert controller.get_can_save()


def test_validation_blocking_and_recovery_preserve_attempt_history(
    tmp_path: Path,
    application: QCoreApplication,
) -> None:
    del application
    controller, coordinator = configured_controller(tmp_path)
    controller.open_document(new_document(payload()))

    controller.dataset_draft.set_output_selected("csv", False)
    controller.dataset_draft.set_output_selected("parquet", False)
    assert controller.get_worker_validation_state() == "blocked"
    assert not controller.get_can_validate()

    controller.dataset_draft.set_output_selected("parquet", True)
    assert controller.get_worker_validation_state() == "not_run"
    assert controller.request_validation()
    coordinator.succeed({})
    assert controller.get_worker_validation_state() == "valid"

    controller.dataset_draft.set_output_selected("parquet", False)
    assert controller.get_worker_validation_state() == "blocked"
    controller.dataset_draft.set_output_selected("csv", True)
    assert controller.get_worker_validation_state() == "stale"


def test_active_plot_edit_blocks_validation_without_becoming_durable_state(
    tmp_path: Path,
    application: QCoreApplication,
) -> None:
    del application
    controller, coordinator = configured_controller(tmp_path)
    controller.open_document(new_document(payload(visualization=True)))

    assert controller.visualization_draft.begin_edit_plot(0) is not None
    assert controller.get_worker_validation_state() == "blocked"
    assert not controller.get_can_validate()
    assert controller.visualization_draft.cancel_plot()
    assert controller.get_worker_validation_state() == "not_run"

    assert controller.request_validation()
    coordinator.succeed({})
    assert controller.get_worker_validation_state() == "valid"
    assert controller.visualization_draft.begin_edit_plot(0) is not None
    assert controller.get_worker_validation_state() == "blocked"
    assert controller.visualization_draft.cancel_plot()
    assert controller.get_worker_validation_state() == "stale"


def test_save_always_runs_fresh_validation_after_standalone_success(
    tmp_path: Path,
    application: QCoreApplication,
) -> None:
    del application
    controller, coordinator = configured_controller(tmp_path)
    controller.open_document(new_document(payload()))

    assert controller.request_validation()
    coordinator.succeed({})
    assert controller.get_worker_validation_state() == "valid"
    validation_calls = len(coordinator.calls)

    assert controller.request_save_as()
    destination = controller.workspace.configs / "validated.yaml"
    assert controller.save_path_selected(str(destination))
    assert len(coordinator.calls) == validation_calls + 1
    assert coordinator.calls[-1][1] == "validate_dataset_config"
    assert controller.get_worker_validation_state() == "running"
    assert not destination.exists()

    coordinator.succeed({})

    assert destination.exists()
    assert controller.get_worker_validation_state() == "valid"
    assert not controller.get_dirty()
    assert controller.request_validation()
    coordinator.succeed({})
    assert controller.get_worker_validation_state() == "valid"
    assert not controller.get_dirty()


def test_reverting_during_save_does_not_resurrect_the_captured_validation(
    tmp_path: Path,
    application: QCoreApplication,
) -> None:
    del application
    controller, coordinator = configured_controller(tmp_path)
    controller.open_document(new_document(payload()))
    destination = controller.workspace.configs / "dataset.yaml"

    assert controller.request_save_as()
    assert controller.save_path_selected(str(destination))
    assert controller.dataset_draft.add_fluid("Cyclopentane")
    assert controller.dataset_draft.remove_fluid(1)
    coordinator.succeed({})

    assert not destination.exists()
    assert controller.get_worker_validation_state() == "stale"


def test_worker_validation_failure_never_writes_pending_yaml(
    tmp_path: Path,
    application: QCoreApplication,
) -> None:
    del application
    controller, coordinator = configured_controller(tmp_path)
    controller.open_document(new_document(payload()))
    controller.save_path_requested.connect(controller.save_path_selected)
    warnings: list[tuple[str, str]] = []
    failures: list[tuple[str, str, str, list[dict[str, str]]]] = []
    controller.warning_requested.connect(lambda title, message: warnings.append((title, message)))
    controller.operationFailed.connect(
        lambda operation, title, message, issues: failures.append(
            (operation, title, message, issues)
        )
    )
    destination = controller.workspace.configs / "dataset.yaml"

    assert controller.request_save_as()
    coordinator.fail(
        {
            "message": "worker rejected exact YAML",
            "details": {"issues": [{"path": "$.grid", "message": "invalid grid"}]},
        }
    )

    assert not destination.exists()
    assert warnings == [("Validation Failed", "worker rejected exact YAML\n$.grid: invalid grid")]
    assert failures == [
        (
            "save_as",
            "Validation Failed",
            "worker rejected exact YAML",
            [{"path": "$.grid", "message": "invalid grid"}],
        )
    ]
    assert controller.get_dirty()


def test_successful_import_reports_typed_source_location(
    tmp_path: Path,
    application: QCoreApplication,
) -> None:
    del application
    controller, coordinator = configured_controller(tmp_path)
    source = tmp_path / "external.yaml"
    content = serialize_dataset_config(payload())
    source.write_bytes(content)
    imported: list[tuple[str, bool]] = []
    controller.importSucceeded.connect(lambda path, external: imported.append((path, external)))

    assert controller.import_dataset(str(source))
    coordinator.succeed(
        {
            "config": payload(),
            "source_name": str(source),
            "source_sha256": sha256_bytes(content),
        }
    )

    assert imported == [(str(source.resolve()), True)]
    assert controller.get_yaml_available()


def test_controller_refuses_stale_validated_bytes_if_draft_changes_in_flight(
    tmp_path: Path,
    application: QCoreApplication,
) -> None:
    del application
    controller, coordinator = configured_controller(tmp_path)
    controller.open_document(new_document(payload()))
    controller.save_path_requested.connect(controller.save_path_selected)
    warnings: list[tuple[str, str]] = []
    controller.warning_requested.connect(lambda title, message: warnings.append((title, message)))
    destination = controller.workspace.configs / "dataset.yaml"

    assert controller.request_save_as()
    assert not controller.get_can_edit()
    assert controller.dataset_draft.add_fluid("Cyclopentane")
    coordinator.succeed({})

    assert not destination.exists()
    assert warnings == [
        (
            "Save Cancelled",
            "The configuration changed while its YAML was being validated. "
            "No file was written; save again.",
        )
    ]
    assert controller.get_dirty()
    assert controller.get_can_edit()


def test_controller_owns_reformat_external_change_and_replacement_guards(
    tmp_path: Path,
    application: QCoreApplication,
) -> None:
    del application
    controller, coordinator = configured_controller(tmp_path)
    workspace = controller.workspace
    assert workspace is not None
    source = workspace.configs / "imported.yaml"
    content = serialize_dataset_config(payload(visualization=True))
    source.write_bytes(content)
    document = DatasetConfigDocument(
        payload(visualization=True),
        source_path=source,
        source_sha256=sha256_bytes(content),
        workspace_owned=True,
        imported=True,
    )
    controller.open_document(document)
    reformats: list[str] = []
    external_changes: list[str] = []
    controller.reformat_confirmation_requested.connect(reformats.append)
    controller.external_change_requested.connect(lambda: external_changes.append("external"))

    assert controller.request_save()
    assert reformats == ["save"]
    assert coordinator.calls[-1][1] == "describe_capabilities"

    source.write_text("changed externally\n", encoding="utf-8")
    assert controller.request_save()
    assert external_changes == ["external"]
    assert coordinator.calls[-1][1] == "describe_capabilities"

    assert controller.visualization_draft.begin_edit_plot(0) is not None
    assert controller.dataset_draft.add_fluid("Cyclopentane")
    assert not controller.clear_document()
    assert controller.get_has_document()
    assert controller.clear_document(discard_confirmed=True)
    assert not controller.get_has_document()
    assert controller.visualization_draft.get_active_plot_draft() is None


def test_config_controller_import_is_qtcore_only_and_scientifically_isolated() -> None:
    code = """
import sys
import carnopy.app.config_controller
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


@pytest.mark.parametrize(
    ("document_type", "default_filename"),
    [
        ("model_sweep", "model-sweep.yaml"),
        ("preparation", "preparation.yaml"),
    ],
)
def test_generic_controller_owns_non_dataset_file_lifecycle(
    tmp_path: Path,
    application: QCoreApplication,
    document_type: str,
    default_filename: str,
) -> None:
    del application
    controller, coordinator = configured_controller(tmp_path)
    source = tmp_path / f"external-{document_type}.yaml"
    source_bytes = template_text(cast(Any, document_type)).encode("utf-8")
    source.write_bytes(source_bytes)
    source_payload = yaml.safe_load(source_bytes)
    assert isinstance(source_payload, dict)

    assert controller.import_configuration(str(source))
    assert coordinator.calls[-1] == (
        "configuration",
        "load_configuration",
        {"config_path": str(source.resolve())},
    )
    coordinator.succeed(
        {
            "document_type": document_type,
            "config": source_payload,
            "source_name": str(source),
            "source_sha256": sha256_bytes(source_bytes),
        }
    )

    assert controller.get_document_kind() == document_type
    assert controller.get_reformat_required()
    assert controller.get_yaml_available()
    assert controller.get_default_save_path().endswith(default_filename)
    assert controller.document is not None
    expected_bytes = serialize_configuration(source_payload)
    assert controller.document.yaml_bytes == expected_bytes

    assert controller.request_validation()
    assert coordinator.calls[-1] == (
        "configuration",
        "validate_configuration",
        {
            "yaml_text": expected_bytes.decode("utf-8"),
            "source_name": str(source.resolve()),
            "expected_document_type": document_type,
        },
    )
    coordinator.succeed({"document_type": document_type})

    destination = controller.workspace.configs / f"saved-{document_type}.yaml"
    assert controller.request_save_as(allow_reformat=True)
    assert controller.save_path_selected(str(destination))
    assert coordinator.calls[-1] == (
        "configuration",
        "validate_configuration",
        {
            "yaml_text": expected_bytes.decode("utf-8"),
            "source_name": str(destination),
            "expected_document_type": document_type,
        },
    )
    coordinator.succeed({"document_type": document_type})

    assert destination.read_bytes() == expected_bytes
    assert not controller.get_dirty()
    assert not controller.get_reformat_required()
    snapshot = controller.execution_snapshot(expected_document_type=cast(Any, document_type))
    assert snapshot.document_type == document_type
    assert snapshot.path == destination.resolve()
    with pytest.raises(ConfigDocumentError, match="open configuration is"):
        controller.execution_snapshot()

    assert controller.reload_source()
    assert coordinator.calls[-1] == (
        "configuration",
        "load_configuration",
        {"config_path": str(destination.resolve())},
    )
    coordinator.succeed(
        {
            "document_type": document_type,
            "config": source_payload,
            "source_name": str(destination),
            "source_sha256": sha256_bytes(expected_bytes),
        }
    )
    assert controller.get_document_kind() == document_type
    assert controller.document is not None
    assert controller.document.source_path == destination.resolve()


def test_dataset_controller_name_remains_a_compatibility_alias() -> None:
    assert DatasetConfigController is ConfigurationController
