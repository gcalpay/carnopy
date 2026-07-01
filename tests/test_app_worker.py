from __future__ import annotations

import importlib
import io
import json
import subprocess
import sys
from pathlib import Path
from threading import Event
from uuid import uuid4

import pytest
from pydantic import ValidationError

from carnopy._execution import ExecutionCancelled, ExecutionControl
from carnopy.app.protocol import PROTOCOL_VERSION, WorkerEvent, encode_event, parse_request
from carnopy.app.worker import _listen_for_cancellation, main
from carnopy.config.io import load_config_file
from carnopy.domain.failures import OutputError
from carnopy.pipeline import run_generation


def _request(request_type: str, payload: dict[str, object]) -> tuple[str, str]:
    request_id = str(uuid4())
    return request_id, json.dumps(
        {
            "protocol_version": PROTOCOL_VERSION,
            "request_id": request_id,
            "type": request_type,
            "payload": payload,
        }
    )


def _events(stream: io.StringIO) -> list[dict[str, object]]:
    return [json.loads(line) for line in stream.getvalue().splitlines()]


def test_protocol_round_trip_and_version_rejection() -> None:
    request_id, line = _request("validate_config", {"config_path": "config.yaml"})
    request = parse_request(line)
    assert str(request.request_id) == request_id
    assert request.type == "validate_config"

    event = WorkerEvent(request_id=request.request_id, type="accepted")
    assert json.loads(encode_event(event))["protocol_version"] == PROTOCOL_VERSION

    invalid = json.loads(line)
    invalid["protocol_version"] = 2
    with pytest.raises(ValidationError):
        parse_request(json.dumps(invalid))


def test_worker_validates_without_calling_cli(property_config_path: Path) -> None:
    request_id, line = _request("validate_config", {"config_path": str(property_config_path)})
    stdout = io.StringIO()
    stderr = io.StringIO()

    assert main(io.StringIO(line + "\n"), stdout, stderr) == 0

    events = _events(stdout)
    assert [event["type"] for event in events] == ["accepted", "phase", "result"]
    assert all(event["request_id"] == request_id for event in events)
    result = events[-1]["payload"]
    assert isinstance(result, dict)
    assert result["mode"] == "property_table"


def test_worker_describes_model_capabilities() -> None:
    _, line = _request("describe_capabilities", {"model": "pr"})
    stdout = io.StringIO()

    assert main(io.StringIO(line + "\n"), stdout, io.StringIO()) == 0

    result = _events(stdout)[-1]
    assert result["type"] == "result"
    payload = result["payload"]
    assert isinstance(payload, dict)
    assert payload["backend"] == "coolprop"
    assert payload["model"] == "pr"
    assert payload["fluids"]
    properties = payload["properties"]
    assert isinstance(properties, list)
    assert "dynamic_viscosity" not in {
        property_metadata["name"]
        for property_metadata in properties
        if isinstance(property_metadata, dict)
    }


