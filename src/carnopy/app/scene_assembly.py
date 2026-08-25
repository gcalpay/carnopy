from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from carnopy.app.scene_bundle import SCENE_BINARY_HEADER
from carnopy.app.scene_cells import SceneCellProjection, SceneQuad, build_scene_cells
from carnopy.app.scene_contracts import (
    SceneCapabilityBlocker,
    SceneCounts,
    SceneProfile,
    SceneRepresentationCapability,
    SceneRequest,
    validate_scene_limits,
)
from carnopy.app.scene_edges import SceneEdge
from carnopy.app.scene_geometry import RetainedScenePoint
from carnopy.app.scene_integrity import canonical_scene_json_bytes
from carnopy.app.scene_profiles import Checkpoint
from carnopy.app.scene_topology import SceneTopologyBlock, SceneTopologyPartition

_FLOAT64_BYTES = 8
_UINT64_BYTES = 8
_UINT32_BYTES = 4

SceneValueRole = Literal["x", "y", "z", "scalar"]


@dataclass(frozen=True)
class SceneValueExtent:
    """Exact retained binary64 range and logarithmic-domain availability."""

    role: SceneValueRole
    field_id: str
    minimum: float
    maximum: float
    logarithmic_available: bool

    def __post_init__(self) -> None:
        if not self.field_id:
            raise ValueError("scene value extent requires a field ID")
        if not math.isfinite(self.minimum) or not math.isfinite(self.maximum):
            raise ValueError("scene value extent requires finite bounds")
        if self.minimum > self.maximum:
            raise ValueError("scene value extent minimum exceeds its maximum")
        if self.logarithmic_available != (self.minimum > 0.0):
            raise ValueError("scene logarithmic availability disagrees with its retained range")


@dataclass(frozen=True)
class SceneStorageProjection:
    """Pre-serialization byte projection for the binary and manifest facts."""

    topology_level_count: int
    binary_bytes: int
    manifest_projection_bytes: int
    bundle_projection_bytes: int

    def __post_init__(self) -> None:
        if (
            min(
                self.topology_level_count,
                self.binary_bytes,
                self.manifest_projection_bytes,
                self.bundle_projection_bytes,
            )
            < 0
        ):
            raise ValueError("scene storage projection values must be non-negative")
        if self.bundle_projection_bytes != self.binary_bytes + self.manifest_projection_bytes:
            raise ValueError("scene bundle projection disagrees with its component sizes")


@dataclass(frozen=True)
class SceneGeometryAssembly:
    """Complete bounded exact geometry before any scene serialization."""

    cells: SceneCellProjection
    capabilities: tuple[SceneRepresentationCapability, ...]
    value_extents: tuple[SceneValueExtent, ...]
    storage: SceneStorageProjection
    counts: SceneCounts

    def __post_init__(self) -> None:
        if tuple(capability.representation for capability in self.capabilities) != (
            "points",
            "wireframe",
            "surface",
        ):
            raise ValueError("scene capabilities must use canonical representation order")
        if not self.capabilities[0].available:
            raise ValueError("a retained scene must always provide its exact points")
        expected_extents: tuple[tuple[SceneValueRole, str], ...] = (
            (
                ("x", self.request.x_field),
                ("y", self.request.y_field),
                ("z", self.request.z_field),
                ("scalar", self.request.scalar_field),
            )
            if self.request.scalar_field is not None
            else (
                ("x", self.request.x_field),
                ("y", self.request.y_field),
                ("z", self.request.z_field),
            )
        )
        if (
            tuple((extent.role, extent.field_id) for extent in self.value_extents)
            != expected_extents
        ):
            raise ValueError("scene value extents do not follow selected-field order")
        if self.counts != SceneCounts(
            points=len(self.points),
            edges=len(self.edges),
            quads=len(self.quads),
            bundle_bytes=self.storage.bundle_projection_bytes,
        ):
            raise ValueError("scene geometry counts disagree with exact primitives")

    @property
    def topology(self) -> SceneTopologyPartition:
        return self.cells.topology

    @property
    def profile(self) -> SceneProfile:
        return self.topology.projection.profile

    @property
    def request(self) -> SceneRequest:
        return self.topology.projection.request

    @property
    def points(self) -> tuple[RetainedScenePoint, ...]:
        return self.topology.projection.points

    @property
    def edges(self) -> tuple[SceneEdge, ...]:
        return self.cells.edges

    @property
    def quads(self) -> tuple[SceneQuad, ...]:
        return self.cells.quads


