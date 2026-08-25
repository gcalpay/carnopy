from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pandas as pd

from carnopy.api import generate_dataset, prepare_dataset
from carnopy.app.scene_contracts import (
    CategoricalSetFilter,
    NumericRangeFilter,
    SceneProfile,
    SceneRequest,
    SceneTopologyAxis,
    SceneTopologyEvidence,
)
from carnopy.app.scene_profiles import _load_scene_profile_source, profile_scene
from carnopy.app.scene_topology import _analyze_block_topology, analyze_scene_topology
from carnopy.app.source_inspection import inspect_for_app


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _generate_grid(
    tmp_path: Path,
    *,
    name: str,
    temperatures: tuple[float, ...] = (320.0, 300.0),
    pressures_bar: tuple[float, ...] = (1.0, 2.0, 3.0, 4.0),
) -> Path:
    config = tmp_path / f"{name}.yaml"
    config.write_text(
        f"""schema_version: 2
document_type: dataset
backend:
  name: coolprop
  model: heos
mode: property_table
fluids: [Propane]
grid:
  temperature: {{kind: explicit, values: {list(temperatures)}, unit: K}}
  pressure: {{kind: explicit, values: {list(pressures_bar)}, unit: bar}}
properties: [specific_enthalpy, mass_density]
outputs:
  dataset_formats: [parquet]
""",
        encoding="utf-8",
    )
    return generate_dataset(config, output_root=tmp_path / f"{name}-runs").output_directory


def _rewrite_dataset(run: Path, frame: pd.DataFrame) -> None:
    dataset = run / "dataset.parquet"
    frame.to_parquet(dataset, index=False)
    metadata_path = run / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    valid_count = int(frame["valid"].sum())
    metadata["row_count"] = len(frame)
    metadata["valid_row_count"] = valid_count
    metadata["invalid_row_count"] = len(frame) - valid_count
    metadata["run_status"] = "completed" if valid_count == len(frame) else "incomplete"
    metadata["artifact_hashes"]["dataset.parquet"] = _sha256(dataset)
    metadata_path.write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _profile(run: Path) -> SceneProfile:
    inspected = inspect_for_app(run)
    assert len(inspected.scene_bindings) == 1
    return profile_scene(inspected.scene_bindings[0])


def _request(profile: SceneProfile, *filters: NumericRangeFilter) -> SceneRequest:
    return SceneRequest(
        binding=profile.binding,
        x_field="temperature",
        y_field="pressure",
        z_field="specific_enthalpy",
        scalar_field="mass_density",
        filters=filters,
    )


def test_topology_preserves_order_and_exact_gaps_without_primitives(tmp_path: Path) -> None:
    run = _generate_grid(tmp_path, name="gaps")
    frame = pd.read_parquet(run / "dataset.parquet")
    assert len(frame) == 8
    frame["phase"] = "gas"
    frame["mass_density_kg_m3"] = [1.0, 100.0, 100.0, 2.0] * 2
    frame.loc[1, "valid"] = False
    frame.loc[1, "failure_layer"] = "property"
    frame.loc[1, "failure_code"] = "backend_error"
    frame.loc[1, "failure_message"] = "controlled invalid row"
    frame.loc[1, "failure_property"] = "mass_density"
    frame.loc[1, "backend_error_type"] = "ValueError"
    frame.loc[1, "backend_error_message"] = "controlled invalid row"
    _rewrite_dataset(run, frame)
    profile = _profile(run)
    request = _request(
        profile,
        NumericRangeFilter(field_id="mass_density", maximum=2.0),
    )

    partition = analyze_scene_topology(profile, request)

    assert len(partition.blocks) == 1
    assert partition.orphan_exclusions == ()
    block = partition.blocks[0]
    assert block.context.phase == "gas"
    assert block.point_indices == (0, 1, 2, 3)
    assert [point.row_position for point in partition.projection.points] == [0, 3, 4, 7]
    assert block.topology.status == "exact"
    assert block.topology.dimension == 2
    assert tuple(axis.field_id for axis in block.topology.axes) == (
        "temperature",
        "pressure",
    )
    assert block.topology.axes[0].levels == (320.0, 300.0)
    assert block.topology.axes[1].levels == (100_000.0, 200_000.0, 300_000.0, 400_000.0)
    assert [location.level_indices for location in block.topology.locations] == [
        (0, 0),
        (0, 3),
        (1, 0),
        (1, 3),
    ]
    assert [gap.exclusion.row_position for gap in block.topology.gap_locations] == [1, 2, 5, 6]
    assert [gap.level_indices for gap in block.topology.gap_locations] == [
        (0, 1),
        (0, 2),
        (1, 1),
        (1, 2),
    ]
    assert [
        (missing.field_id, missing.level_indices)
        for missing in block.topology.missing_intermediate_levels
    ] == [("pressure", (1, 2))]
    assert not hasattr(partition, "edges")
    assert not hasattr(partition, "quads")

    zero_request = _request(
        profile,
        NumericRangeFilter(field_id="temperature", minimum=320.0, maximum=320.0),
        NumericRangeFilter(field_id="pressure", minimum=100_000.0, maximum=100_000.0),
    )
    zero = analyze_scene_topology(profile, zero_request)
    assert len(zero.blocks) == 1
    assert zero.blocks[0].topology.status == "zero_dimensional"
    assert zero.blocks[0].topology.dimension == 0

    loaded = _load_scene_profile_source(profile.binding, checkpoint=None)
    enthalpy = next(field for field in loaded.fields if field.field_id == "specific_enthalpy")
    third_axis = SceneTopologyAxis(
        field_id=enthalpy.field_id,
        source_column=enthalpy.column,
        unit=enthalpy.unit or "J/kg",
        levels=tuple(float(value) for value in enthalpy.values.tolist()),
    )
    synthetic = replace(
        loaded,
        topology=SceneTopologyEvidence(
            status="exact",
            axes=(*loaded.topology.axes, third_axis),
            context_fields=loaded.topology.context_fields,
        ),
    )
    higher = _analyze_block_topology(
        synthetic,
        partition.projection,
        block.context,
        block.point_indices,
        block.exclusions,
    )
    assert higher.status == "unsupported_dimension"
    assert higher.dimension == 3
    assert higher.reason_code == "unsupported_topology_dimension"


