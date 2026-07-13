from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from uuid import UUID, uuid4

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MPLBACKEND", "Agg")
pytest.importorskip("PySide6")

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from carnopy.app.client import TransportOutcome, WorkerClient
from carnopy.app.export_cleanup import ImageExportFinalizer
from carnopy.app.plot_staging import cleanup_plot_staging, create_plot_staging
from carnopy.app.protocol import WorkerEvent, encode_event
from carnopy.app.request_coordinator import DesktopRequestCoordinator, RequestOutcome


@pytest.fixture(scope="module")
def application() -> QApplication:
    existing = QApplication.instance()
    app = existing if isinstance(existing, QApplication) else QApplication([])
    yield app


def wait_for_transport(
    application: QApplication,
    start: Callable[[WorkerClient, UUID], None],
) -> tuple[WorkerClient, list[WorkerEvent], TransportOutcome]:
    del application
    client = WorkerClient()
    events: list[WorkerEvent] = []
    outcomes: list[TransportOutcome] = []
    loop = QEventLoop()
    timed_out = False
    request_id = uuid4()

    def timeout() -> None:
        nonlocal timed_out
        timed_out = True
        loop.quit()

    client.event_received.connect(events.append)
    client.transport_finished.connect(outcomes.append)
    client.transport_finished.connect(lambda _outcome: loop.quit())
    QTimer.singleShot(15_000, timeout)
    start(client, request_id)
    loop.exec()
    assert not timed_out
    assert not client.is_busy
    assert len(outcomes) == 1
    return client, events, outcomes[0]


def test_qprocess_client_emits_one_transport_outcome(
    application: QApplication,
) -> None:
    def start(client: WorkerClient, request_id: UUID) -> None:
        client.start_request(request_id, "describe_capabilities", {"model": "heos"})
        with pytest.raises(RuntimeError, match="already active"):
            client.start_request(uuid4(), "describe_capabilities", {"model": "pr"})

    client, events, outcome = wait_for_transport(application, start)

    assert [event.type for event in events] == ["accepted", "result"]
    assert outcome.request_type == "describe_capabilities"
    assert outcome.successful
    assert outcome.terminal_event is not None
    assert outcome.terminal_event.payload["model"] == "heos"
    assert outcome.client_failure is None
    assert outcome.force_stopped is False
    client.deleteLater()
    application.processEvents()


def test_qprocess_client_reports_failed_start_once(
    application: QApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from carnopy.app import client as client_module

    monkeypatch.setattr(client_module.sys, "executable", str(tmp_path / "missing-python"))

    def start(client: WorkerClient, request_id: UUID) -> None:
        client.start_request(request_id, "describe_capabilities", {"model": "heos"})

    client, events, outcome = wait_for_transport(application, start)

    assert events == []
    assert outcome.client_failure is not None
    assert outcome.client_failure["code"] == "failed_to_start"
    assert outcome.exit_status == "failed_to_start"
    client.deleteLater()
    application.processEvents()


def test_importing_transport_and_coordinator_does_not_load_scientific_dependencies() -> None:
    code = """
import sys
import carnopy.app.client
import carnopy.app.request_coordinator
for name in (
    "CoolProp", "numpy", "pandas", "pyarrow", "matplotlib",
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
    ("line", "code"),
    [
        ("not-json", "invalid_event"),
        (
            encode_event(WorkerEvent(request_id=uuid4(), type="accepted")).strip(),
            "request_id_mismatch",
        ),
    ],
)
def test_qprocess_client_records_protocol_failures(line: str, code: str) -> None:
    client = WorkerClient()
    client._request_id = uuid4()
    client._request_type = "describe_capabilities"

    client._handle_event_line(line)

    assert client._client_failure is not None
    assert client._client_failure["code"] == code


def test_coordinator_runs_plot_finalizer_after_worker_exit(
    application: QApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import pandas as pd

    from carnopy.app.source_inspection import inspect_for_app
    from carnopy.app.workspace import initialize_workspace

    monkeypatch.setenv("MPLCONFIGDIR", str(tmp_path / "mpl"))
    workspace = initialize_workspace(tmp_path / "workspace")
    dataset = tmp_path / "dataset.parquet"
    pd.DataFrame(
        {
            "run_id": ["run"] * 4,
            "case_id": [0, 1, 2, 3],
            "mode": ["property_table"] * 4,
            "fluid": ["Propane"] * 4,
            "backend": ["coolprop"] * 4,
            "backend_model": ["heos"] * 4,
            "backend_version": ["test"] * 4,
            "phase": ["gas"] * 4,
            "valid": [True] * 4,
            "temperature_K": [280.0, 300.0, 280.0, 300.0],
            "pressure_Pa": [100_000.0, 100_000.0, 200_000.0, 200_000.0],
            "mass_density_kg_m3": [1.9, 1.8, 3.9, 3.7],
        }
    ).to_parquet(dataset, index=False)
    revision = inspect_for_app(dataset).revision
    lease = create_plot_staging(workspace.root)
    finalizer = ImageExportFinalizer(lease)
    client = WorkerClient()
    coordinator = DesktopRequestCoordinator(client)
    outcomes: list[RequestOutcome] = []
    loop = QEventLoop()
    session = coordinator.start_request(
        "plot",
        "render_plot",
        {
            "workspace_path": str(workspace.root),
            "source_path": str(dataset),
            "inspection_revision": revision,
            "plot_name": "density-curves",
            "format": "png",
            "plot": {
                "kind": "property_curves",
                "property": "mass_density",
                "x": "temperature",
            },
            "staging": lease.worker_payload(),
        },
        finalizer=finalizer,
    )
    session.completed.connect(outcomes.append)
    coordinator.busy_changed.connect(lambda busy: None if busy else loop.quit())
    QTimer.singleShot(15_000, loop.quit)
    loop.exec()

    assert len(outcomes) == 1
    assert outcomes[0].successful
    payload = outcomes[0].result_payload
    assert payload is not None
    assert Path(str(payload["image_path"])).is_file()
    staging_root = workspace.private_directory / "plot-staging"
    assert staging_root.is_dir()
    assert list(staging_root.iterdir()) == []
    coordinator.deleteLater()
    client.deleteLater()
    application.processEvents()


def test_image_export_finalizer_is_idempotent_and_structures_cleanup_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from carnopy.app import export_cleanup
    from carnopy.app.workspace import initialize_workspace

    workspace = initialize_workspace(tmp_path / "workspace")
    lease = create_plot_staging(workspace.root)
    calls = 0

    def fail_cleanup(*_args: object, **_kwargs: object) -> None:
        nonlocal calls
        calls += 1
        raise RuntimeError("simulated cleanup failure")

    monkeypatch.setattr(export_cleanup, "cleanup_plot_staging", fail_cleanup)
    finalizer = ImageExportFinalizer(lease)

    first = finalizer.finish(False)
    second = finalizer.finish(True)

    assert first == "plot staging cleanup failed: simulated cleanup failure"
    assert second == first
    assert calls == 1
    cleanup_plot_staging(lease, successful=False)
