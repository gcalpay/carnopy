from __future__ import annotations

import hashlib
import io
import json
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pandas as pd
import pytest

from carnopy.api import generate_dataset, prepare_dataset
from carnopy.app.protocol import PROTOCOL_VERSION
from carnopy.app.scene_contracts import SceneContractError, SceneSourceBinding
from carnopy.app.scene_pick_contracts import ResolveScenePickPayload, ScenePickResult
from carnopy.app.scene_picks import resolve_scene_pick
from carnopy.app.source_inspection import inspect_for_app
from carnopy.app.worker import main


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _dataset_frame(*, model: str = "heos", run_id: str = "pick-run") -> pd.DataFrame:
    return pd.DataFrame(
        {
            "run_id": [run_id] * 4,
            "case_id": [0, 1, 2, 3],
            "mode": ["property_table"] * 4,
            "fluid": ["Propane"] * 4,
            "backend": ["coolprop"] * 4,
            "backend_model": [model] * 4,
            "backend_version": ["test"] * 4,
            "phase": ["gas", "gas", "liquid", "liquid"],
            "backend_phase": ["gas", "gas", "liquid", "liquid"],
            "temperature_K": [320.0, 320.0, 300.0, 300.0],
            "pressure_Pa": [100_000.0, 250_000.0, 100_000.0, 250_000.0],
            "specific_enthalpy_J_kg": [420_000.0, 430_000.0, 240_000.0, 250_000.0],
            "valid": [True, True, True, False],
            "failure_layer": [None, None, None, "property"],
            "failure_code": [None, None, None, "backend_error"],
            "failure_message": [None, None, None, "controlled failure"],
            "failure_property": [None, None, None, "specific_enthalpy"],
            "backend_error_type": [None, None, None, "ValueError"],
            "backend_error_message": [None, None, None, "controlled failure"],
        }
    )


def _write_dataset_run(
    root: Path,
    *,
    model: str = "heos",
    run_id: str = "pick-run",
    frame: pd.DataFrame | None = None,
) -> Path:
    root.mkdir(parents=True)
    selected = _dataset_frame(model=model, run_id=run_id) if frame is None else frame
    dataset = root / "dataset.parquet"
    selected.to_parquet(dataset, index=False)
    _write_json(root / "report.json", {"report_schema_version": 1, "run_id": run_id})
    _write_json(
        root / "metadata.json",
        {
            "metadata_schema_version": 1,
            "dataset_schema_version": 2,
            "run_id": run_id,
            "run_status": "incomplete" if not selected["valid"].all() else "completed",
            "mode": "property_table",
            "backend": "coolprop",
            "backend_model": model,
            "row_count": len(selected),
            "valid_row_count": int(selected["valid"].sum()),
            "invalid_row_count": int((~selected["valid"]).sum()),
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
                "report.json": _sha256(root / "report.json"),
            },
        },
    )
    return root


def _write_sweep(root: Path) -> Path:
    root.mkdir()
    _write_json(root / "sweep.normalized.json", {})
    _write_json(root / "report.json", {"sweep_report_schema_version": 1})
    child = _write_dataset_run(
        root / "models" / "heos" / "child",
        model="heos",
        run_id="pick-child",
    )
    comparison = root / "comparison"
    comparison.mkdir()
    values = comparison / "values.parquet"
    deltas = comparison / "deltas.parquet"
    pd.DataFrame({"case_id": [0], "value": [1.0]}).to_parquet(values, index=False)
    pd.DataFrame({"case_id": [0], "delta": [0.0]}).to_parquet(deltas, index=False)
    _write_json(
        root / "metadata.json",
        {
            "sweep_metadata_schema_version": 1,
            "sweep_id": "pick-sweep",
            "sweep_run_id": "pick-sweep-run",
            "sweep_status": "completed",
            "mode": "property_table",
            "backend": "coolprop",
            "models": ["heos"],
            "reference_model": "heos",
            "child_runs": [
                {
                    "backend_model": "heos",
                    "run_id": "pick-child",
                    "output_directory": str(child),
                }
            ],
            "artifact_hashes": {
                "comparison/values.parquet": _sha256(values),
                "comparison/deltas.parquet": _sha256(deltas),
                "sweep.normalized.json": _sha256(root / "sweep.normalized.json"),
                "report.json": _sha256(root / "report.json"),
            },
        },
    )
    return root


def _binding(source: Path) -> SceneSourceBinding:
    bindings = inspect_for_app(source).scene_bindings
    assert len(bindings) == 1
    return bindings[0]


def _payload(
    binding: SceneSourceBinding, row_position: int, stable_id: int
) -> ResolveScenePickPayload:
    return ResolveScenePickPayload(
        binding=binding,
        row_position=row_position,
        stable_id=stable_id,
    )


def _worker_request(payload: dict[str, object]) -> str:
    return json.dumps(
        {
            "protocol_version": PROTOCOL_VERSION,
            "request_id": str(uuid4()),
            "type": "resolve_scene_pick",
            "payload": payload,
        }
    )


