from __future__ import annotations

from dataclasses import dataclass

from carnopy.app.scene_contracts import (
    SceneGapSummary,
    SceneProfile,
    SceneRequest,
    canonical_gap_summaries,
)
from carnopy.app.scene_edges import (
    SceneEdge,
    SceneEdgeProjection,
    _build_topology_edges,
    _varying_axis_indices,
)
from carnopy.app.scene_profiles import Checkpoint
from carnopy.app.scene_topology import (
    SceneTopologyBlock,
    SceneTopologyPartition,
    analyze_scene_topology,
)

Coordinates3D = tuple[float, float, float]
QuadCoordinates = tuple[Coordinates3D, Coordinates3D, Coordinates3D, Coordinates3D]
QuadPointIndices = tuple[int, int, int, int]
IntegerAxisCoordinates = tuple[int, int, int, int]
IntegerVector3 = tuple[int, int, int]
IntegerQuadCoordinates = tuple[IntegerVector3, IntegerVector3, IntegerVector3, IntegerVector3]


@dataclass(frozen=True)
class SceneQuad:
    """One complete cell preserving its exact ordered four-corner identity."""

    point_indices: tuple[int, int, int, int]
    topology_axis_indices: tuple[int, int]

    def __post_init__(self) -> None:
        if len(self.point_indices) != 4 or any(index < 0 for index in self.point_indices):
            raise ValueError("scene quad requires four non-negative point indices")
        if len(set(self.point_indices)) != 4:
            raise ValueError("scene quad must not repeat a point index")
        if (
            len(self.topology_axis_indices) != 2
            or self.topology_axis_indices[0] < 0
            or self.topology_axis_indices[0] >= self.topology_axis_indices[1]
        ):
            raise ValueError("scene quad requires two ordered topology axis indices")


@dataclass(frozen=True)
class SceneBlockCells:
    """Exact two-dimensional quads and deterministic omissions for one block."""

    block_index: int
    quads: tuple[SceneQuad, ...]
    omitted_missing_corner_count: int
    omitted_repeated_vertex_count: int
    omitted_collinear_count: int

    def __post_init__(self) -> None:
        if self.block_index < 0:
            raise ValueError("scene cell block index must be non-negative")
        if any(
            count < 0
            for count in (
                self.omitted_missing_corner_count,
                self.omitted_repeated_vertex_count,
                self.omitted_collinear_count,
            )
        ):
            raise ValueError("scene cell omission counts must be non-negative")
        identities = [quad.point_indices for quad in self.quads]
        if len(set(identities)) != len(identities):
            raise ValueError("scene cell block repeats a quad")

    @property
    def omitted_degenerate_count(self) -> int:
        return self.omitted_repeated_vertex_count + self.omitted_collinear_count


@dataclass(frozen=True)
class SceneCellProjection:
    """Exact one- and two-dimensional primitives over one topology partition."""

    edge_projection: SceneEdgeProjection
    blocks: tuple[SceneBlockCells, ...]
    omissions: tuple[SceneGapSummary, ...]

    def __post_init__(self) -> None:
        topology = self.edge_projection.topology
        if tuple(block.block_index for block in self.blocks) != tuple(range(len(topology.blocks))):
            raise ValueError("scene cell blocks must align with topology block order")
        if self.omissions != _cell_omission_summaries(self.edge_projection, self.blocks):
            raise ValueError("scene cell omissions disagree with block counts")
        identities: list[tuple[int, int, int, int]] = []
        for topology_block, cell_block in zip(topology.blocks, self.blocks, strict=True):
            self._validate_block_quads(topology_block, cell_block)
            identities.extend(quad.point_indices for quad in cell_block.quads)
        if len(set(identities)) != len(identities):
            raise ValueError("scene cell projection repeats a quad across blocks")

    def _validate_block_quads(
        self,
        topology_block: SceneTopologyBlock,
        cell_block: SceneBlockCells,
    ) -> None:
        if cell_block.quads and (
            topology_block.topology.status != "exact" or topology_block.topology.dimension != 2
        ):
            raise ValueError("scene quads require exact two-dimensional topology")
        active_axes = _varying_axis_indices(topology_block)
        location_by_point = {
            location.point_indices[0]: location
            for location in topology_block.topology.locations
            if len(location.point_indices) == 1
        }
        points = self.edge_projection.topology.projection.points
        for quad in cell_block.quads:
            if quad.topology_axis_indices != active_axes:
                raise ValueError("scene quad axes disagree with its topology block")
            if any(index not in topology_block.point_indices for index in quad.point_indices):
                raise ValueError("scene quad crosses its declared topology block")
            try:
                locations = tuple(location_by_point[index] for index in quad.point_indices)
            except KeyError as exc:
                raise ValueError("scene quad corner has no unambiguous topology location") from exc
            expected_levels = _ordered_cell_corner_levels(
                locations[0].level_indices,
                active_axes,
            )
            if tuple(location.level_indices for location in locations) != expected_levels:
                raise ValueError("scene quad corners do not follow exact cell order")
            coordinates: QuadCoordinates = (
                points[quad.point_indices[0]].coordinates,
                points[quad.point_indices[1]].coordinates,
                points[quad.point_indices[2]].coordinates,
                points[quad.point_indices[3]].coordinates,
            )
            if len(set(coordinates)) != 4:
                raise ValueError("scene cell projection contains a repeated-vertex quad")
            if _coordinates_exactly_collinear(coordinates):
                raise ValueError("scene cell projection contains an exactly collinear quad")

    @property
    def topology(self) -> SceneTopologyPartition:
        return self.edge_projection.topology

    @property
    def edges(self) -> tuple[SceneEdge, ...]:
        return self.edge_projection.edges

    @property
    def quads(self) -> tuple[SceneQuad, ...]:
        return tuple(quad for block in self.blocks for quad in block.quads)

    @property
    def edge_count(self) -> int:
        return self.edge_projection.edge_count

    @property
    def quad_count(self) -> int:
        return sum(len(block.quads) for block in self.blocks)


