from __future__ import annotations

import hashlib
import json
import math
from dataclasses import replace
from pathlib import Path

import pandas as pd
import pytest

from carnopy.api import generate_dataset
from carnopy.app.scene_cells import (
    SceneCellProjection,
    SceneQuad,
    build_scene_cells,
)
from carnopy.app.scene_contracts import SceneProfile, SceneRequest
from carnopy.app.scene_profiles import profile_scene
from carnopy.app.source_inspection import inspect_for_app


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _generate_cell_grid(
    tmp_path: Path,
    *,
    name: str,
    temperatures: tuple[float, ...] = (330.0, 300.0),
    pressures_bar: tuple[float, ...] = (8.0, 3.0, 1.0),
    properties: tuple[str, ...] = (
        "specific_enthalpy",
        "mass_density",
        "specific_entropy",
    ),
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
properties: [{", ".join(properties)}]
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


def _topology_request(profile: SceneProfile) -> SceneRequest:
    return SceneRequest(
        binding=profile.binding,
        x_field="temperature",
        y_field="pressure",
        z_field="specific_enthalpy",
        scalar_field="mass_density",
    )


def _property_request(profile: SceneProfile) -> SceneRequest:
    return SceneRequest(
        binding=profile.binding,
        x_field="specific_enthalpy",
        y_field="mass_density",
        z_field="specific_entropy",
    )


def test_two_dimensional_cells_preserve_exact_edges_and_quad_order(tmp_path: Path) -> None:
    run = _generate_cell_grid(tmp_path, name="ordered")
    frame = pd.read_parquet(run / "dataset.parquet")
    assert len(frame) == 6
    frame["phase"] = "gas"
    _rewrite_dataset(run, frame)
    profile = _profile(run)

    result = build_scene_cells(profile, _topology_request(profile))

    block = result.topology.blocks[0]
    assert block.topology.status == "exact"
    assert block.topology.dimension == 2
    assert block.topology.axes[0].levels == (330.0, 300.0)
    assert block.topology.axes[1].levels == (800_000.0, 300_000.0, 100_000.0)
    assert [(edge.point_indices, edge.topology_axis_index) for edge in result.edges] == [
        ((0, 3), 0),
        ((0, 1), 1),
        ((1, 4), 0),
        ((1, 2), 1),
        ((2, 5), 0),
        ((3, 4), 1),
        ((4, 5), 1),
    ]
    assert [(quad.point_indices, quad.topology_axis_indices) for quad in result.quads] == [
        ((0, 3, 4, 1), (0, 1)),
        ((1, 4, 5, 2), (0, 1)),
    ]
    assert result.edge_count == 7
    assert result.quad_count == 2
    assert result.omissions == ()
    assert not hasattr(result, "triangles")


def test_cell_projection_retains_exact_one_dimensional_edges(tmp_path: Path) -> None:
    run = _generate_cell_grid(
        tmp_path,
        name="one-dimensional",
        temperatures=(300.0,),
    )
    frame = pd.read_parquet(run / "dataset.parquet")
    assert len(frame) == 3
    frame["phase"] = "gas"
    _rewrite_dataset(run, frame)
    profile = _profile(run)

    result = build_scene_cells(profile, _topology_request(profile))

    assert result.topology.blocks[0].topology.dimension == 1
    assert [(edge.point_indices, edge.topology_axis_index) for edge in result.edges] == [
        ((0, 1), 1),
        ((1, 2), 1),
    ]
    assert result.quads == ()
    assert result.omissions == ()


def test_two_dimensional_cells_leave_an_invalid_corner_as_a_gap(tmp_path: Path) -> None:
    run = _generate_cell_grid(
        tmp_path,
        name="missing",
        pressures_bar=(4.0, 1.0),
    )
    frame = pd.read_parquet(run / "dataset.parquet")
    assert len(frame) == 4
    frame["phase"] = "gas"
    frame.loc[3, "valid"] = False
    frame.loc[3, "failure_layer"] = "property"
    frame.loc[3, "failure_code"] = "backend_error"
    frame.loc[3, "failure_message"] = "controlled missing corner"
    frame.loc[3, "failure_property"] = "specific_enthalpy"
    frame.loc[3, "backend_error_type"] = "ValueError"
    frame.loc[3, "backend_error_message"] = "controlled missing corner"
    _rewrite_dataset(run, frame)
    profile = _profile(run)

    result = build_scene_cells(profile, _topology_request(profile))

    assert [point.row_position for point in result.topology.projection.points] == [0, 1, 2]
    assert [(edge.point_indices, edge.topology_axis_index) for edge in result.edges] == [
        ((0, 2), 0),
        ((0, 1), 1),
    ]
    assert result.quads == ()
    assert result.blocks[0].omitted_missing_corner_count == 1
    assert result.blocks[0].omitted_degenerate_count == 0
    assert [(gap.code, gap.count, gap.block_index) for gap in result.omissions] == [
        ("missing_topology_corner", 1, 0)
    ]
    assert result.topology.blocks[0].topology.gap_locations[0].level_indices == (1, 1)


@pytest.mark.parametrize(
    (
        "name",
        "coordinates",
        "expected_edges",
        "expected_zero",
        "expected_repeated",
        "expected_collinear",
        "expected_quads",
    ),
    (
        (
            "repeated",
            (
                (0.0, 0.0, 0.0),
                (0.0, 3.0, 0.0),
                (0.0, 0.0, 0.0),
                (2.0, 2.0, 0.0),
            ),
            3,
            1,
            1,
            0,
            0,
        ),
        (
            "collinear",
            (
                (0.0, 0.0, 0.0),
                (3.0, 3.0, 3.0),
                (1.0, 1.0, 1.0),
                (2.0, 2.0, 2.0),
            ),
            4,
            0,
            0,
            1,
            0,
        ),
        (
            "subnormal-area",
            (
                (0.0, 0.0, 0.0),
                (0.0, math.nextafter(0.0, 1.0), 0.0),
                (math.nextafter(0.0, 1.0), 0.0, 0.0),
                (
                    math.nextafter(0.0, 1.0),
                    math.nextafter(0.0, 1.0),
                    0.0,
                ),
            ),
            4,
            0,
            0,
            0,
            1,
        ),
    ),
)
def test_two_dimensional_cells_classify_degeneracy_without_tolerance(
    tmp_path: Path,
    name: str,
    coordinates: tuple[tuple[float, float, float], ...],
    expected_edges: int,
    expected_zero: int,
    expected_repeated: int,
    expected_collinear: int,
    expected_quads: int,
) -> None:
    run = _generate_cell_grid(
        tmp_path,
        name=name,
        pressures_bar=(4.0, 1.0),
    )
    frame = pd.read_parquet(run / "dataset.parquet")
    assert len(frame) == len(coordinates) == 4
    frame["phase"] = "gas"
    for column_index, column in enumerate(
        ("specific_enthalpy_J_kg", "mass_density_kg_m3", "specific_entropy_J_kgK")
    ):
        frame[column] = [coordinate[column_index] for coordinate in coordinates]
    _rewrite_dataset(run, frame)
    profile = _profile(run)

    result = build_scene_cells(profile, _property_request(profile))

    assert result.edge_count == expected_edges
    assert result.edge_projection.blocks[0].omitted_zero_length_count == expected_zero
    assert result.blocks[0].omitted_repeated_vertex_count == expected_repeated
    assert result.blocks[0].omitted_collinear_count == expected_collinear
    assert result.quad_count == expected_quads
    omission_counts = {gap.code: gap.count for gap in result.omissions}
    assert omission_counts.get("zero_length_edge", 0) == expected_zero
    assert omission_counts.get("degenerate_quad", 0) == expected_repeated + expected_collinear
    if expected_quads:
        assert result.quads[0].point_indices == (0, 2, 3, 1)


def test_two_dimensional_cells_never_cross_context_or_duplicate_topology(
    tmp_path: Path,
) -> None:
    run = _generate_cell_grid(
        tmp_path,
        name="contexts",
        pressures_bar=(4.0, 1.0),
    )
    gas = pd.read_parquet(run / "dataset.parquet")
    assert len(gas) == 4
    gas["phase"] = "gas"
    liquid = gas.copy()
    liquid["case_id"] = liquid["case_id"] + 4
    liquid["phase"] = "liquid"
    duplicate = gas.iloc[[0]].copy()
    duplicate["case_id"] = 8
    frame = pd.concat([gas, liquid, duplicate], ignore_index=True)
    _rewrite_dataset(run, frame)
    profile = _profile(run)

    result = build_scene_cells(profile, _topology_request(profile))

    assert [block.context.phase for block in result.topology.blocks] == ["gas", "liquid"]
    gas_block, liquid_block = result.topology.blocks
    assert gas_block.topology.status == "duplicate_locations"
    assert result.edge_projection.blocks[gas_block.index].edges == ()
    assert result.blocks[gas_block.index].quads == ()
    assert liquid_block.topology.status == "exact"
    assert [
        edge.point_indices for edge in result.edge_projection.blocks[liquid_block.index].edges
    ] == [
        (4, 6),
        (4, 5),
        (5, 7),
        (6, 7),
    ]
    assert result.blocks[liquid_block.index].quads[0].point_indices == (4, 6, 7, 5)

    with pytest.raises(ValueError, match="crosses its declared topology block"):
        SceneCellProjection(
            edge_projection=result.edge_projection,
            blocks=(
                result.blocks[0],
                replace(
                    result.blocks[1],
                    quads=(
                        SceneQuad(
                            point_indices=(0, 6, 7, 5),
                            topology_axis_indices=(0, 1),
                        ),
                    ),
                ),
            ),
            omissions=(),
        )
    with pytest.raises(ValueError, match="exact cell order"):
        SceneCellProjection(
            edge_projection=result.edge_projection,
            blocks=(
                result.blocks[0],
                replace(
                    result.blocks[1],
                    quads=(
                        SceneQuad(
                            point_indices=(4, 5, 7, 6),
                            topology_axis_indices=(0, 1),
                        ),
                    ),
                ),
            ),
            omissions=(),
        )
