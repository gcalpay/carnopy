from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import cast
from uuid import uuid4

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from carnopy.app.config_document import SavedConfigSnapshot
from carnopy.app.execution_page import DatasetExecutionPage
from carnopy.app.protocol import EventType, RequestType, WorkerEvent
from carnopy.app.request_coordinator import (
    DesktopRequestCoordinator,
    RequestOutcome,
)
from carnopy.app.workspace import initialize_workspace


class StubSession(QObject):
    event_received = Signal(object)
    completed = Signal(object)
    policy_changed = Signal()

    def __init__(self, request_type: RequestType) -> None:
        super().__init__()
        self.request_id = uuid4()
        self.request_type = request_type
        self.cooperative_cancel_available = False
        self.force_stop_available = False
        self.cancelled = False
        self.stopped = False

    def cancel(self) -> bool:
        if not self.cooperative_cancel_available:
            return False
        self.cancelled = True
        self.cooperative_cancel_available = False
        self.policy_changed.emit()
        return True

    def force_stop(self) -> bool:
        if not self.force_stop_available:
            return False
        self.stopped = True
        self.force_stop_available = False
        self.policy_changed.emit()
        return True


class StubCoordinator(QObject):
    busy_changed = Signal(bool)

    def __init__(self) -> None:
        super().__init__()
        self.is_busy = False
        self.started: list[tuple[str, RequestType, dict[str, object]]] = []
        self.session: StubSession | None = None

    def start_request(
        self,
        owner: str,
        request_type: RequestType,
        payload: dict[str, object],
    ) -> StubSession:
        self.started.append((owner, request_type, payload))
        self.session = StubSession(request_type)
        self.is_busy = True
        self.busy_changed.emit(True)
        return self.session

    def emit_event(self, event_type: str, payload: dict[str, object]) -> None:
        assert self.session is not None
        if event_type == "phase":
            self.session.cooperative_cancel_available = bool(payload.get("cancellable", False))
            self.session.policy_changed.emit()
        self.session.event_received.emit(
            WorkerEvent(
                request_id=self.session.request_id,
                type=cast(EventType, event_type),
                payload=payload,
            )
        )

    def finish(self, payload: dict[str, object]) -> None:
        assert self.session is not None
        terminal = WorkerEvent(
            request_id=self.session.request_id,
            type="result",
            payload=payload,
        )
        envelope: dict[str, object] = {
            "request_id": str(self.session.request_id),
            "request_type": self.session.request_type,
            "terminal_event": terminal.model_dump(mode="json"),
            "stderr": "",
            "exit_code": 0,
            "exit_status": "normal",
            "force_stopped": False,
            "cleanup_error": None,
        }
        outcome = RequestOutcome(
            request_id=self.session.request_id,
            request_type=self.session.request_type,
            owner="execution",
            terminal_event=terminal,
            client_failure=None,
            stderr="",
            exit_code=0,
            exit_status="normal",
            force_stopped=False,
            cleanup_error=None,
            terminal_envelope=envelope,
        )
        self.session.completed.emit(outcome)
        self.is_busy = False
        self.busy_changed.emit(False)


@pytest.fixture(scope="module")
def application() -> QApplication:
    existing = QApplication.instance()
    app = existing if isinstance(existing, QApplication) else QApplication([])
    yield app


def test_execution_page_uses_saved_digest_and_fixed_workspace_destinations(
    tmp_path: Path,
    application: QApplication,
) -> None:
    del application
    workspace = initialize_workspace(tmp_path / "workspace")
    config = workspace.configs / "dataset.yaml"
    content = b"schema_version: 2\n"
    config.write_bytes(content)
    snapshot = SavedConfigSnapshot(
        path=config,
        yaml_bytes=content,
        sha256=hashlib.sha256(content).hexdigest(),
    )
    stub = StubCoordinator()
    page = DatasetExecutionPage(cast(DesktopRequestCoordinator, stub))
    page.set_workspace(workspace)
    page.set_snapshot(snapshot)

    page.generate()

    assert stub.started == [
        (
            "execution",
            "generate_dataset",
            {
                "config_path": str(config),
                "expected_config_sha256": snapshot.sha256,
                "output_root": str(workspace.outputs),
                "figures_root": str(workspace.figures),
            },
        )
    ]
    assert "carnopy generate" in page.command.toPlainText()
    assert str(workspace.outputs) in page.command.toPlainText()


def test_execution_page_tracks_owned_progress_and_finalized_result(
    tmp_path: Path,
    application: QApplication,
) -> None:
    del application
    workspace = initialize_workspace(tmp_path / "workspace")
    config = workspace.configs / "dataset.yaml"
    config.write_bytes(b"value\n")
    snapshot = SavedConfigSnapshot(config, b"value\n", hashlib.sha256(b"value\n").hexdigest())
    stub = StubCoordinator()
    page = DatasetExecutionPage(cast(DesktopRequestCoordinator, stub))
    page.set_workspace(workspace)
    page.set_snapshot(snapshot)
    finalized: list[Path] = []
    page.run_finalized.connect(finalized.append)
    page.generate()
    stub.emit_event("phase", {"name": "generation", "cancellable": True})
    stub.emit_event("progress", {"completed": 7, "total": 10})
    run = workspace.outputs / "run"
    stub.finish(
        {
            "run_status": "completed_with_invalid_rows",
            "row_count": 10,
            "valid_row_count": 9,
            "invalid_row_count": 1,
            "output_directory": str(run),
            "visualization": None,
        }
    )

    assert page.progress.value() == 7
    assert page.progress.maximum() == 10
    assert "9 valid" in page.result.text()
    assert finalized == [run]
    assert page.inspect_button.isEnabled()


def test_execution_page_requests_cooperative_cancel_before_force_stop(
    tmp_path: Path,
    application: QApplication,
) -> None:
    del application
    workspace = initialize_workspace(tmp_path / "workspace")
    config = workspace.configs / "dataset.yaml"
    config.write_bytes(b"value\n")
    snapshot = SavedConfigSnapshot(config, b"value\n", hashlib.sha256(b"value\n").hexdigest())
    stub = StubCoordinator()
    page = DatasetExecutionPage(cast(DesktopRequestCoordinator, stub))
    page.set_workspace(workspace)
    page.set_snapshot(snapshot)
    page.generate()

    stub.emit_event("phase", {"name": "generation", "cancellable": True})
    assert page.cancel()
    assert stub.session is not None
    assert stub.session.cancelled
    assert not stub.session.stopped
    stub.session.force_stop_available = True
    stub.session.policy_changed.emit()
    assert not page.force_stop_button.isHidden()
    assert page.force_stop()
    assert stub.session.stopped
