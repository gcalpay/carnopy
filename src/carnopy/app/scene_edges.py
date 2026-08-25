from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise

from carnopy.app.scene_contracts import (
    SceneGapSummary,
    SceneProfile,
    SceneRequest,
    canonical_gap_summaries,
)
from carnopy.app.scene_profiles import Checkpoint
from carnopy.app.scene_topology import (
    SceneTopologyBlock,
    SceneTopologyLocation,
    SceneTopologyPartition,
    analyze_scene_topology,
)


@dataclass(frozen=True)
class SceneEdge:
    """One oriented edge between exact adjacent source-sampling locations."""

    point_indices: tuple[int, int]
    topology_axis_index: int

    def __post_init__(self) -> None:
        if len(self.point_indices) != 2 or any(index < 0 for index in self.point_indices):
            raise ValueError("scene edge requires two non-negative point indices")
        if self.point_indices[0] == self.point_indices[1]:
            raise ValueError("scene edge endpoints must be distinct points")
        if self.topology_axis_index < 0:
            raise ValueError("scene edge topology axis index must be non-negative")


@dataclass(frozen=True)
class SceneBlockEdges:
    """Exact one-dimensional edges and omissions for one topology block."""

    block_index: int
    edges: tuple[SceneEdge, ...]
    omitted_zero_length_count: int

    def __post_init__(self) -> None:
        if self.block_index < 0:
            raise ValueError("scene edge block index must be non-negative")
        if self.omitted_zero_length_count < 0:
            raise ValueError("scene zero-length edge count must be non-negative")
        pairs = [edge.point_indices for edge in self.edges]
        if len(set(pairs)) != len(pairs):
            raise ValueError("scene edge block repeats an edge")


@dataclass(frozen=True)
class SceneEdgeProjection:
    """One-dimensional edges over an exact topology partition."""

    topology: SceneTopologyPartition
    blocks: tuple[SceneBlockEdges, ...]
    omissions: tuple[SceneGapSummary, ...]

    def __post_init__(self) -> None:
        if tuple(block.block_index for block in self.blocks) != tuple(
            range(len(self.topology.blocks))
        ):
            raise ValueError("scene edge blocks must align with topology block order")
        expected_omissions = canonical_gap_summaries(
            SceneGapSummary(
                code="zero_length_edge",
                count=block.omitted_zero_length_count,
                block_index=block.block_index,
            )
            for block in self.blocks
            if block.omitted_zero_length_count
        )
        if self.omissions != expected_omissions:
            raise ValueError("scene edge omissions disagree with block counts")
        pairs: list[tuple[int, int]] = []
        for topology_block, edge_block in zip(
            self.topology.blocks,
            self.blocks,
            strict=True,
        ):
            self._validate_block_edges(topology_block, edge_block)
            pairs.extend(edge.point_indices for edge in edge_block.edges)
        if len(set(pairs)) != len(pairs):
            raise ValueError("scene edge projection repeats an edge across blocks")

    def _validate_block_edges(
        self,
        topology_block: SceneTopologyBlock,
        edge_block: SceneBlockEdges,
    ) -> None:
        if edge_block.edges and (
            topology_block.topology.status != "exact" or topology_block.topology.dimension != 1
        ):
            raise ValueError("scene edges require exact one-dimensional block topology")
        location_by_point = {
            location.point_indices[0]: location
            for location in topology_block.topology.locations
            if len(location.point_indices) == 1
        }
        for edge in edge_block.edges:
            if any(index not in topology_block.point_indices for index in edge.point_indices):
                raise ValueError("scene edge crosses its declared topology block")
            try:
                first = location_by_point[edge.point_indices[0]]
                second = location_by_point[edge.point_indices[1]]
            except KeyError as exc:
                raise ValueError(
                    "scene edge endpoint has no unambiguous topology location"
                ) from exc
            if not _locations_are_oriented_neighbors(
                first,
                second,
                edge.topology_axis_index,
            ):
                raise ValueError("scene edge endpoints are not oriented adjacent levels")
            points = self.topology.projection.points
            if (
                points[edge.point_indices[0]].coordinates
                == points[edge.point_indices[1]].coordinates
            ):
                raise ValueError("scene edge projection contains an exact zero-length edge")

    @property
    def edges(self) -> tuple[SceneEdge, ...]:
        return tuple(edge for block in self.blocks for edge in block.edges)

    @property
    def edge_count(self) -> int:
        return sum(len(block.edges) for block in self.blocks)


