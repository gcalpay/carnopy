from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable
from uuid import uuid4

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from carnopy.app.client import WorkerClient
from carnopy.app.protocol import WorkerEvent, encode_event


@pytest.fixture(scope="module")
def application() -> QApplication:
    existing = QApplication.instance()
    app = existing if isinstance(existing, QApplication) else QApplication([])
    yield app


def wait_for_request(
    application: QApplication,
    start: Callable[[WorkerClient], None],
) -> tuple[WorkerClient, list[dict[str, object]], list[dict[str, object]]]:
    del application
    client = WorkerClient()
    succeeded: list[dict[str, object]] = []
    failed: list[dict[str, object]] = []
    loop = QEventLoop()
    timed_out = False

    def timeout() -> None:
        nonlocal timed_out
        timed_out = True
        loop.quit()

    client.request_succeeded.connect(succeeded.append)
    client.request_failed.connect(failed.append)
    client.busy_changed.connect(lambda busy: None if busy else loop.quit())
    QTimer.singleShot(15_000, timeout)
    start(client)
    loop.exec()
    assert not timed_out
    assert not client.is_busy
    return client, succeeded, failed


def test_qprocess_client_runs_and_caches_capability_request(
    application: QApplication,
) -> None:
    client_holder: list[WorkerClient] = []
    busy_at_success: list[bool] = []

    def start(client: WorkerClient) -> None:
        client_holder.append(client)
        client.request_succeeded.connect(lambda _payload: busy_at_success.append(client.is_busy))
        client.start_request("describe_capabilities", {"model": "heos"})
        with pytest.raises(RuntimeError, match="already active"):
            client.start_request("describe_capabilities", {"model": "pr"})

    client, succeeded, failed = wait_for_request(application, start)

    assert failed == []
    assert succeeded and succeeded[0]["model"] == "heos"
    assert client is client_holder[0]
    assert client.cached_capabilities("heos") == succeeded[0]
    assert busy_at_success == [False]


def test_importing_qprocess_client_does_not_load_scientific_dependencies() -> None:
    code = """
import sys
import carnopy.app.client
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


def test_qprocess_client_rejects_mismatched_request_events(
    application: QApplication,
) -> None:
    del application
    client = WorkerClient()
    failures: list[dict[str, object]] = []
    client.request_failed.connect(failures.append)
    client._request_id = uuid4()

    client._handle_event_line(encode_event(WorkerEvent(request_id=uuid4(), type="accepted")))

    assert failures == [
        {
            "category": "protocol",
            "message": "worker event request ID does not match the active request",
        }
    ]
