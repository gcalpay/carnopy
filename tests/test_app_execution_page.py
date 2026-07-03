from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from carnopy.app.client import WorkerClient
from carnopy.app.config_document import SavedConfigSnapshot
from carnopy.app.execution_page import DatasetExecutionPage
from carnopy.app.protocol import WorkerEvent
from carnopy.app.workspace import initialize_workspace


class StubClient(QObject):
    event_received = Signal(object)
    request_succeeded = Signal(object)
    request_failed = Signal(object)
    request_finished = Signal(object)
    busy_changed = Signal(bool)

    def __init__(self) -> None:
        super().__init__()
        self.is_busy = False
        self.started: list[tuple[str, dict[str, object]]] = []
        self.active_id: UUID | None = None
        self.cancelled = False
        self.stopped = False

    def start_request(self, kind: str, payload: dict[str, object]) -> UUID:
        self.started.append((kind, payload))
        self.active_id = uuid4()
        self.is_busy = True
        self.busy_changed.emit(True)
        return self.active_id

    def request_cancel(self) -> bool:
        self.cancelled = True
        return True

    def force_stop(self) -> bool:
        self.stopped = True
        return True


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
    stub = StubClient()
    page = DatasetExecutionPage(cast(WorkerClient, stub))
    page.set_workspace(workspace)
    page.set_snapshot(snapshot)

    page.generate()

    assert stub.started == [
        (
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
    stub = StubClient()
    page = DatasetExecutionPage(cast(WorkerClient, stub))
    page.set_workspace(workspace)
    page.set_snapshot(snapshot)
    finalized: list[Path] = []
    page.run_finalized.connect(finalized.append)
    page.generate()
    request_id = stub.active_id
    assert request_id is not None

    stub.event_received.emit(
        WorkerEvent(
            request_id=request_id,
            type="phase",
            payload={"name": "generation", "cancellable": True},
        )
    )
    stub.event_received.emit(
        WorkerEvent(
            request_id=request_id,
            type="progress",
            payload={"completed": 7, "total": 10},
        )
    )
    run = workspace.outputs / "run"
    stub.request_succeeded.emit(
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


def test_execution_page_ignores_events_for_other_requests(
    tmp_path: Path,
    application: QApplication,
) -> None:
    del application
    workspace = initialize_workspace(tmp_path / "workspace")
    stub = StubClient()
    page = DatasetExecutionPage(cast(WorkerClient, stub))
    page.set_workspace(workspace)

    stub.event_received.emit(
        WorkerEvent(
            request_id=uuid4(),
            type="progress",
            payload={"completed": 99, "total": 100},
        )
    )

    assert page.progress.value() == 0


def test_execution_page_requests_cooperative_cancel_before_force_stop(
    tmp_path: Path,
    application: QApplication,
) -> None:
    del application
    workspace = initialize_workspace(tmp_path / "workspace")
    config = workspace.configs / "dataset.yaml"
    config.write_bytes(b"value\n")
    snapshot = SavedConfigSnapshot(config, b"value\n", hashlib.sha256(b"value\n").hexdigest())
    stub = StubClient()
    page = DatasetExecutionPage(cast(WorkerClient, stub))
    page.set_workspace(workspace)
    page.set_snapshot(snapshot)
    page.generate()

    assert page.cancel()
    assert stub.cancelled
    assert not stub.stopped
    page._show_force_stop()
    assert not page.force_stop_button.isHidden()
    assert page.force_stop()
    assert stub.stopped
