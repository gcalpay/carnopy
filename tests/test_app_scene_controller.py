from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import cast
from uuid import UUID

import pandas as pd
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication, QEvent, QObject, Signal

from carnopy.app.client import TransportOutcome, WorkerClient
from carnopy.app.protocol import EventType, RequestType, WorkerEvent
from carnopy.app.request_coordinator import DesktopRequestCoordinator
from carnopy.app.scene_build import BuildScenePayload, execute_scene_build
from carnopy.app.scene_contracts import SceneContractError, SceneProfile
from carnopy.app.scene_controller import SceneController
from carnopy.app.scene_leases import SceneLease, acquire_scene_session
from carnopy.app.scene_profiles import profile_scene
from carnopy.app.source_inspection import inspect_for_app
from carnopy.app.workspace import initialize_workspace


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
        self.cancelled: list[UUID] = []
        self.raise_on_start = False

    def start_request(
        self,
        request_id: UUID,
        request_type: RequestType,
        payload: Mapping[str, object] | None = None,
    ) -> None:
        if self.raise_on_start:
            raise RuntimeError("simulated scene worker start failure")
        if self.is_busy:
            raise RuntimeError("transport is busy")
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
        return self.is_busy and request_id == self.request_id

    def shutdown(self) -> None:
        assert not self.is_busy

    def emit_event(self, event_type: EventType, payload: dict[str, object]) -> None:
        assert self.request_id is not None
        self.event_received.emit(
            WorkerEvent(
                request_id=self.request_id,
                type=event_type,
                payload=payload,
            )
        )

    def finish(
        self,
        *,
        payload: dict[str, object] | None = None,
        terminal_type: EventType = "result",
        exit_code: int = 0,
        exit_status: str = "normal",
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
        self.payload = None
        self.transport_finished.emit(
            TransportOutcome(
                request_id=request_id,
                request_type=request_type,
                terminal_event=terminal,
                client_failure=None,
                stderr="",
                exit_code=exit_code,
                exit_status=exit_status,
                force_stopped=False,
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


@pytest.fixture(scope="module")
def scene_profile(tmp_path_factory: pytest.TempPathFactory) -> SceneProfile:
    source = tmp_path_factory.mktemp("scene-controller-source")
    dataset = source / "dataset.parquet"
    frame = pd.DataFrame(
        {
            "run_id": ["scene-controller-run"] * 4,
            "case_id": [0, 1, 2, 3],
            "mode": ["property_table"] * 4,
            "fluid": ["Propane"] * 4,
            "backend": ["coolprop"] * 4,
            "backend_model": ["heos"] * 4,
            "backend_version": ["test"] * 4,
            "phase": ["gas"] * 4,
            "backend_phase": ["gas"] * 4,
            "temperature_K": [320.0, 320.0, 300.0, 300.0],
            "pressure_Pa": [100_000.0, 250_000.0, 100_000.0, 250_000.0],
            "specific_enthalpy_J_kg": [420_000.0, 430_000.0, 240_000.0, 250_000.0],
            "valid": [True] * 4,
            "failure_layer": [None] * 4,
            "failure_code": [None] * 4,
            "failure_message": [None] * 4,
            "failure_property": [None] * 4,
            "backend_error_type": [None] * 4,
            "backend_error_message": [None] * 4,
        }
    )
    frame.to_parquet(dataset, index=False)
    _write_json(
        source / "report.json",
        {"report_schema_version": 1, "run_id": "scene-controller-run"},
    )
    _write_json(
        source / "metadata.json",
        {
            "metadata_schema_version": 1,
            "dataset_schema_version": 2,
            "run_id": "scene-controller-run",
            "run_status": "completed",
            "mode": "property_table",
            "backend": "coolprop",
            "backend_model": "heos",
            "row_count": 4,
            "valid_row_count": 4,
            "invalid_row_count": 0,
            "canonical_properties": ["specific_enthalpy"],
            "canonical_units": {
                "temperature_K": "K",
                "pressure_Pa": "Pa",
                "specific_enthalpy_J_kg": "J/kg",
            },
            "sampling": {
                "original": {},
                "materialized_si": {
                    "temperature": [320.0, 300.0],
                    "pressure": [100_000.0, 250_000.0],
                },
            },
            "artifact_hashes": {
                "dataset.parquet": _sha256(dataset),
                "report.json": _sha256(source / "report.json"),
            },
        },
    )
    return profile_scene(inspect_for_app(source).scene_bindings[0])


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _controller() -> tuple[SceneController, StubTransport]:
    transport = StubTransport()
    coordinator = DesktopRequestCoordinator(cast(WorkerClient, transport))
    return SceneController(coordinator), transport


def _accept_profile(
    controller: SceneController,
    transport: StubTransport,
    profile: SceneProfile,
) -> None:
    assert controller.draft.copy_binding(profile.binding)
    assert controller.get_state() == "unprofiled"
    assert controller.profile()
    assert transport.request_type == "profile_scene"
    transport.finish(payload=profile.model_dump(mode="json"))
    assert controller.draft.profile_snapshot() == profile
    assert controller.get_state() == "ready"


def _execute_current_build(transport: StubTransport) -> dict[str, object]:
    assert transport.request_type == "build_scene"
    assert transport.payload is not None
    payload = BuildScenePayload.model_validate(transport.payload)
    return execute_scene_build(
        payload,
        emit=lambda _event_type, _payload: None,
        checkpoint=lambda: None,
    )


def _build_initial_scene(
    controller: SceneController,
    transport: StubTransport,
) -> None:
    assert controller.build()
    result = _execute_current_build(transport)
    transport.finish(payload=result)
    assert controller.get_has_scene()
    assert controller.get_state() == "succeeded"


def _change_request(controller: SceneController) -> None:
    current = controller.draft.get_scalar_field()
    replacement = "pressure" if current != "pressure" else "temperature"
    assert controller.draft.set_scalar_field(replacement)
    assert controller.get_settings_stale()


def test_profile_uses_global_scene_owner_and_locks_submitted_draft(
    application: QCoreApplication,
    scene_profile: SceneProfile,
) -> None:
    del application
    controller, transport = _controller()
    assert controller.draft.copy_binding(scene_profile.binding)
    messages: list[str] = []
    controller.draft.message.connect(messages.append)

    blocker = controller.coordinator.start_request("inspection", "inspect_source", {})
    assert blocker.owner == "inspection"
    assert not controller.profile()
    transport.finish(payload={})

    assert controller.profile()
    assert controller.coordinator.active_owner == "scene"
    assert controller.get_draft_locked()
    assert not controller.draft.clear()
    assert "locked" in messages[-1]
    with pytest.raises(SceneContractError, match="locked"):
        controller.draft.create_profile_submission()

    transport.emit_event(
        "phase",
        {"name": "scene_profiling", "cancellable": True},
    )
    assert controller.get_cancellation_available()
    transport.finish(payload=scene_profile.model_dump(mode="json"))

    assert not controller.get_draft_locked()
    assert not controller.get_operation_active()
    assert controller.draft.profile_snapshot() == scene_profile
    assert controller.get_state() == "ready"


def test_verified_replacement_retires_only_discarded_or_superseded_leases(
    application: QCoreApplication,
    scene_profile: SceneProfile,
    tmp_path: Path,
) -> None:
    del application
    workspace = initialize_workspace(tmp_path / "workspace")
    scene_session = acquire_scene_session(workspace.root)
    controller, transport = _controller()
    retired: list[SceneLease] = []
    controller.lease_retirement_requested.connect(retired.append)
    controller.set_scene_session(scene_session)
    try:
        _accept_profile(controller, transport, scene_profile)
        assert controller.build()
        transport.emit_event(
            "phase",
            {"name": "scene_geometry", "cancellable": True},
        )
        transport.emit_event("progress", {"completed": 1, "total": 4})
        assert controller.get_cancellation_available()
        assert (controller.get_progress_completed(), controller.get_progress_total()) == (1, 4)
        initial_result = _execute_current_build(transport)
        transport.emit_event(
            "phase",
            {
                "name": "scene_publication",
                "cancellable": False,
                "termination_protected": True,
            },
        )
        assert controller.get_protected_finalization()
        assert not controller.cancel()
        transport.finish(payload=initial_result)
        initial_scene = controller.current_scene_snapshot()
        assert initial_scene is not None
        assert retired == []

        _change_request(controller)
        assert controller.build()
        cancelled_lease = BuildScenePayload.model_validate(transport.payload).lease.lease_id
        transport.emit_event(
            "phase",
            {"name": "scene_geometry", "cancellable": True},
        )
        assert controller.cancel()
        assert transport.cancelled
        transport.finish(
            terminal_type="cancelled",
            payload={"code": "cancelled", "message": "cancelled by test"},
        )
        assert controller.current_scene_snapshot() is initial_scene
        assert controller.get_state() == "cancelled"
        assert [lease.lease_id for lease in retired] == [cancelled_lease]

        assert controller.build()
        failed_lease = BuildScenePayload.model_validate(transport.payload).lease.lease_id
        tampered_result = _execute_current_build(transport)
        tampered_result["content_id"] = "scene-content-" + "0" * 64
        transport.finish(payload=tampered_result)
        assert controller.current_scene_snapshot() is initial_scene
        assert controller.get_issue_category() == "integrity"
        assert controller.get_issue_code() == "scene_integrity_error"
        assert [lease.lease_id for lease in retired] == [cancelled_lease, failed_lease]

        assert controller.build()
        replacement_result = _execute_current_build(transport)
        transport.finish(payload=replacement_result)
        replacement = controller.current_scene_snapshot()
        assert replacement is not None and replacement is not initial_scene
        assert not controller.get_settings_stale()
        assert controller.get_state() == "succeeded"
        assert retired[-1] == initial_scene.lease
    finally:
        scene_session.close()


def test_source_change_preserves_snapshot_and_blocks_old_binding(
    application: QCoreApplication,
    scene_profile: SceneProfile,
    tmp_path: Path,
) -> None:
    del application
    workspace = initialize_workspace(tmp_path / "workspace")
    scene_session = acquire_scene_session(workspace.root)
    controller, transport = _controller()
    retired: list[SceneLease] = []
    controller.lease_retirement_requested.connect(retired.append)
    controller.set_scene_session(scene_session)
    try:
        _accept_profile(controller, transport, scene_profile)
        _build_initial_scene(controller, transport)
        accepted = controller.current_scene_snapshot()
        assert accepted is not None

        _change_request(controller)
        assert controller.build()
        failed_lease = BuildScenePayload.model_validate(transport.payload).lease.lease_id
        transport.finish(
            terminal_type="error",
            payload={
                "category": "execution",
                "code": "scene_source_changed",
                "message": "source revision changed",
            },
            exit_code=1,
        )

        assert controller.current_scene_snapshot() is accepted
        assert controller.get_source_stale()
        assert controller.get_draft_source_stale()
        assert controller.get_state() == "source_stale"
        assert not controller.get_can_build()
        assert not controller.get_can_profile()
        assert [lease.lease_id for lease in retired] == [failed_lease]

        refreshed = scene_profile.binding.model_copy(
            update={"inspection_revision": "d" * 64},
            deep=True,
        )
        assert controller.draft.copy_binding(refreshed)
        assert controller.get_source_stale()
        assert not controller.get_draft_source_stale()
        assert controller.get_can_profile()
    finally:
        scene_session.close()


def test_start_failure_releases_candidate_and_unlocks_draft(
    application: QCoreApplication,
    scene_profile: SceneProfile,
    tmp_path: Path,
) -> None:
    del application
    workspace = initialize_workspace(tmp_path / "workspace")
    scene_session = acquire_scene_session(workspace.root)
    controller, transport = _controller()
    retired: list[SceneLease] = []
    controller.lease_retirement_requested.connect(retired.append)
    controller.set_scene_session(scene_session)
    try:
        _accept_profile(controller, transport, scene_profile)
        transport.raise_on_start = True

        assert not controller.build()

        assert len(retired) == 1
        assert not controller.get_draft_locked()
        assert not controller.get_operation_active()
        assert controller.get_issue_code() == "worker_start_failed"
        assert controller.current_scene_snapshot() is None
    finally:
        scene_session.close()


def test_scene_controller_import_keeps_heavy_modules_out_of_gui_process() -> None:
    code = r"""
import sys
from carnopy.app.scene_controller import SceneController
assert SceneController is not None
blocked = {
    "CoolProp", "numpy", "pandas", "pyarrow", "matplotlib", "vtk",
    "carnopy.app.worker", "carnopy.app.scene_profiles", "carnopy.app.scene_geometry",
    "carnopy.app.scene_topology", "carnopy.app.scene_writer",
}
loaded = sorted(name for name in blocked if name in sys.modules)
if loaded:
    raise SystemExit("heavy modules loaded: " + ", ".join(loaded))
"""
    completed = subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr or completed.stdout
