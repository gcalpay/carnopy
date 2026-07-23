from __future__ import annotations

import hashlib
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
from carnopy.app.protocol import (
    PROTOCOL_VERSION,
    WorkerEvent,
    encode_event,
    parse_event,
    parse_request,
)
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
    assert parse_event(encode_event(event)).request_id == request.request_id

    invalid = json.loads(line)
    invalid["protocol_version"] = 2
    with pytest.raises(ValidationError):
        parse_request(json.dumps(invalid))

    invalid_event = json.loads(encode_event(event))
    invalid_event["protocol_version"] = 2
    with pytest.raises(ValidationError):
        parse_event(json.dumps(invalid_event))


def test_worker_validates_without_calling_cli(property_config_path: Path) -> None:
    request_id, line = _request(
        "validate_config",
        {
            "config_path": str(property_config_path),
            "expected_config_sha256": hashlib.sha256(property_config_path.read_bytes()).hexdigest(),
        },
    )
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
    assert payload["models"] == ["heos", "pr", "srk"]
    assert payload["modes"] == [
        "property_table",
        "saturation_table",
        "vapor_mass_fraction_table",
    ]
    assert payload["dataset_formats"] == ["csv", "parquet"]
    assert payload["reference_state"] == {
        "policy": "coolprop_DEF",
        "display": "CoolProp DEF",
        "description": (
            "CoolProp's factory reference state is reset before generation and is not changed "
            "while rows are evaluated."
        ),
        "user_selectable": False,
    }
    assert payload["units_by_axis"] == {
        "temperature": ["K", "degC"],
        "pressure": ["Pa", "hPa", "kPa", "MPa", "bar", "atm"],
        "vapor_mass_fraction": ["1"],
    }
    assert {item["kind"] for item in payload["samplers"]} == {
        "explicit",
        "linspace",
        "stepspace",
        "geomspace",
        "logspace",
    }
    assert payload["fluids"]
    properties = payload["properties"]
    assert isinstance(properties, list)
    assert "dynamic_viscosity" not in {
        property_metadata["name"]
        for property_metadata in properties
        if isinstance(property_metadata, dict)
    }
    catalog = {item["name"]: item for item in payload["property_catalog"] if isinstance(item, dict)}
    assert catalog["mass_density"]["supported_models"] == ["heos", "pr", "srk"]
    assert catalog["dynamic_viscosity"]["supported_models"] == ["heos"]
    assert payload["reference_dependent_fields"] == [
        "specific_enthalpy",
        "specific_entropy",
        "specific_internal_energy",
    ]
    assert payload["visualization"]["plot_kinds"] == [
        "property_curves",
        "property_heatmap",
        "xy",
        "pv",
        "ts",
    ]
    assert payload["visualization"]["kind_contracts"]["xy"] == {
        "required": ["x", "y"],
        "applicable": [
            "x",
            "y",
            "group_by",
            "filters",
            "series",
            "display_units",
            "fluids",
            "x_scale",
            "y_scale",
            "format",
        ],
    }
    assert payload["visualization"]["categorical_values"]["saturation_endpoint"] == [
        "saturated_liquid",
        "saturated_vapor",
    ]
    assert "gas" in payload["visualization"]["categorical_values"]["phase"]


def test_worker_loads_and_fully_validates_dataset_config(
    property_config_path: Path,
) -> None:
    request_id, line = _request(
        "load_dataset_config",
        {"config_path": str(property_config_path)},
    )
    stdout = io.StringIO()

    assert main(io.StringIO(line + "\n"), stdout, io.StringIO()) == 0

    events = _events(stdout)
    assert [event["type"] for event in events] == ["accepted", "phase", "result"]
    assert all(event["request_id"] == request_id for event in events)
    payload = events[-1]["payload"]
    assert isinstance(payload, dict)
    assert payload["config"]["fluids"] == ["Propane"]
    assert payload["validation"]["projected_rows"] == 2
    assert payload["requested_fluid_canonical_names"] == ["n-Propane"]
    assert payload["source_sha256"] == hashlib.sha256(property_config_path.read_bytes()).hexdigest()


def test_worker_validates_exact_dataset_yaml_text(property_config_path: Path) -> None:
    text = property_config_path.read_text(encoding="utf-8")
    _, line = _request(
        "validate_dataset_config",
        {"yaml_text": text, "source_name": "draft.yaml"},
    )
    stdout = io.StringIO()

    assert main(io.StringIO(line + "\n"), stdout, io.StringIO()) == 0

    payload = _events(stdout)[-1]["payload"]
    assert isinstance(payload, dict)
    assert payload["source_name"] == "draft.yaml"
    assert payload["source_sha256"] == hashlib.sha256(text.encode()).hexdigest()


