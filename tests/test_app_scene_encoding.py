from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path

import pandas as pd

from carnopy.api import generate_dataset
from carnopy.app.scene_assembly import SceneGeometryAssembly, build_scene_geometry
from carnopy.app.scene_bundle import (
    SCENE_BINARY_HEADER,
    SCENE_BINARY_MAGIC,
    SCENE_ENDIAN_MARKER,
    SceneBufferDescriptor,
)
from carnopy.app.scene_contracts import NumericRangeFilter, SceneProfile, SceneRequest
from carnopy.app.scene_encoding import (
    SceneBinaryEncoding,
    _append_buffer,
    encode_scene_binary,
)
from carnopy.app.scene_profiles import profile_scene
from carnopy.app.source_inspection import inspect_for_app


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _generate_grid(tmp_path: Path, *, interleaved_contexts: bool) -> Path:
    config = tmp_path / "scene-encoding.yaml"
    config.write_text(
        """schema_version: 2
document_type: dataset
backend:
  name: coolprop
  model: heos
mode: property_table
fluids: [Propane]
grid:
  temperature: {kind: explicit, values: [330.0, 300.0], unit: K}
  pressure: {kind: explicit, values: [4.0, 1.0], unit: bar}
properties: [specific_enthalpy, mass_density]
outputs:
  dataset_formats: [parquet]
""",
        encoding="utf-8",
    )
    run = generate_dataset(config, output_root=tmp_path / "runs").output_directory
    dataset = run / "dataset.parquet"
    frame = pd.read_parquet(dataset)
    if interleaved_contexts:
        rows: list[pd.Series] = []
        for _index, row in frame.iterrows():
            for phase in ("gas", "liquid"):
                copied = row.copy()
                copied["phase"] = phase
                rows.append(copied)
        frame = pd.DataFrame(rows).reset_index(drop=True)
    else:
        frame["phase"] = "gas"
    frame["case_id"] = range(len(frame))
    frame.to_parquet(dataset, index=False)

    metadata_path = run / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["row_count"] = len(frame)
    metadata["valid_row_count"] = len(frame)
    metadata["invalid_row_count"] = 0
    metadata["run_status"] = "completed"
    metadata["artifact_hashes"]["dataset.parquet"] = _sha256(dataset)
    metadata_path.write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return run


def _profile(run: Path) -> SceneProfile:
    inspected = inspect_for_app(run)
    assert len(inspected.scene_bindings) == 1
    return profile_scene(inspected.scene_bindings[0])


def _request(
    profile: SceneProfile,
    *filters: NumericRangeFilter,
    scalar: bool = True,
) -> SceneRequest:
    return SceneRequest(
        binding=profile.binding,
        x_field="temperature",
        y_field="pressure",
        z_field="specific_enthalpy",
        scalar_field="mass_density" if scalar else None,
        filters=filters,
    )


def _descriptor(
    encoding: SceneBinaryEncoding,
    name: str,
) -> SceneBufferDescriptor:
    return next(buffer for buffer in encoding.buffers if buffer.name == name)


def _unpack(
    encoding: SceneBinaryEncoding,
    name: str,
    format_string: str,
) -> tuple[tuple[int | float, ...], ...]:
    descriptor = _descriptor(encoding, name)
    payload = encoding.data[descriptor.offset : descriptor.offset + descriptor.byte_length]
    return tuple(struct.iter_unpack(format_string, payload))


def _canonical_point_order(assembly: SceneGeometryAssembly) -> tuple[int, ...]:
    return tuple(
        point_index for block in assembly.topology.blocks for point_index in block.point_indices
    )