def build_scene_cells(
    profile: SceneProfile,
    request: SceneRequest,
    *,
    checkpoint: Checkpoint | None = None,
) -> SceneCellProjection:
    """Build exact adjacent edges and ordered complete-cell quads without repair."""

    topology = analyze_scene_topology(profile, request, checkpoint=checkpoint)
    edge_projection = _build_topology_edges(
        topology,
        checkpoint=checkpoint,
        included_dimensions=frozenset({1, 2}),
    )
    return _build_topology_cells(edge_projection, checkpoint=checkpoint)


def _build_topology_cells(
    edge_projection: SceneEdgeProjection,
    *,
    checkpoint: Checkpoint | None,
) -> SceneCellProjection:
    blocks = tuple(
        _build_block_cells(
            edge_projection,
            block,
            checkpoint=checkpoint,
        )
        for block in edge_projection.topology.blocks
    )
    return SceneCellProjection(
        edge_projection=edge_projection,
        blocks=blocks,
        omissions=_cell_omission_summaries(edge_projection, blocks),
    )


def _build_block_cells(
    edge_projection: SceneEdgeProjection,
    block: SceneTopologyBlock,
    *,
    checkpoint: Checkpoint | None,
) -> SceneBlockCells:
    if block.topology.status != "exact" or block.topology.dimension != 2:
        return SceneBlockCells(
            block_index=block.index,
            quads=(),
            omitted_missing_corner_count=0,
            omitted_repeated_vertex_count=0,
            omitted_collinear_count=0,
        )
    active_axes = _varying_axis_indices(block)
    if len(active_axes) != 2:
        raise ValueError("exact two-dimensional topology has inconsistent varying axes")
    location_by_levels = {location.level_indices: location for location in block.topology.locations}
    first_axis, second_axis = active_axes
    first_levels = tuple(
        location.level_indices[first_axis] for location in block.topology.locations
    )
    second_levels = tuple(
        location.level_indices[second_axis] for location in block.topology.locations
    )
    template = block.topology.locations[0].level_indices
    points = edge_projection.topology.projection.points
    quads: list[SceneQuad] = []
    missing_corner_count = 0
    repeated_vertex_count = 0
    collinear_count = 0
    candidate_index = 0
    for first_level in range(min(first_levels), max(first_levels)):
        for second_level in range(min(second_levels), max(second_levels)):
            if checkpoint is not None and candidate_index % 1_024 == 0:
                checkpoint()
            candidate_index += 1
            corner_levels = _ordered_cell_corner_levels(
                _cell_base_levels(
                    template,
                    active_axes,
                    first_level,
                    second_level,
                ),
                active_axes,
            )
            locations = tuple(location_by_levels.get(levels) for levels in corner_levels)
            if any(location is None for location in locations):
                missing_corner_count += 1
                continue
            exact_locations = tuple(location for location in locations if location is not None)
            if len(exact_locations) != 4:
                raise ValueError("complete scene cell does not contain four exact locations")
            if any(len(location.point_indices) != 1 for location in exact_locations):
                raise ValueError("exact scene topology contains an ambiguous cell corner")
            point_indices: QuadPointIndices = (
                exact_locations[0].point_indices[0],
                exact_locations[1].point_indices[0],
                exact_locations[2].point_indices[0],
                exact_locations[3].point_indices[0],
            )
            if len(set(point_indices)) != 4:
                repeated_vertex_count += 1
                continue
            coordinates: QuadCoordinates = (
                points[point_indices[0]].coordinates,
                points[point_indices[1]].coordinates,
                points[point_indices[2]].coordinates,
                points[point_indices[3]].coordinates,
            )
            if len(set(coordinates)) != 4:
                repeated_vertex_count += 1
                continue
            if _coordinates_exactly_collinear(coordinates):
                collinear_count += 1
                continue
            quads.append(
                SceneQuad(
                    point_indices=point_indices,
                    topology_axis_indices=active_axes,
                )
            )
    return SceneBlockCells(
        block_index=block.index,
        quads=tuple(quads),
        omitted_missing_corner_count=missing_corner_count,
        omitted_repeated_vertex_count=repeated_vertex_count,
        omitted_collinear_count=collinear_count,
    )