def _events(stream: io.StringIO) -> list[dict[str, object]]:
    return [json.loads(line) for line in stream.getvalue().splitlines()]


def test_direct_pick_returns_every_exact_source_cell(tmp_path: Path) -> None:
    source = _write_dataset_run(tmp_path / "run")
    binding = _binding(source)

    result = resolve_scene_pick(_payload(binding, 1, 1))
    row = result.row()

    assert result.source_path == str(source.resolve())
    assert result.source_kind == "dataset"
    assert result.inspection_revision == binding.inspection_revision
    assert result.table_id == "dataset"
    assert result.table_sha256 == binding.selected_table().artifact.sha256
    assert result.row_position == 1
    assert result.stable_id_field == "case_id"
    assert result.stable_id == 1
    assert tuple(row) == tuple(_dataset_frame().columns)
    assert row["run_id"].model_dump() == {"kind": "text", "value": "pick-run"}
    assert row["case_id"].model_dump() == {"kind": "integer", "value": 1}
    assert row["temperature_K"].model_dump() == {"kind": "float", "value": 320.0}
    assert row["valid"].model_dump() == {"kind": "boolean", "value": True}
    assert row["failure_layer"].model_dump() == {"kind": "null", "value": None}


def test_sweep_child_pick_uses_selected_child_table_identity(tmp_path: Path) -> None:
    source = _write_sweep(tmp_path / "sweep")
    binding = _binding(source)

    result = resolve_scene_pick(_payload(binding, 2, 2))

    assert result.source_kind == "model_sweep"
    assert result.table_id == "model.heos.dataset"
    assert result.row()["run_id"].value == "pick-child"
    assert result.row()["case_id"].value == 2


def test_prepared_main_and_scenario_picks_return_exact_joined_evidence(
    property_config_path: Path,
    tmp_path: Path,
) -> None:
    run = generate_dataset(property_config_path, output_root=tmp_path / "runs")
    preparation_config = tmp_path / "preparation.yaml"
    preparation_config.write_text(
        """schema_version: 1
document_type: preparation
features:
  numeric: [temperature, pressure, mass_density]
  derived: [specific_volume]
categorical_features: []
targets: [specific_enthalpy]
scenarios:
  - name: baseline
    kind: unsplit
    transformations:
      - field: pressure
        methods: [log10]
outputs:
  formats: [parquet]
""",
        encoding="utf-8",
    )
    prepared = prepare_dataset(
        run.output_directory,
        config=preparation_config,
        output_root=tmp_path / "prepared",
    )
    bindings = {
        binding.selected_table_id: binding
        for binding in inspect_for_app(prepared.output_directory).scene_bindings
    }

    main_result = resolve_scene_pick(_payload(bindings["table"], 1, 1))
    main_context = main_result.prepared_context

    assert main_result.source_kind == "preparation"
    assert main_result.stable_id_field == "prepared_row_id"
    assert main_result.row()["prepared_row_id"].value == 1
    assert main_context is not None
    assert main_context.scenario is None
    assert main_context.partition is None
    assert main_context.provenance.row()["source_row_index"].value == 1
    assert main_context.provenance.row()["source_row_hash"].kind == "text"
    assert main_context.diagnostics.row()["source_valid"].value is True
    assert "source_failure_message" in main_context.diagnostics.row()
    assert (
        main_context.provenance.table_sha256
        == next(
            table for table in bindings["table"].tables if table.table_id == "provenance"
        ).artifact.sha256
    )

    scenario_binding = bindings["scenario.baseline.all"]
    stdout = io.StringIO()
    request = _worker_request(_payload(scenario_binding, 0, 0).model_dump(mode="json"))
    assert main(io.StringIO(request + "\n"), stdout, io.StringIO()) == 0
    scenario_result = ScenePickResult.model_validate(_events(stdout)[-1]["payload"])
    scenario_context = scenario_result.prepared_context

    assert scenario_result.table_id == "scenario.baseline.all"
    assert scenario_result.row()["pressure__log10"].kind == "float"
    assert scenario_context is not None
    assert scenario_context.scenario == "baseline"
    assert scenario_context.partition == "all"
    assert scenario_context.provenance.row()["prepared_row_id"].value == 0
    assert scenario_context.diagnostics.row()["prepared_row_id"].value == 0

    provenance_path = prepared.provenance_path
    provenance = pd.read_parquet(provenance_path)
    provenance.loc[1, "prepared_row_id"] = 0
    provenance.to_parquet(provenance_path, index=False)
    manifest = json.loads(prepared.manifest_path.read_text(encoding="utf-8"))
    manifest["artifact_hashes"]["data/provenance.parquet"] = _sha256(provenance_path)
    _write_json(prepared.manifest_path, manifest)
    corrupted_binding = next(
        binding
        for binding in inspect_for_app(prepared.output_directory).scene_bindings
        if binding.selected_table_id == "table"
    )

    with pytest.raises(SceneContractError, match="repeats a prepared_row_id") as caught:
        resolve_scene_pick(_payload(corrupted_binding, 0, 0))

    assert caught.value.code == "unsupported_scene_source"