def test_topology_partitions_contexts_and_preserves_duplicate_points(tmp_path: Path) -> None:
    run = _generate_grid(
        tmp_path,
        name="contexts",
        pressures_bar=(1.0, 2.5),
    )
    frame = pd.read_parquet(run / "dataset.parquet")
    assert len(frame) == 4
    frame["phase"] = ["gas", "gas", "liquid", "liquid"]
    duplicate = frame.iloc[[0]].copy()
    duplicate["case_id"] = 4
    missing_context = frame.iloc[[1]].copy()
    missing_context["case_id"] = 5
    missing_context["phase"] = None
    frame = pd.concat([frame, duplicate, missing_context], ignore_index=True)
    _rewrite_dataset(run, frame)
    profile = _profile(run)

    partition = analyze_scene_topology(profile, _request(profile))

    assert [block.context.phase for block in partition.blocks] == [None, "gas", "liquid"]
    missing, gas, liquid = partition.blocks
    assert missing.topology.status == "missing_context"
    assert missing.topology.missing_context_fields == ("phase",)
    assert missing.topology.reason_code == "missing_context"
    assert gas.topology.dimension == 1
    assert gas.topology.status == "duplicate_locations"
    assert [location.level_indices for location in gas.topology.duplicate_locations] == [(0, 0)]
    assert gas.topology.duplicate_locations[0].point_indices == (0, 4)
    assert [partition.projection.points[index].stable_id for index in (0, 4)] == [0, 4]
    assert liquid.topology.status == "exact"
    assert liquid.topology.dimension == 1
    assert gas.topology.axes[0].levels == liquid.topology.axes[0].levels == (320.0, 300.0)

    gas_only = analyze_scene_topology(
        profile,
        SceneRequest(
            binding=profile.binding,
            x_field="temperature",
            y_field="pressure",
            z_field="specific_enthalpy",
            filters=(CategoricalSetFilter(field_id="phase", values=("gas",)),),
        ),
    )
    assert [block.context.phase for block in gas_only.blocks] == ["gas"]
    assert [group.context.phase for group in gas_only.orphan_exclusions] == [None, "liquid"]
    assert [
        row.row_position for group in gas_only.orphan_exclusions for row in group.exclusions
    ] == [5, 2, 3]


def test_prepared_scenario_blocks_remain_explicitly_topology_unavailable(
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
scenarios:
  - name: baseline
    kind: unsplit
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
        value
        for value in inspected.scene_bindings
        if value.selected_table_id == "scenario.baseline.all"
    )
    profile = profile_scene(binding)
    request = SceneRequest(
        binding=binding,
        x_field="temperature",
        y_field="pressure",
        z_field="mass_density",
        scalar_field="specific_enthalpy",
    )

    partition = analyze_scene_topology(profile, request)

    assert partition.blocks
    assert all(block.context.scenario == "baseline" for block in partition.blocks)
    assert all(block.context.partition == "all" for block in partition.blocks)
    assert all(block.topology.status == "unavailable" for block in partition.blocks)
    assert all(block.topology.dimension is None for block in partition.blocks)
    assert all(
        block.topology.reason_code == "source_sampling_levels_not_recorded"
        for block in partition.blocks
    )
