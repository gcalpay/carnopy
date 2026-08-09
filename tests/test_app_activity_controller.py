from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from uuid import UUID

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication, QEvent, QObject, Signal

from carnopy.app.activity_controller import ActivityController
from carnopy.app.jobs import JobStore
from carnopy.app.request_coordinator import DesktopRequestCoordinator
from carnopy.app.workspace import Workspace, initialize_workspace


class StubCoordinator(QObject):
    busy_changed = Signal(bool)

    def __init__(self) -> None:
        super().__init__()
        self.active_session: SimpleNamespace | None = None


@pytest.fixture(scope="module")
def application() -> QCoreApplication:
    existing = QCoreApplication.instance()
    app = existing if isinstance(existing, QCoreApplication) else QCoreApplication([])
    yield app
    if type(app) is QCoreApplication:
        app.quit()
        app.deleteLater()
        QCoreApplication.sendPostedEvents(app, QEvent.Type.DeferredDelete)


def controller_for(workspace: Workspace) -> tuple[ActivityController, StubCoordinator]:
    coordinator = StubCoordinator()
    controller = ActivityController(cast(DesktopRequestCoordinator, coordinator))
    controller.set_workspace(workspace)
    return controller, coordinator


def start_record(
    store: JobStore,
    *,
    request_id: str,
    operation: str = "generate",
) -> dict[str, object]:
    return cast(
        dict[str, object],
        store.start(
            request_id=request_id,
            operation=operation,
            config_relative_path="configs/dataset.yaml",
            yaml_snapshot="schema_version: 2\n",
            config_sha256="a" * 64,
        ),
    )


def finish_generation(store: JobStore, record: dict[str, object], workspace: Workspace) -> None:
    request_id = str(record["request_id"])
    store.finish(
        record,
        {
            "request_id": request_id,
            "request_type": "generate_dataset",
            "terminal_event": {
                "protocol_version": 1,
                "request_id": request_id,
                "type": "result",
                "payload": {
                    "run_id": "run-id",
                    "run_status": "completed",
                    "output_directory": str(workspace.outputs / "run-id"),
                    "row_count": 10,
                    "valid_row_count": 9,
                    "invalid_row_count": 1,
                    "spec_id": "spec",
                    "generation_context_id": "context",
                    "output_request_id": "output",
                    "visualization": {
                        "visualization_request_id": "visualization",
                        "status": "completed",
                        "figure_directory": str(workspace.figures / "run-id"),
                        "report_path": str(
                            workspace.figures / "run-id" / "visualization-report.json"
                        ),
                    },
                },
            },
            "stderr": "",
            "exit_code": 0,
            "exit_status": "normal",
            "force_stopped": False,
        },
    )


def test_activity_projects_schema_one_records_and_effective_interruption(
    tmp_path: Path,
    application: QCoreApplication,
) -> None:
    del application
    workspace = initialize_workspace(tmp_path / "workspace")
    store = JobStore(workspace.private_directory)
    request_id = "00000000-0000-0000-0000-000000000001"
    start_record(store, request_id=request_id)
    controller, coordinator = controller_for(workspace)

    [row] = controller.records_model.rows()
    assert row["recordId"] == request_id
    assert row["state"] == "interrupted"
    assert row["stateLabel"] == "Interrupted"
    assert row["configurationPath"] == "configs/dataset.yaml"
    assert row["configurationSha256"] == "a" * 64

    coordinator.active_session = SimpleNamespace(
        owner="execution",
        request_id=UUID(request_id),
    )
    controller.refresh_records()
    assert controller.records_model.rows()[0]["state"] == "running"
    assert store.load()[0].data is not None
    assert store.load()[0].data["status"] == "running"


def test_activity_selected_generation_exposes_typed_actions_and_diagnostic_text(
    tmp_path: Path,
    application: QCoreApplication,
) -> None:
    del application
    workspace = initialize_workspace(tmp_path / "workspace")
    store = JobStore(workspace.private_directory)
    request_id = "00000000-0000-0000-0000-000000000002"
    record = start_record(store, request_id=request_id)
    finish_generation(store, record, workspace)
    controller, _coordinator = controller_for(workspace)

    assert controller.select_record(request_id)

    assert controller.get_selected_record_state() == "completed"
    assert controller.get_can_inspect_run()
    assert controller.get_can_view_plots()
    assert controller.get_can_remove_record()
    summary = controller.get_selected_record_summary()
    assert summary["outputDirectory"] == str(workspace.outputs / "run-id")
    assert summary["visualizationReportPath"] == str(
        workspace.figures / "run-id" / "visualization-report.json"
    )
    assert '"terminal_envelope"' in controller.get_selected_diagnostic_text()