def test_worker_reports_structured_dataset_config_issues(property_config_path: Path) -> None:
    text = property_config_path.read_text(encoding="utf-8").replace(
        "properties:\n  - specific_enthalpy\n  - mass_density",
        "properties: []",
    )
    _, line = _request(
        "validate_dataset_config",
        {"yaml_text": text, "source_name": "invalid.yaml"},
    )
    stdout = io.StringIO()

    assert main(io.StringIO(line + "\n"), stdout, io.StringIO()) == 1

    event = _events(stdout)[-1]
    assert event["type"] == "error"
    payload = event["payload"]
    assert isinstance(payload, dict)
    assert payload["category"] == "config"
    assert payload["code"] == "invalid_config"
    assert len(payload["details"]["issues"]) == 1
    issue = payload["details"]["issues"][0]
    assert issue["path"] == "properties"
    assert issue["code"] == "too_short"
    assert "at least 1" in issue["message"]


def test_worker_generates_structured_progress_and_result(
    property_config_path: Path,
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "runs"
    request_id, line = _request(
        "generate_dataset",
        {
            "config_path": str(property_config_path),
            "expected_config_sha256": hashlib.sha256(property_config_path.read_bytes()).hexdigest(),
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


def test_worker_rejects_changed_config_before_pipeline_import(
    property_config_path: Path,
) -> None:
    request_id = str(uuid4())
    request = json.dumps(
        {
            "protocol_version": PROTOCOL_VERSION,
            "request_id": request_id,
            "type": "generate_dataset",
            "payload": {
                "config_path": str(property_config_path),
                "expected_config_sha256": "0" * 64,
                "output_root": str(property_config_path.parent / "runs"),
            },
        }
    )
    code = """
import io
import json
import sys
from carnopy.app.worker import main
request = sys.argv[1]
stdout = io.StringIO()
result = main(io.StringIO(request + "\\n"), stdout, io.StringIO())
event = json.loads(stdout.getvalue().splitlines()[-1])
assert result == 1
assert event["payload"]["category"] == "config"
assert event["payload"]["code"] == "source_changed"
assert "carnopy.pipeline" not in sys.modules
assert "CoolProp" not in sys.modules
"""

    completed = subprocess.run(
        [sys.executable, "-c", code, request],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_worker_inspection_and_preview_do_not_import_coolprop(tmp_path: Path) -> None:
    dataset = tmp_path / "dataset.parquet"
    import pandas as pd

    pd.DataFrame(
        {
            "run_id": ["run"],
            "case_id": [0],
            "mode": ["property_table"],
            "fluid": ["Propane"],
            "backend": ["coolprop"],
            "backend_version": ["test"],
            "phase": ["gas"],
            "valid": [True],
            "temperature_K": [300.0],
            "pressure_Pa": [100000.0],
        }
    ).to_parquet(dataset, index=False)
    code = r"""
import io
import json
import sys
from carnopy.app.worker import main

source = sys.argv[1]
request_id = "00000000-0000-0000-0000-000000000001"
inspect_request = json.dumps({
    "protocol_version": 1,
    "request_id": request_id,
    "type": "inspect_source",
    "payload": {"source_path": source},
})
stdout = io.StringIO()
assert main(io.StringIO(inspect_request + "\n"), stdout, io.StringIO()) == 0
inspection = json.loads(stdout.getvalue().splitlines()[-1])["payload"]
preview_request = json.dumps({
    "protocol_version": 1,
    "request_id": "00000000-0000-0000-0000-000000000002",
    "type": "preview_table",
    "payload": {
        "source_path": source,
        "table_id": "dataset",
        "inspection_revision": inspection["revision"],
        "offset": 0,
        "limit": 1,
    },
})
stdout = io.StringIO()
assert main(io.StringIO(preview_request + "\n"), stdout, io.StringIO()) == 0
assert json.loads(stdout.getvalue().splitlines()[-1])["payload"]["block_count"] == 1
assert "CoolProp" not in sys.modules
assert "carnopy.backends.coolprop" not in sys.modules
assert "carnopy.app.capabilities" not in sys.modules
"""

    completed = subprocess.run(
        [sys.executable, "-c", code, str(dataset)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_worker_rejects_preview_over_500_rows_before_source_resolution() -> None:
    _, line = _request(
        "preview_table",
        {
            "source_path": "missing",
            "table_id": "dataset",
            "inspection_revision": "a" * 64,
            "offset": 0,
            "limit": 501,
        },
    )
    stdout = io.StringIO()

    assert main(io.StringIO(line + "\n"), stdout, io.StringIO()) == 2

    payload = _events(stdout)[-1]["payload"]
    assert isinstance(payload, dict)
    assert payload["code"] == "invalid_payload"


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
