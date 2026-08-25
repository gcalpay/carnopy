from __future__ import annotations

import hashlib
import struct
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Final

from carnopy.app.scene_assembly import SceneGeometryAssembly
from carnopy.app.scene_bundle import (
    SCENE_BINARY_HEADER,
    SCENE_BINARY_HEADER_VERSION,
    SCENE_BINARY_MAGIC,
    SCENE_ENDIAN_MARKER,
    SCENE_SCHEMA_VERSION,
    SceneBinaryDescriptor,
    SceneBlockRange,
    SceneBufferDescriptor,
    SceneBufferDType,
    SceneBundleCounts,
)

_UINT64_MAX: Final = 2**64 - 1
_UINT32_MAX: Final = 2**32 - 1


@dataclass(frozen=True)
class SceneBinaryEncoding:
    """Complete deterministic in-memory binary layout, before any lease write."""

    data: bytes
    binary_descriptor: SceneBinaryDescriptor
    counts: SceneBundleCounts
    buffers: tuple[SceneBufferDescriptor, ...]
    blocks: tuple[SceneBlockRange, ...]

    def __post_init__(self) -> None:
        expected_header = SCENE_BINARY_HEADER.pack(
            SCENE_BINARY_MAGIC,
            SCENE_BINARY_HEADER_VERSION,
            SCENE_SCHEMA_VERSION,
            SCENE_ENDIAN_MARKER,
        )
        if self.data[: SCENE_BINARY_HEADER.size] != expected_header:
            raise ValueError("scene encoding has an invalid binary header")
        if self.binary_descriptor.size != len(self.data):
            raise ValueError("scene binary descriptor has the wrong size")
        if self.binary_descriptor.sha256 != _sha256(self.data):
            raise ValueError("scene binary descriptor has the wrong hash")
        _validate_encoded_buffers(self.data, self.buffers)
        _validate_encoded_blocks(self.counts, self.blocks)


def encode_scene_binary(assembly: SceneGeometryAssembly) -> SceneBinaryEncoding:
    """Encode exact geometry into the accepted renderer-neutral binary contract."""

    point_order, remapped_edges, remapped_quads, blocks = _canonical_connectivity(assembly)
    ordered_points = tuple(assembly.points[index] for index in point_order)

    data = bytearray(
        SCENE_BINARY_HEADER.pack(
            SCENE_BINARY_MAGIC,
            SCENE_BINARY_HEADER_VERSION,
            SCENE_SCHEMA_VERSION,
            SCENE_ENDIAN_MARKER,
        )
    )
    buffers: list[SceneBufferDescriptor] = []
    _append_buffer(
        data,
        buffers,
        name="points",
        dtype="float64",
        shape=(len(ordered_points), 3),
        payload=_pack_rows("<ddd", (point.coordinates for point in ordered_points)),
    )
    if assembly.request.scalar_field is not None:
        scalar_rows: list[tuple[float]] = []
        for point in ordered_points:
            if point.scalar is None:
                raise ValueError("selected scene scalar is absent from an encoded point")
            scalar_rows.append((point.scalar,))
        _append_buffer(
            data,
            buffers,
            name="scalars",
            dtype="float64",
            shape=(len(ordered_points),),
            payload=_pack_rows("<d", scalar_rows),
        )
    if any(point.row_position > _UINT64_MAX for point in ordered_points):
        raise ValueError("scene row position exceeds unsigned 64-bit storage")
    _append_buffer(
        data,
        buffers,
        name="row_positions",
        dtype="uint64",
        shape=(len(ordered_points),),
        payload=_pack_rows("<Q", ((point.row_position,) for point in ordered_points)),
    )
    _append_buffer(
        data,
        buffers,
        name="stable_ids",
        dtype="uint64",
        shape=(len(ordered_points),),
        payload=_pack_rows("<Q", ((point.stable_id,) for point in ordered_points)),
    )
    if remapped_edges:
        _append_buffer(
            data,
            buffers,
            name="edges",
            dtype="uint32",
            shape=(len(remapped_edges), 2),
            payload=_pack_rows("<II", remapped_edges),
        )
    if remapped_quads:
        _append_buffer(
            data,
            buffers,
            name="quads",
            dtype="uint32",
            shape=(len(remapped_quads), 4),
            payload=_pack_rows("<IIII", remapped_quads),
        )
    for axis_index, axis in enumerate(assembly.profile.topology.axes):
        _append_buffer(
            data,
            buffers,
            name=f"topology_levels.{axis_index}",
            dtype="float64",
            shape=(len(axis.levels),),
            payload=_pack_rows("<d", ((level,) for level in axis.levels)),
        )

    encoded = bytes(data)
    if len(encoded) != assembly.storage.binary_bytes:
        raise ValueError("encoded scene size disagrees with its exact storage projection")
    counts = SceneBundleCounts(
        points=assembly.counts.points,
        edges=assembly.counts.edges,
        quads=assembly.counts.quads,
    )
    return SceneBinaryEncoding(
        data=encoded,
        binary_descriptor=SceneBinaryDescriptor(
            size=len(encoded),
            sha256=_sha256(encoded),
        ),
        counts=counts,
        buffers=tuple(buffers),
        blocks=blocks,
    )