def _cell_base_levels(
    template: tuple[int, ...],
    active_axes: tuple[int, int],
    first_level: int,
    second_level: int,
) -> tuple[int, ...]:
    result = list(template)
    result[active_axes[0]] = first_level
    result[active_axes[1]] = second_level
    return tuple(result)


def _ordered_cell_corner_levels(
    base: tuple[int, ...],
    active_axes: tuple[int, int],
) -> tuple[tuple[int, ...], tuple[int, ...], tuple[int, ...], tuple[int, ...]]:
    first_axis, second_axis = active_axes
    first = list(base)
    first[first_axis] += 1
    diagonal = list(first)
    diagonal[second_axis] += 1
    second = list(base)
    second[second_axis] += 1
    return base, tuple(first), tuple(diagonal), tuple(second)


def _coordinates_exactly_collinear(
    coordinates: QuadCoordinates,
) -> bool:
    """Test exact binary64 collinearity after invertible per-axis integer scaling."""

    integer_axes: list[IntegerAxisCoordinates] = []
    for axis_index in range(3):
        ratios = tuple(point[axis_index].as_integer_ratio() for point in coordinates)
        common_denominator = max(denominator for _, denominator in ratios)
        scaled = tuple(
            numerator * (common_denominator // denominator) for numerator, denominator in ratios
        )
        integer_axes.append((scaled[0], scaled[1], scaled[2], scaled[3]))
    integer_points: IntegerQuadCoordinates = (
        (integer_axes[0][0], integer_axes[1][0], integer_axes[2][0]),
        (integer_axes[0][1], integer_axes[1][1], integer_axes[2][1]),
        (integer_axes[0][2], integer_axes[1][2], integer_axes[2][2]),
        (integer_axes[0][3], integer_axes[1][3], integer_axes[2][3]),
    )
    origin = integer_points[0]
    direction: IntegerVector3 = (
        integer_points[1][0] - origin[0],
        integer_points[1][1] - origin[1],
        integer_points[1][2] - origin[2],
    )
    return all(
        _integer_cross_is_zero(
            direction,
            (
                integer_points[point][0] - origin[0],
                integer_points[point][1] - origin[1],
                integer_points[point][2] - origin[2],
            ),
        )
        for point in (2, 3)
    )


def _integer_cross_is_zero(
    first: IntegerVector3,
    second: IntegerVector3,
) -> bool:
    return (
        first[1] * second[2] == first[2] * second[1]
        and first[2] * second[0] == first[0] * second[2]
        and first[0] * second[1] == first[1] * second[0]
    )


def _cell_omission_summaries(
    edge_projection: SceneEdgeProjection,
    blocks: tuple[SceneBlockCells, ...],
) -> tuple[SceneGapSummary, ...]:
    summaries = list(edge_projection.omissions)
    for block in blocks:
        if block.omitted_missing_corner_count:
            summaries.append(
                SceneGapSummary(
                    code="missing_topology_corner",
                    count=block.omitted_missing_corner_count,
                    block_index=block.block_index,
                )
            )
        if block.omitted_degenerate_count:
            summaries.append(
                SceneGapSummary(
                    code="degenerate_quad",
                    count=block.omitted_degenerate_count,
                    block_index=block.block_index,
                )
            )
    return canonical_gap_summaries(summaries)