def build_scene_geometry(
    profile: SceneProfile,
    request: SceneRequest,
    *,
    checkpoint: Checkpoint | None = None,
) -> SceneGeometryAssembly:
    """Build and bound every exact renderer-neutral Stage 6 primitive."""

    cells = build_scene_cells(profile, request, checkpoint=checkpoint)
    primitive_counts = SceneCounts(
        points=len(cells.topology.projection.points),
        edges=cells.edge_count,
        quads=cells.quad_count,
        bundle_bytes=0,
    )
    validate_scene_limits(primitive_counts)
    capabilities = derive_scene_capabilities(cells)
    value_extents = _scene_value_extents(cells)
    storage = _project_scene_storage(cells, capabilities, value_extents)
    counts = SceneCounts(
        points=primitive_counts.points,
        edges=primitive_counts.edges,
        quads=primitive_counts.quads,
        bundle_bytes=storage.bundle_projection_bytes,
    )
    validate_scene_limits(counts)
    if checkpoint is not None:
        checkpoint()
    return SceneGeometryAssembly(
        cells=cells,
        capabilities=capabilities,
        value_extents=value_extents,
        storage=storage,
        counts=counts,
    )


def derive_scene_capabilities(
    cells: SceneCellProjection,
) -> tuple[SceneRepresentationCapability, ...]:
    """Apply the global all-retained-block rule to exact scene primitives."""

    wireframe_blockers: list[SceneCapabilityBlocker] = []
    surface_blockers: list[SceneCapabilityBlocker] = []
    for topology_block, edge_block, cell_block in zip(
        cells.topology.blocks,
        cells.edge_projection.blocks,
        cells.blocks,
        strict=True,
    ):
        wireframe_blocker = _connectivity_blocker(
            topology_block,
            representation="wireframe",
            primitive_count=len(edge_block.edges),
        )
        if wireframe_blocker is not None:
            wireframe_blockers.append(wireframe_blocker)
        surface_blocker = _connectivity_blocker(
            topology_block,
            representation="surface",
            primitive_count=len(cell_block.quads),
        )
        if surface_blocker is not None:
            surface_blockers.append(surface_blocker)
    return (
        SceneRepresentationCapability(representation="points", available=True),
        SceneRepresentationCapability(
            representation="wireframe",
            available=not wireframe_blockers,
            blockers=tuple(wireframe_blockers),
        ),
        SceneRepresentationCapability(
            representation="surface",
            available=not surface_blockers,
            blockers=tuple(surface_blockers),
        ),
    )


def _connectivity_blocker(
    block: SceneTopologyBlock,
    *,
    representation: Literal["wireframe", "surface"],
    primitive_count: int,
) -> SceneCapabilityBlocker | None:
    topology = block.topology
    if topology.status in {"unavailable", "incomplete"}:
        return SceneCapabilityBlocker(
            code="topology_unavailable",
            message=_block_reason(block, "does not have complete verified topology"),
            block_index=block.index,
        )
    if topology.status == "unsupported_dimension":
        return SceneCapabilityBlocker(
            code="unsupported_topology_dimension",
            message=_block_reason(block, "has an unsupported topology dimension"),
            block_index=block.index,
        )
    if topology.status == "missing_context":
        fields = ", ".join(topology.missing_context_fields)
        return SceneCapabilityBlocker(
            code="missing_context",
            message=f"Block {block.index} lacks required context: {fields}.",
            block_index=block.index,
        )
    if topology.status == "duplicate_locations":
        return SceneCapabilityBlocker(
            code="duplicate_topology_location",
            message=f"Block {block.index} contains duplicate topology locations.",
            block_index=block.index,
        )
    if primitive_count:
        return None
    if representation == "wireframe":
        return SceneCapabilityBlocker(
            code="no_valid_edges",
            message=f"Block {block.index} has no valid exact adjacency edge.",
            block_index=block.index,
        )
    return SceneCapabilityBlocker(
        code="no_valid_quads",
        message=f"Block {block.index} has no valid exact ordered quad.",
        block_index=block.index,
    )