def test_worker_generates_structured_progress_and_result(
    property_config_path: Path,
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "runs"
    request_id, line = _request(
        "generate_dataset",
        {
            "config_path": str(property_config_path),
            "output_root": str(output_root),
            "figures_root": str(tmp_path / "figures"),
        },
    )
    stdout = io.StringIO()

    assert main(io.StringIO(line + "\n"), stdout, io.StringIO()) == 0

    events = _events(stdout)
    assert events[0]["type"] == "accepted"
    assert events[-1]["type"] == "result"
    assert all(event["request_id"] == request_id for event in events)
    assert any(event["type"] == "progress" for event in events)
    phases = [
        event["payload"]["name"]
        for event in events
        if event["type"] == "phase" and isinstance(event["payload"], dict)
    ]
    assert phases == [
        "validation",
        "backend_initialization",
        "generation",
        "writing",
        "finalization",
    ]
    result = events[-1]["payload"]
    assert isinstance(result, dict)
    assert Path(str(result["output_directory"])).is_dir()


def test_importing_worker_protocol_does_not_load_execution_dependencies() -> None:
    code = """
import sys
import carnopy.app.protocol
import carnopy.app.worker
for name in (
    "CoolProp", "numpy", "pandas", "pyarrow", "matplotlib",
    "carnopy.cli", "carnopy.pipeline",
):
    if name in sys.modules:
        raise SystemExit(name)
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_worker_reports_malformed_request_as_protocol_error() -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()

    assert main(io.StringIO("not-json\n"), stdout, stderr) == 2

    events = _events(stdout)
    assert len(events) == 1
    assert events[0]["protocol_version"] == PROTOCOL_VERSION
    assert events[0]["request_id"] == "00000000-0000-0000-0000-000000000000"
    assert events[0]["type"] == "error"
    payload = events[0]["payload"]
    assert isinstance(payload, dict)
    assert payload["category"] == "protocol"
    assert str(payload["message"]).startswith("invalid worker request")


def test_cancel_listener_accepts_only_matching_cancel_request() -> None:
    request_id = uuid4()
    _, mismatched = _request("cancel", {})
    matching = json.dumps(
        {
            "protocol_version": PROTOCOL_VERSION,
            "request_id": str(request_id),
            "type": "cancel",
            "payload": {},
        }
    )
    cancelled = Event()
    stderr = io.StringIO()

    _listen_for_cancellation(
        io.StringIO(mismatched + "\n" + matching + "\n"),
        stderr,
        request_id,
        cancelled,
    )

    assert cancelled.is_set()
    assert "mismatched" in stderr.getvalue()


@pytest.mark.parametrize(
    "fixture_name",
    ["property_config_path", "saturation_config_path", "vapor_config_path"],
)
def test_generation_control_reports_all_rows(
    request: pytest.FixtureRequest,
    fixture_name: str,
    tmp_path: Path,
) -> None:
    config_path = request.getfixturevalue(fixture_name)
    phases: list[tuple[str, bool]] = []
    progress: list[tuple[int, int]] = []
    control = ExecutionControl(
        cancellation_requested=lambda: False,
        on_phase=lambda name, cancellable: phases.append((name, cancellable)),
        on_progress=lambda completed, total: progress.append((completed, total)),
        minimum_progress_interval=0.0,
    )

    result = run_generation(
        load_config_file(config_path),
        tmp_path / fixture_name,
        execution=control,
    )

    assert progress[-1] == (result.row_count, result.row_count)
    assert [name for name, _ in phases] == [
        "validation",
        "backend_initialization",
        "generation",
        "writing",
        "finalization",
    ]


def test_cooperative_cancellation_removes_staging_directory(
    property_config_path: Path,
    tmp_path: Path,
) -> None:
    cancelled = Event()

    def phase(name: str, _cancellable: bool) -> None:
        if name == "generation":
            cancelled.set()

    control = ExecutionControl(
        cancellation_requested=cancelled.is_set,
        on_phase=phase,
        on_progress=lambda _completed, _total: None,
    )
    output_root = tmp_path / "runs"

    with pytest.raises(ExecutionCancelled):
        run_generation(
            load_config_file(property_config_path),
            output_root,
            execution=control,
        )

    assert output_root.is_dir()
    assert list(output_root.iterdir()) == []


def test_handled_generation_failure_removes_staging_directory(
    property_config_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pipeline = importlib.import_module("carnopy.pipeline")

    def fail_write(*_args: object, **_kwargs: object) -> list[str]:
        raise OutputError("controlled write failure")

    monkeypatch.setattr(pipeline, "write_dataset_formats", fail_write)
    output_root = tmp_path / "runs"

    with pytest.raises(OutputError, match="controlled write failure"):
        run_generation(load_config_file(property_config_path), output_root)

    assert output_root.is_dir()
    assert list(output_root.iterdir()) == []


def test_cancellation_is_ignored_after_finalization_boundary() -> None:
    cancelled = Event()
    control = ExecutionControl(
        cancellation_requested=cancelled.is_set,
        on_phase=lambda _name, _cancellable: None,
        on_progress=lambda _completed, _total: None,
    )
    control.disable_cancellation()
    cancelled.set()

    control.raise_if_cancelled()