def test_encoding_canonicalizes_interleaved_blocks_and_remaps_exact_primitives(
    tmp_path: Path,
) -> None:
    profile = _profile(_generate_grid(tmp_path, interleaved_contexts=True))
    assembly = build_scene_geometry(profile, _request(profile))

    encoding = encode_scene_binary(assembly)

    point_order = _canonical_point_order(assembly)
    assert point_order == (0, 2, 4, 6, 1, 3, 5, 7)
    assert encoding.data[: SCENE_BINARY_HEADER.size] == SCENE_BINARY_HEADER.pack(
        SCENE_BINARY_MAGIC,
        1,
        1,
        SCENE_ENDIAN_MARKER,
    )
    assert encoding.counts.model_dump() == {"points": 8, "edges": 8, "quads": 2}
    assert tuple(buffer.name for buffer in encoding.buffers) == (
        "points",
        "scalars",
        "row_positions",
        "stable_ids",
        "edges",
        "quads",
        "topology_levels.0",
        "topology_levels.1",
    )
    assert tuple(_unpack(encoding, "row_positions", "<Q")) == tuple(
        (assembly.points[index].row_position,) for index in point_order
    )
    assert tuple(_unpack(encoding, "stable_ids", "<Q")) == tuple(
        (assembly.points[index].stable_id,) for index in point_order
    )
    assert tuple(_unpack(encoding, "points", "<ddd")) == tuple(
        assembly.points[index].coordinates for index in point_order
    )
    assert tuple(_unpack(encoding, "scalars", "<d")) == tuple(
        (assembly.points[index].scalar,) for index in point_order
    )

    old_to_new = {old_index: new_index for new_index, old_index in enumerate(point_order)}
    expected_edges = tuple(
        tuple(old_to_new[index] for index in edge.point_indices)
        for block in assembly.cells.edge_projection.blocks
        for edge in block.edges
    )
    expected_quads = tuple(
        tuple(old_to_new[index] for index in quad.point_indices)
        for block in assembly.cells.blocks
        for quad in block.quads
    )
    assert _unpack(encoding, "edges", "<II") == expected_edges
    assert _unpack(encoding, "quads", "<IIII") == expected_quads
    assert [(block.point_start, block.point_count) for block in encoding.blocks] == [
        (0, 4),
        (4, 4),
    ]
    assert [(block.edge_start, block.edge_count) for block in encoding.blocks] == [
        (0, 4),
        (4, 4),
    ]
    assert [(block.quad_start, block.quad_count) for block in encoding.blocks] == [
        (0, 1),
        (1, 1),
    ]
    for block in encoding.blocks:
        for edge in _unpack(encoding, "edges", "<II")[
            block.edge_start : block.edge_start + block.edge_count
        ]:
            assert all(
                block.point_start <= index < block.point_start + block.point_count for index in edge
            )
        for quad in _unpack(encoding, "quads", "<IIII")[
            block.quad_start : block.quad_start + block.quad_count
        ]:
            assert all(
                block.point_start <= index < block.point_start + block.point_count for index in quad
            )


def test_encoding_is_byte_stable_hashed_aligned_and_preserves_topology_level_order(
    tmp_path: Path,
) -> None:
    profile = _profile(_generate_grid(tmp_path, interleaved_contexts=True))
    assembly = build_scene_geometry(profile, _request(profile))

    first = encode_scene_binary(assembly)
    second = encode_scene_binary(assembly)

    assert first == second
    assert len(first.data) == assembly.storage.binary_bytes
    assert first.binary_descriptor.sha256 == hashlib.sha256(first.data).hexdigest()
    cursor = SCENE_BINARY_HEADER.size
    for descriptor in first.buffers:
        assert descriptor.offset == (cursor + 7) & ~7
        assert first.data[cursor : descriptor.offset] == b"\0" * (descriptor.offset - cursor)
        payload = first.data[descriptor.offset : descriptor.offset + descriptor.byte_length]
        assert descriptor.sha256 == hashlib.sha256(payload).hexdigest()
        cursor = descriptor.offset + descriptor.byte_length
    assert cursor == len(first.data)
    assert _unpack(first, "topology_levels.0", "<d") == tuple(
        (level,) for level in profile.topology.axes[0].levels
    )
    assert _unpack(first, "topology_levels.1", "<d") == tuple(
        (level,) for level in profile.topology.axes[1].levels
    )
    assert profile.topology.axes[0].levels == (330.0, 300.0)
    assert profile.topology.axes[1].levels == (400_000.0, 100_000.0)


def test_points_only_encoding_omits_optional_and_empty_buffers(tmp_path: Path) -> None:
    profile = _profile(_generate_grid(tmp_path, interleaved_contexts=False))
    request = _request(
        profile,
        NumericRangeFilter(field_id="temperature", minimum=330.0, maximum=330.0),
        NumericRangeFilter(field_id="pressure", minimum=400_000.0, maximum=400_000.0),
        scalar=False,
    )
    assembly = build_scene_geometry(profile, request)

    encoding = encode_scene_binary(assembly)

    assert encoding.counts.model_dump() == {"points": 1, "edges": 0, "quads": 0}
    assert tuple(buffer.name for buffer in encoding.buffers) == (
        "points",
        "row_positions",
        "stable_ids",
        "topology_levels.0",
        "topology_levels.1",
    )
    assert len(encoding.blocks) == 1
    assert encoding.blocks[0].point_count == 1
    assert encoding.blocks[0].edge_count == encoding.blocks[0].quad_count == 0
    assert len(encoding.data) == assembly.storage.binary_bytes


def test_layout_helper_zero_fills_a_required_alignment_gap() -> None:
    data = bytearray(SCENE_BINARY_HEADER.pack(SCENE_BINARY_MAGIC, 1, 1, SCENE_ENDIAN_MARKER))
    descriptors: list[SceneBufferDescriptor] = []

    _append_buffer(
        data,
        descriptors,
        name="edges",
        dtype="uint32",
        shape=(1,),
        payload=struct.pack("<I", 7),
    )
    _append_buffer(
        data,
        descriptors,
        name="quads",
        dtype="uint32",
        shape=(1,),
        payload=struct.pack("<I", 9),
    )

    assert descriptors[0].offset == 16
    assert descriptors[1].offset == 24
    assert data[20:24] == b"\0\0\0\0"