def _block_reason(block: SceneTopologyBlock, fallback: str) -> str:
    reason = block.topology.reason.rstrip(".") or fallback
    return f"Block {block.index} {reason}."


def _scene_value_extents(cells: SceneCellProjection) -> tuple[SceneValueExtent, ...]:
    projection = cells.topology.projection
    request = projection.request
    roles: list[tuple[SceneValueRole, str, tuple[float, ...]]] = [
        ("x", request.x_field, tuple(point.coordinates[0] for point in projection.points)),
        ("y", request.y_field, tuple(point.coordinates[1] for point in projection.points)),
        ("z", request.z_field, tuple(point.coordinates[2] for point in projection.points)),
    ]
    if request.scalar_field is not None:
        scalars = tuple(point.scalar for point in projection.points)
        if any(value is None for value in scalars):
            raise ValueError("selected scene scalar is missing from a retained point")
        roles.append(
            (
                "scalar",
                request.scalar_field,
                tuple(value for value in scalars if value is not None),
            )
        )
    return tuple(
        SceneValueExtent(
            role=role,
            field_id=field_id,
            minimum=min(values),
            maximum=max(values),
            logarithmic_available=min(values) > 0.0,
        )
        for role, field_id, values in roles
    )


def _project_scene_storage(
    cells: SceneCellProjection,
    capabilities: tuple[SceneRepresentationCapability, ...],
    value_extents: tuple[SceneValueExtent, ...],
) -> SceneStorageProjection:
    projection = cells.topology.projection
    point_count = len(projection.points)
    topology_level_count = sum(len(axis.levels) for axis in projection.profile.topology.axes)
    binary_bytes = (
        SCENE_BINARY_HEADER.size
        + point_count * 3 * _FLOAT64_BYTES
        + (point_count * _FLOAT64_BYTES if projection.request.scalar_field is not None else 0)
        + point_count * _UINT64_BYTES
        + point_count * _UINT64_BYTES
        + cells.edge_count * 2 * _UINT32_BYTES
        + cells.quad_count * 4 * _UINT32_BYTES
        + topology_level_count * _FLOAT64_BYTES
    )
    manifest_projection = _manifest_fact_projection(
        cells,
        capabilities,
        value_extents,
        binary_bytes=binary_bytes,
    )
    manifest_bytes = len(canonical_scene_json_bytes(manifest_projection))
    return SceneStorageProjection(
        topology_level_count=topology_level_count,
        binary_bytes=binary_bytes,
        manifest_projection_bytes=manifest_bytes,
        bundle_projection_bytes=binary_bytes + manifest_bytes,
    )


def _manifest_fact_projection(
    cells: SceneCellProjection,
    capabilities: tuple[SceneRepresentationCapability, ...],
    value_extents: tuple[SceneValueExtent, ...],
    *,
    binary_bytes: int,
) -> dict[str, object]:
    topology = cells.topology
    return {
        "request": topology.projection.request.model_dump(mode="json"),
        "profile": topology.projection.profile.model_dump(mode="json"),
        "value_extents": [extent.__dict__ for extent in value_extents],
        "capabilities": [capability.model_dump(mode="json") for capability in capabilities],
        "point_exclusions": [
            exclusion.model_dump(mode="json") for exclusion in topology.projection.exclusions
        ],
        "primitive_omissions": [omission.model_dump(mode="json") for omission in cells.omissions],
        "blocks": [
            {
                "index": block.index,
                "context": block.context.model_dump(mode="json"),
                "point_count": len(block.point_indices),
                "edge_count": len(cells.edge_projection.blocks[block.index].edges),
                "quad_count": len(cells.blocks[block.index].quads),
                "topology_status": block.topology.status,
                "topology_dimension": block.topology.dimension,
                "topology_reason_code": block.topology.reason_code,
                "excluded_row_count": len(block.exclusions),
            }
            for block in topology.blocks
        ],
        "projected_binary_bytes": binary_bytes,
    }