def build_scene_edges(
    profile: SceneProfile,
    request: SceneRequest,
    *,
    checkpoint: Checkpoint | None = None,
) -> SceneEdgeProjection:
    """Build exact one-dimensional adjacency edges without inventing connectivity."""

    topology = analyze_scene_topology(profile, request, checkpoint=checkpoint)
    return _build_topology_edges(topology, checkpoint=checkpoint)


def _build_topology_edges(
    topology: SceneTopologyPartition,
    *,
    checkpoint: Checkpoint | None,
) -> SceneEdgeProjection:
    blocks: list[SceneBlockEdges] = []
    for block in topology.blocks:
        if checkpoint is not None:
            checkpoint()
        edges, zero_length_count = _build_block_edges(
            topology,
            block,
            checkpoint=checkpoint,
        )
        blocks.append(
            SceneBlockEdges(
                block_index=block.index,
                edges=edges,
                omitted_zero_length_count=zero_length_count,
            )
        )
    omissions = canonical_gap_summaries(
        SceneGapSummary(
            code="zero_length_edge",
            count=block.omitted_zero_length_count,
            block_index=block.block_index,
        )
        for block in blocks
        if block.omitted_zero_length_count
    )
    return SceneEdgeProjection(
        topology=topology,
        blocks=tuple(blocks),
        omissions=omissions,
    )


def _build_block_edges(
    topology: SceneTopologyPartition,
    block: SceneTopologyBlock,
    *,
    checkpoint: Checkpoint | None,
) -> tuple[tuple[SceneEdge, ...], int]:
    if block.topology.status != "exact" or block.topology.dimension != 1:
        return (), 0
    varying_axes = tuple(
        axis_index
        for axis_index in range(len(block.topology.axes))
        if len({location.level_indices[axis_index] for location in block.topology.locations}) > 1
    )
    if len(varying_axes) != 1:
        raise ValueError("exact one-dimensional topology has inconsistent varying axes")
    axis_index = varying_axes[0]
    ordered = tuple(
        sorted(
            block.topology.locations,
            key=lambda location: location.level_indices[axis_index],
        )
    )
    edges: list[SceneEdge] = []
    zero_length_count = 0
    points = topology.projection.points
    for candidate_index, (first, second) in enumerate(pairwise(ordered)):
        if checkpoint is not None and candidate_index % 1_024 == 0:
            checkpoint()
        if not _locations_are_oriented_neighbors(first, second, axis_index):
            continue
        if len(first.point_indices) != 1 or len(second.point_indices) != 1:
            raise ValueError("exact scene topology contains an ambiguous location")
        point_indices = (first.point_indices[0], second.point_indices[0])
        if points[point_indices[0]].coordinates == points[point_indices[1]].coordinates:
            zero_length_count += 1
            continue
        edges.append(
            SceneEdge(
                point_indices=point_indices,
                topology_axis_index=axis_index,
            )
        )
    return tuple(edges), zero_length_count


def _locations_are_oriented_neighbors(
    first: SceneTopologyLocation,
    second: SceneTopologyLocation,
    axis_index: int,
) -> bool:
    if axis_index >= len(first.level_indices) or len(first.level_indices) != len(
        second.level_indices
    ):
        return False
    if second.level_indices[axis_index] != first.level_indices[axis_index] + 1:
        return False
    return all(
        first_index == second_index
        for index, (first_index, second_index) in enumerate(
            zip(first.level_indices, second.level_indices, strict=True)
        )
        if index != axis_index
    )