def _canonical_connectivity(
    assembly: SceneGeometryAssembly,
) -> tuple[
    tuple[int, ...],
    tuple[tuple[int, int], ...],
    tuple[tuple[int, int, int, int], ...],
    tuple[SceneBlockRange, ...],
]:
    point_order = tuple(
        point_index for block in assembly.topology.blocks for point_index in block.point_indices
    )
    old_to_new = [-1] * len(point_order)
    for new_index, old_index in enumerate(point_order):
        old_to_new[old_index] = new_index
    if any(index < 0 for index in old_to_new):
        raise ValueError("scene blocks do not partition encoded points")

    remapped_edges: list[tuple[int, int]] = []
    remapped_quads: list[tuple[int, int, int, int]] = []
    blocks: list[SceneBlockRange] = []
    point_start = 0
    edge_start = 0
    quad_start = 0
    for topology_block, edge_block, cell_block in zip(
        assembly.topology.blocks,
        assembly.cells.edge_projection.blocks,
        assembly.cells.blocks,
        strict=True,
    ):
        block_edges = tuple(
            (old_to_new[edge.point_indices[0]], old_to_new[edge.point_indices[1]])
            for edge in edge_block.edges
        )
        block_quads = tuple(
            (
                old_to_new[quad.point_indices[0]],
                old_to_new[quad.point_indices[1]],
                old_to_new[quad.point_indices[2]],
                old_to_new[quad.point_indices[3]],
            )
            for quad in cell_block.quads
        )
        if any(index > _UINT32_MAX for edge in block_edges for index in edge) or any(
            index > _UINT32_MAX for quad in block_quads for index in quad
        ):
            raise ValueError("scene connectivity exceeds unsigned 32-bit storage")
        blocks.append(
            SceneBlockRange(
                index=topology_block.index,
                context=topology_block.context,
                point_start=point_start,
                point_count=len(topology_block.point_indices),
                edge_start=edge_start,
                edge_count=len(block_edges),
                quad_start=quad_start,
                quad_count=len(block_quads),
            )
        )
        remapped_edges.extend(block_edges)
        remapped_quads.extend(block_quads)
        point_start += len(topology_block.point_indices)
        edge_start += len(block_edges)
        quad_start += len(block_quads)
    return point_order, tuple(remapped_edges), tuple(remapped_quads), tuple(blocks)


def _pack_rows(format_string: str, rows: Iterable[tuple[int | float, ...]]) -> bytes:
    packer = struct.Struct(format_string)
    payload = bytearray()
    for row in rows:
        payload.extend(packer.pack(*row))
    return bytes(payload)


def _append_buffer(
    data: bytearray,
    descriptors: list[SceneBufferDescriptor],
    *,
    name: str,
    dtype: SceneBufferDType,
    shape: tuple[int, ...],
    payload: bytes,
) -> None:
    offset = _align_to_eight(len(data))
    data.extend(b"\0" * (offset - len(data)))
    data.extend(payload)
    descriptors.append(
        SceneBufferDescriptor(
            name=name,
            dtype=dtype,
            offset=offset,
            shape=shape,
            byte_length=len(payload),
            sha256=_sha256(payload),
        )
    )


def _validate_encoded_buffers(
    data: bytes,
    buffers: tuple[SceneBufferDescriptor, ...],
) -> None:
    cursor = SCENE_BINARY_HEADER.size
    for descriptor in buffers:
        expected_offset = _align_to_eight(cursor)
        if descriptor.offset != expected_offset:
            raise ValueError("scene encoding does not use its canonical aligned offset")
        if any(data[cursor : descriptor.offset]):
            raise ValueError("scene encoding contains nonzero alignment padding")
        end = descriptor.offset + descriptor.byte_length
        if end > len(data):
            raise ValueError("scene encoding buffer exceeds the binary boundary")
        if descriptor.sha256 != _sha256(data[descriptor.offset : end]):
            raise ValueError("scene encoding buffer has the wrong hash")
        cursor = end
    if cursor != len(data):
        raise ValueError("scene encoding contains unclaimed trailing bytes")


def _validate_encoded_blocks(
    counts: SceneBundleCounts,
    blocks: tuple[SceneBlockRange, ...],
) -> None:
    point_cursor = edge_cursor = quad_cursor = 0
    for expected_index, block in enumerate(blocks):
        if block.index != expected_index:
            raise ValueError("scene encoded block indices are not canonical")
        if (block.point_start, block.edge_start, block.quad_start) != (
            point_cursor,
            edge_cursor,
            quad_cursor,
        ):
            raise ValueError("scene encoded block ranges are not contiguous")
        point_cursor += block.point_count
        edge_cursor += block.edge_count
        quad_cursor += block.quad_count
    if (point_cursor, edge_cursor, quad_cursor) != (
        counts.points,
        counts.edges,
        counts.quads,
    ):
        raise ValueError("scene encoded block ranges do not partition its primitives")


def _align_to_eight(value: int) -> int:
    return (value + 7) & ~7


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
