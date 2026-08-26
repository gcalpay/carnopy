from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd
import pytest

from carnopy._execution import ExecutionCancelled
from carnopy.app.protocol import EventType
from carnopy.app.scene_build import (
    BuildScenePayload,
    adopt_scene_build,
    execute_scene_build,
)
from carnopy.app.scene_bundle import verify_scene_bundle
from carnopy.app.scene_contracts import SceneContractError, SceneProfile, SceneRequest
from carnopy.app.scene_integrity import (
    SCENE_BINARY_NAME,
    SCENE_MANIFEST_NAME,
    SceneBundleError,
)
from carnopy.app.scene_leases import (
    SceneLease,
    SceneLeasePayload,
    acquire_scene_session,
    create_scene_lease,
)
from carnopy.app.scene_profiles import profile_scene
from carnopy.app.source_inspection import inspect_for_app
from carnopy.app.worker import main
from carnopy.app.workspace import initialize_workspace


@dataclass(frozen=True)
class SceneBuildInputs:
    source: Path
    profile: SceneProfile
    request: SceneRequest


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


@pytest.fixture(scope="module")
def scene_build_inputs(tmp_path_factory: pytest.TempPathFactory) -> SceneBuildInputs:
    source = tmp_path_factory.mktemp("scene-build-source")
    dataset = source / "dataset.parquet"
    frame = pd.DataFrame(
        {
            "run_id": ["scene-build-run"] * 4,
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
    _write_json(source / "report.json", {"report_schema_version": 1, "run_id": "scene-build-run"})
    _write_json(
        source / "metadata.json",
        {
            "metadata_schema_version": 1,
            "dataset_schema_version": 2,
            "run_id": "scene-build-run",
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
    binding = inspect_for_app(source).scene_bindings[0]
    profile = profile_scene(binding)
    request = SceneRequest(
        binding=profile.binding,
        x_field="temperature",
        y_field="pressure",
        z_field="specific_enthalpy",
        scalar_field="specific_enthalpy",
    )
    return SceneBuildInputs(source=source, profile=profile, request=request)


def _build_payload(
    workspace: Path,
    lease: SceneLease,
    inputs: SceneBuildInputs,
) -> BuildScenePayload:
    return BuildScenePayload(
        workspace_path=workspace,
        lease=SceneLeasePayload.model_validate(lease.worker_payload(), strict=True),
        profile=inputs.profile,
        request=inputs.request,
    )


def _execute(payload: BuildScenePayload) -> dict[str, object]:
    return execute_scene_build(
        payload,
        emit=lambda _event_type, _payload: None,
        checkpoint=lambda: None,
    )


def test_build_scene_worker_publishes_then_parent_independently_adopts(
    scene_build_inputs: SceneBuildInputs,
    tmp_path: Path,
) -> None:
    workspace = initialize_workspace(tmp_path / "workspace")
    session = acquire_scene_session(workspace.root)
    try:
        lease = create_scene_lease(session)
        payload = _build_payload(workspace.root, lease, scene_build_inputs)
        worker_request = json.dumps(
            {
                "protocol_version": 1,
                "request_id": str(uuid4()),
                "type": "build_scene",
                "payload": payload.model_dump(mode="json"),
            }
        )
        stdout = io.StringIO()

        assert main(io.StringIO(worker_request + "\n"), stdout, io.StringIO()) == 0

        events = [json.loads(line) for line in stdout.getvalue().splitlines()]
        phases = [event["payload"] for event in events if event["type"] == "phase"]
        progress = [event["payload"] for event in events if event["type"] == "progress"]
        assert [phase["name"] for phase in phases] == [
            "scene_geometry",
            "scene_encoding",
            "scene_source_revalidation",
            "scene_publication",
        ]
        assert phases[-1] == {
            "name": "scene_publication",
            "cancellable": False,
            "termination_protected": True,
        }
        assert progress == [{"completed": completed, "total": 4} for completed in range(5)]
        assert events[0]["type"] == "accepted"
        assert events[-1]["type"] == "result"

        verified = adopt_scene_build(
            lease,
            scene_build_inputs.profile,
            scene_build_inputs.request,
            events[-1]["payload"],
        )

        assert verified.manifest.request_id == scene_build_inputs.request.request_id
        assert verified.manifest.scientific_payload.request == scene_build_inputs.request
    finally:
        session.close()


def test_build_scene_cancels_before_publication_without_scene_files(
    scene_build_inputs: SceneBuildInputs,
    tmp_path: Path,
) -> None:
    workspace = initialize_workspace(tmp_path / "workspace")
    session = acquire_scene_session(workspace.root)
    cancel_requested = False

    def emit(event_type: EventType, payload: dict[str, Any]) -> None:
        nonlocal cancel_requested
        if event_type == "phase" and payload.get("name") == "scene_encoding":
            cancel_requested = True

    def checkpoint() -> None:
        if cancel_requested:
            raise ExecutionCancelled("injected scene cancellation")

    try:
        lease = create_scene_lease(session)
        with pytest.raises(ExecutionCancelled, match="injected scene cancellation"):
            execute_scene_build(
                _build_payload(workspace.root, lease, scene_build_inputs),
                emit=emit,
                checkpoint=checkpoint,
            )

        assert not (lease.path / SCENE_BINARY_NAME).exists()
        assert not (lease.path / SCENE_MANIFEST_NAME).exists()
    finally:
        session.close()


def test_parent_rejects_result_or_binary_tampering_and_preserves_prior_scene(
    scene_build_inputs: SceneBuildInputs,
    tmp_path: Path,
) -> None:
    workspace = initialize_workspace(tmp_path / "workspace")
    session = acquire_scene_session(workspace.root)
    try:
        previous_lease = create_scene_lease(session)
        previous_result = _execute(
            _build_payload(workspace.root, previous_lease, scene_build_inputs)
        )
        previous = adopt_scene_build(
            previous_lease,
            scene_build_inputs.profile,
            scene_build_inputs.request,
            previous_result,
        )
        previous_binary = previous.binary_path.read_bytes()

        candidate_lease = create_scene_lease(session)
        candidate_result = _execute(
            _build_payload(workspace.root, candidate_lease, scene_build_inputs)
        )
        mismatched_result = dict(candidate_result)
        mismatched_result["content_id"] = "scene-content-" + "0" * 64
        with pytest.raises(SceneBundleError, match="result disagrees"):
            adopt_scene_build(
                candidate_lease,
                scene_build_inputs.profile,
                scene_build_inputs.request,
                mismatched_result,
            )

        candidate_binary = candidate_lease.path / SCENE_BINARY_NAME
        tampered = bytearray(candidate_binary.read_bytes())
        tampered[-1] ^= 1
        candidate_binary.write_bytes(tampered)
        with pytest.raises(SceneBundleError, match="hash"):
            adopt_scene_build(
                candidate_lease,
                scene_build_inputs.profile,
                scene_build_inputs.request,
                candidate_result,
            )

        assert verify_scene_bundle(previous_lease).manifest == previous.manifest
        assert previous.binary_path.read_bytes() == previous_binary
    finally:
        session.close()


def test_source_change_during_protected_publication_prevents_build_result(
    scene_build_inputs: SceneBuildInputs,
    tmp_path: Path,
) -> None:
    workspace = initialize_workspace(tmp_path / "workspace")
    session = acquire_scene_session(workspace.root)
    dataset = scene_build_inputs.source / "dataset.parquet"
    original = dataset.read_bytes()
    original_stat = dataset.stat()

    def mutate_at_publication(event_type: EventType, payload: dict[str, Any]) -> None:
        if event_type == "phase" and payload.get("name") == "scene_publication":
            dataset.write_bytes(b"changed during protected publication")

    try:
        lease = create_scene_lease(session)
        with pytest.raises(SceneContractError) as error:
            execute_scene_build(
                _build_payload(workspace.root, lease, scene_build_inputs),
                emit=mutate_at_publication,
                checkpoint=lambda: None,
            )

        assert error.value.code == "scene_source_changed"
        assert (
            verify_scene_bundle(lease).manifest.request_id == scene_build_inputs.request.request_id
        )
    finally:
        dataset.write_bytes(original)
        os.utime(dataset, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
        session.close()


def test_scene_build_parent_import_excludes_heavy_scientific_and_rendering_modules() -> None:
    script = """
import sys
from carnopy.app.scene_build import adopt_scene_build

blocked = ("CoolProp", "numpy", "pandas", "pyarrow", "matplotlib", "vtk")
loaded = sorted(name for name in blocked if name in sys.modules)
raise SystemExit("heavy imports: " + ", ".join(loaded) if loaded else 0)
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