@pytest.mark.parametrize(
    ("row_position", "stable_id", "message"),
    [
        (10, 1, "row position"),
        (1, 99, "case_id"),
        (1, 0, "row order"),
    ],
)
def test_pick_rejects_missing_reordered_or_substituted_identity(
    tmp_path: Path,
    row_position: int,
    stable_id: int,
    message: str,
) -> None:
    binding = _binding(_write_dataset_run(tmp_path / "run"))

    with pytest.raises(SceneContractError, match=message) as caught:
        resolve_scene_pick(_payload(binding, row_position, stable_id))

    assert caught.value.code == "scene_pick_stale"


def test_pick_rejects_duplicate_case_identity(tmp_path: Path) -> None:
    frame = _dataset_frame()
    frame["case_id"] = [0, 0, 2, 3]
    binding = _binding(_write_dataset_run(tmp_path / "run", frame=frame))

    with pytest.raises(SceneContractError, match="repeats a case_id") as caught:
        resolve_scene_pick(_payload(binding, 0, 0))

    assert caught.value.code == "scene_pick_stale"


@pytest.mark.parametrize("mutation", ["reorder", "substitute_case_id"])
def test_pick_revalidates_source_revision_before_returning_any_row(
    tmp_path: Path,
    mutation: str,
) -> None:
    source = _write_dataset_run(tmp_path / "run")
    binding = _binding(source)
    changed = _dataset_frame()
    if mutation == "reorder":
        changed = changed.iloc[[1, 0, 2, 3]].reset_index(drop=True)
    else:
        changed.loc[1, "case_id"] = 99
    changed.to_parquet(source / "dataset.parquet", index=False)

    with pytest.raises(SceneContractError, match="source changed") as caught:
        resolve_scene_pick(_payload(binding, 1, 1))

    assert caught.value.code == "scene_source_changed"


def test_pick_revalidates_source_after_reading_the_selected_row(tmp_path: Path) -> None:
    source = _write_dataset_run(tmp_path / "run")
    binding = _binding(source)
    checkpoint_count = 0

    def mutate_before_final_revalidation() -> None:
        nonlocal checkpoint_count
        checkpoint_count += 1
        if checkpoint_count == 3:
            changed = _dataset_frame()
            changed.loc[1, "case_id"] = 99
            changed.to_parquet(source / "dataset.parquet", index=False)

    with pytest.raises(SceneContractError, match="source changed") as caught:
        resolve_scene_pick(
            _payload(binding, 1, 1),
            checkpoint=mutate_before_final_revalidation,
        )

    assert checkpoint_count == 3
    assert caught.value.code == "scene_source_changed"


def test_pick_rejects_a_forged_source_kind(tmp_path: Path) -> None:
    binding = _binding(_write_dataset_run(tmp_path / "run"))
    prepared = SceneSourceBinding.model_validate(
        {**binding.model_dump(mode="json"), "source_kind": "preparation"}
    )

    with pytest.raises(SceneContractError, match="identity no longer matches") as caught:
        resolve_scene_pick(_payload(prepared, 0, 0))

    assert caught.value.code == "scene_source_changed"


def test_resolve_scene_pick_worker_returns_typed_row_and_rejects_bad_payload(
    tmp_path: Path,
) -> None:
    binding = _binding(_write_dataset_run(tmp_path / "run"))
    request = _worker_request(_payload(binding, 1, 1).model_dump(mode="json"))
    stdout = io.StringIO()

    assert main(io.StringIO(request + "\n"), stdout, io.StringIO()) == 0

    events = _events(stdout)
    assert [event["type"] for event in events] == ["accepted", "phase", "result"]
    assert events[1]["payload"] == {
        "name": "scene_pick_resolution",
        "cancellable": True,
    }
    result_payload = events[-1]["payload"]
    assert isinstance(result_payload, dict)
    assert ScenePickResult.model_validate(result_payload).stable_id == 1

    invalid = _payload(binding, 1, 1).model_dump(mode="json")
    invalid["row_position"] = True
    stdout = io.StringIO()
    assert main(io.StringIO(_worker_request(invalid) + "\n"), stdout, io.StringIO()) == 2
    error = _events(stdout)[-1]
    assert error["type"] == "error"
    assert isinstance(error["payload"], dict)
    assert error["payload"]["code"] == "invalid_payload"


def test_scene_pick_contract_import_remains_lightweight() -> None:
    code = r"""
import sys
from carnopy.app.scene_pick_contracts import ResolveScenePickPayload, ScenePickResult
assert ResolveScenePickPayload is not None and ScenePickResult is not None
blocked = {"CoolProp", "numpy", "pandas", "pyarrow", "matplotlib", "vtk"}
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