@pytest.mark.parametrize(
    ("operation", "owner", "run_key", "run_id"),
    [
        ("execute_sweep", "sweep", "sweep_run_id", "sweep-run"),
        ("execute_preparation", "preparation", "preparation_run_id", "preparation-run"),
    ],
)
def test_activity_projects_finalized_workflow_outputs_as_inspectable(
    tmp_path: Path,
    application: QCoreApplication,
    operation: str,
    owner: str,
    run_key: str,
    run_id: str,
) -> None:
    del application
    workspace = initialize_workspace(tmp_path / owner)
    store = JobStore(workspace.private_directory)
    record = store.start(
        request_id=f"00000000-0000-0000-0000-{len(owner):012d}",
        operation=operation,
        config_relative_path="configs/workflow.yaml",
        yaml_snapshot="schema_version: 2\n",
        config_sha256="a" * 64,
        owner=owner,
        plan_identity={"plan_id": "b" * 64},
        preparation_source_identity=(
            {"inspection_revision": "c" * 64} if owner == "preparation" else None
        ),
    )
    request_id = str(record["request_id"])
    output = workspace.outputs / run_id
    store.finish(
        record,
        {
            "request_id": request_id,
            "request_type": operation,
            "terminal_event": {
                "protocol_version": 1,
                "request_id": request_id,
                "type": "result",
                "payload": {run_key: run_id, "output_directory": str(output)},
            },
            "stderr": "",
            "exit_code": 0,
            "exit_status": "normal",
            "force_stopped": False,
        },
    )

    controller, _coordinator = controller_for(workspace)
    assert controller.select_record(request_id)
    assert controller.get_can_inspect_run()
    assert controller.get_selected_record_summary()["runId"] == run_id
    assert controller.get_selected_record_summary()["outputDirectory"] == str(output)


def test_activity_record_removal_never_removes_generated_artifacts(
    tmp_path: Path,
    application: QCoreApplication,
) -> None:
    del application
    workspace = initialize_workspace(tmp_path / "workspace")
    output = workspace.outputs / "run-id"
    output.mkdir()
    store = JobStore(workspace.private_directory)
    request_id = "00000000-0000-0000-0000-000000000003"
    record = start_record(store, request_id=request_id)
    finish_generation(store, record, workspace)
    controller, _coordinator = controller_for(workspace)

    assert controller.select_record(request_id)
    assert controller.remove_selected_record()

    assert controller.records_model.rows() == ()
    assert output.is_dir()


def test_activity_keeps_unreadable_records_visible(
    tmp_path: Path,
    application: QCoreApplication,
) -> None:
    del application
    workspace = initialize_workspace(tmp_path / "workspace")
    store = JobStore(workspace.private_directory)
    store.directory.mkdir()
    malformed = store.directory / "malformed.json"
    malformed.write_text("{", encoding="utf-8")
    controller, _coordinator = controller_for(workspace)

    [row] = controller.records_model.rows()
    assert row["readable"] is False
    assert row["state"] == "unreadable"
    assert controller.select_record("malformed.json")
    assert "Unreadable activity record" in controller.get_selected_diagnostic_text()


def test_recovery_removes_only_selected_identity_checked_direct_candidates(
    tmp_path: Path,
    application: QCoreApplication,
) -> None:
    del application
    workspace = initialize_workspace(tmp_path / "workspace")
    first = workspace.outputs / ".20260702T120000Z_property_1a2b3c4d.staging"
    second = workspace.outputs / ".20260702T120001Z_saturation_2a2b3c4d.staging"
    first.mkdir()
    second.mkdir()
    controller, _coordinator = controller_for(workspace)

    assert controller.get_recovery_state() == "ready"
    assert controller.recovery_candidates_model.get_count() == 2
    assert controller.set_recovery_selected(0, True)
    assert controller.get_selected_recovery_count() == 1
    assert controller.selected_recovery_paths() == (first,)
    assert controller.get_selected_recovery_paths() == [str(first)]
    assert controller.property("selectedRecoveryPaths") == [str(first)]
    assert controller.get_selected_recovery_paths_text() == str(first)
    assert controller.remove_selected_recovery()

    assert not first.exists()
    assert second.is_dir()
    assert controller.get_recovery_state() == "ready"
    assert controller.get_selected_recovery_count() == 0


def test_recovery_refuses_a_replaced_selected_candidate(
    tmp_path: Path,
    application: QCoreApplication,
) -> None:
    del application
    workspace = initialize_workspace(tmp_path / "workspace")
    candidate = workspace.outputs / ".20260702T120000Z_property_1a2b3c4d.staging"
    candidate.mkdir()
    controller, _coordinator = controller_for(workspace)
    assert controller.set_recovery_selected(0, True)
    moved = workspace.outputs / "moved"
    candidate.rename(moved)
    candidate.mkdir()

    assert not controller.remove_selected_recovery()

    assert candidate.is_dir()
    assert moved.is_dir()
    assert controller.get_recovery_state() == "failed"
    assert "replaced after selection" in controller.get_recovery_issue()


def test_activity_controller_import_keeps_worker_and_scientific_modules_unloaded() -> None:
    code = """
import sys
import carnopy.app.activity_controller
blocked = [
    name for name in (
        'carnopy.app.source_inspection',
        'carnopy.app.table_preview',
        'pandas',
        'pyarrow',
        'numpy',
        'CoolProp',
        'matplotlib',
    )
    if name in sys.modules
]
print(','.join(blocked))
"""
    completed = subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == ""
