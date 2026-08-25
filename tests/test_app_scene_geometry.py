from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import pandas as pd
import pytest

from carnopy.api import generate_dataset, prepare_dataset
from carnopy.app.scene_contracts import (
    CategoricalSetFilter,
    NumericRangeFilter,
    SceneContractError,
    SceneProfile,
    SceneRequest,
)
from carnopy.app.scene_geometry import project_scene_points
from carnopy.app.scene_profiles import profile_scene
from carnopy.app.source_inspection import inspect_for_app


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_projection_run(tmp_path: Path) -> Path:
    config = tmp_path / "projection.yaml"
    config.write_text(
        """schema_version: 2
document_type: dataset
backend:
  name: coolprop
  model: heos
mode: property_table
fluids: [Propane]
grid:
  temperature: {kind: explicit, values: [300.0, 310.0], unit: K}
  pressure: {kind: explicit, values: [1.0, 2.0, 3.0], unit: bar}
properties: [specific_enthalpy, mass_density]
""",
        encoding="utf-8",
    )
    run = generate_dataset(config, output_root=tmp_path / "runs")
    dataset = run.output_directory / "dataset.parquet"
    frame = pd.read_parquet(dataset)
    assert len(frame) == 6
    frame["phase"] = ["gas", "Gas", "gas", "gas", "gas", "gas"]
    frame.loc[2, "valid"] = False
    frame.loc[2, "failure_layer"] = "property"
    frame.loc[2, "failure_code"] = "backend_error"
    frame.loc[2, "failure_message"] = "controlled invalid row"
    frame.loc[2, "failure_property"] = "specific_enthalpy"
    frame.loc[2, "backend_error_type"] = "ValueError"
    frame.loc[2, "backend_error_message"] = "controlled invalid row"
    frame.loc[3, "specific_enthalpy_J_kg"] = float("nan")
    frame.loc[4, "mass_density_kg_m3"] = float("inf")
    frame.to_parquet(dataset, index=False)

    metadata_path = run.output_directory / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["run_status"] = "incomplete"
    metadata["valid_row_count"] = 5
    metadata["invalid_row_count"] = 1
    metadata["artifact_hashes"]["dataset.parquet"] = _sha256(dataset)
    metadata_path.write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return run.output_directory


def _projection_profile(source: Path) -> SceneProfile:
    inspected = inspect_for_app(source)
    assert len(inspected.scene_bindings) == 1
    return profile_scene(inspected.scene_bindings[0])


def _projection_request(profile: SceneProfile) -> SceneRequest:
    return SceneRequest(
        binding=profile.binding,
        x_field="temperature",
        y_field="pressure",
        z_field="specific_enthalpy",
        scalar_field="mass_density",
        filters=(
            CategoricalSetFilter(field_id="phase", values=("gas",)),
            NumericRangeFilter(
                field_id="temperature",
                minimum=300.0,
                maximum=310.0,
            ),
        ),
    )


def test_point_projection_applies_exact_filters_and_accounts_for_every_row(
    tmp_path: Path,
) -> None:
    source = _write_projection_run(tmp_path)
    profile = _projection_profile(source)
    request = _projection_request(profile)

    projection = project_scene_points(profile, request)

    assert projection.stable_id_field == "case_id"
    assert projection.retained_row_count == 2
    assert projection.excluded_row_count == 4
    assert [point.row_position for point in projection.points] == [0, 5]
    assert [point.stable_id for point in projection.points] == [0, 5]
    assert projection.points[0].coordinates[:2] == (300.0, 100_000.0)
    assert projection.points[1].coordinates[:2] == (310.0, 300_000.0)
    assert all(math.isfinite(value) for point in projection.points for value in point.coordinates)
    assert all(
        point.scalar is not None and math.isfinite(point.scalar) for point in projection.points
    )
    assert {(gap.code, gap.field_id): gap.count for gap in projection.exclusions} == {
        ("filtered", "phase"): 1,
        ("missing_selected_value", "specific_enthalpy"): 1,
        ("nonfinite_selected_value", "mass_density"): 1,
        ("source_invalid", None): 1,
    }

    reused_scalar_request = SceneRequest(
        binding=profile.binding,
        x_field=request.x_field,
        y_field=request.y_field,
        z_field=request.z_field,
        scalar_field=request.z_field,
        filters=request.filters,
    )
    reused_scalar = project_scene_points(profile, reused_scalar_request)
    assert [point.row_position for point in reused_scalar.points] == [0, 4, 5]
    assert all(point.scalar == point.coordinates[2] for point in reused_scalar.points)

    empty_request = SceneRequest(
        binding=profile.binding,
        x_field=request.x_field,
        y_field=request.y_field,
        z_field=request.z_field,
        filters=(
            CategoricalSetFilter(field_id="phase", values=("gas",)),
            NumericRangeFilter(
                field_id="pressure",
                minimum=999_999.0,
                maximum=999_999.0,
            ),
        ),
    )
    with pytest.raises(SceneContractError) as empty:
        project_scene_points(profile, empty_request)
    assert empty.value.code == "scene_no_retained_points"
    assert empty.value.details["source_row_count"] == 6


def test_point_projection_rejects_changed_source_and_profile(tmp_path: Path) -> None:
    source = _write_projection_run(tmp_path)
    profile = _projection_profile(source)
    request = _projection_request(profile)
    payload = profile.model_dump(mode="json")
    payload["fields"][0]["label"] = "Changed label"
    changed_profile = SceneProfile.model_validate(payload)

    with pytest.raises(SceneContractError) as invalid_profile:
        project_scene_points(changed_profile, request)
    assert invalid_profile.value.code == "invalid_scene_profile"

    (source / "dataset.parquet").write_bytes(b"changed")
    with pytest.raises(SceneContractError) as stale:
        project_scene_points(profile, request)
    assert stale.value.code == "scene_source_changed"


def test_prepared_points_preserve_prepared_row_identity(
    property_config_path: Path,
    tmp_path: Path,
) -> None:
    run = generate_dataset(property_config_path, output_root=tmp_path / "runs")
    config = tmp_path / "preparation.yaml"
    config.write_text(
        """schema_version: 1
document_type: preparation
features:
  numeric: [temperature, pressure, mass_density]
  derived: [specific_volume]
categorical_features: []
targets: [specific_enthalpy]
outputs:
  formats: [parquet]
""",
        encoding="utf-8",
    )
    prepared = prepare_dataset(
        run.output_directory,
        config=config,
        output_root=tmp_path / "prepared",
    )
    inspected = inspect_for_app(prepared.output_directory)
    binding = next(
        binding for binding in inspected.scene_bindings if binding.selected_table_id == "table"
    )
    profile = profile_scene(binding)
    request = SceneRequest(
        binding=binding,
        x_field="temperature",
        y_field="pressure",
        z_field="mass_density",
        scalar_field="specific_enthalpy",
    )

    projection = project_scene_points(profile, request)

    assert projection.stable_id_field == "prepared_row_id"
    assert projection.retained_row_count == profile.source_row_count == 2
    assert projection.exclusions == ()
    assert [point.row_position for point in projection.points] == [0, 1]
    assert [point.stable_id for point in projection.points] == [0, 1]
