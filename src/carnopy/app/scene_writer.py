from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from carnopy.app.scene_assembly import SceneGeometryAssembly
from carnopy.app.scene_bundle import (
    SCENE_SCHEMA_VERSION,
    SceneBundleManifest,
    SceneManifestOrphanExclusions,
    SceneManifestScientificBlock,
    SceneManifestTopology,
    SceneManifestTopologyAxis,
    SceneManifestValueExtent,
    SceneScientificPayload,
    scene_content_id,
)
from carnopy.app.scene_cells import SceneBlockCells
from carnopy.app.scene_contracts import SceneCounts, validate_scene_limits
from carnopy.app.scene_edges import SceneBlockEdges
from carnopy.app.scene_encoding import SceneBinaryEncoding, encode_scene_binary
from carnopy.app.scene_integrity import (
    SCENE_BINARY_NAME,
    SCENE_MANIFEST_NAME,
    SceneBundleError,
    canonical_scene_json_bytes,
    write_scene_exclusive_regular_file,
)
from carnopy.app.scene_leases import SceneLease, verify_scene_lease
from carnopy.app.scene_topology import SceneTopologyBlock


@dataclass(frozen=True)
class PreparedSceneBundle:
    """Canonical binary and manifest bytes validated before filesystem writes."""

    encoding: SceneBinaryEncoding
    manifest: SceneBundleManifest
    manifest_bytes: bytes
    bundle_bytes: int

    def __post_init__(self) -> None:
        expected_manifest = canonical_scene_json_bytes(self.manifest.model_dump(mode="json"))
        if self.manifest_bytes != expected_manifest:
            raise ValueError("prepared scene manifest bytes are not canonical")
        if self.manifest.binary != self.encoding.binary_descriptor:
            raise ValueError("prepared scene manifest has the wrong binary identity")
        if self.manifest.counts != self.encoding.counts:
            raise ValueError("prepared scene manifest has the wrong primitive counts")
        if self.manifest.buffers != self.encoding.buffers:
            raise ValueError("prepared scene manifest has the wrong buffer descriptors")
        if self.manifest.blocks != self.encoding.blocks:
            raise ValueError("prepared scene manifest has the wrong block ranges")
        if self.bundle_bytes != len(self.encoding.data) + len(self.manifest_bytes):
            raise ValueError("prepared scene bundle has the wrong exact size")


@dataclass(frozen=True)
class WrittenSceneBundle:
    """One manifest-last worker publication awaiting parent verification."""

    lease: SceneLease
    manifest: SceneBundleManifest
    manifest_path: Path
    binary_path: Path
    manifest_size: int
    binary_size: int
    bundle_size: int


def prepare_scene_bundle(assembly: SceneGeometryAssembly) -> PreparedSceneBundle:
    """Build the canonical manifest and exact bounded bytes without writing files."""

    encoding = encode_scene_binary(assembly)
    scientific_payload = _scientific_payload(assembly, encoding)
    identity_payload: dict[str, object] = {
        "scene_schema_version": SCENE_SCHEMA_VERSION,
        "request_id": assembly.request.request_id,
        "binary": encoding.binary_descriptor.model_dump(mode="json"),
        "counts": encoding.counts.model_dump(mode="json"),
        "blocks": [block.model_dump(mode="json") for block in encoding.blocks],
        "buffers": [buffer.model_dump(mode="json") for buffer in encoding.buffers],
        "scientific_payload": scientific_payload.model_dump(mode="json"),
    }
    manifest = SceneBundleManifest.model_validate(
        {
            **identity_payload,
            "content_id": scene_content_id(identity_payload),
        }
    )
    manifest_bytes = canonical_scene_json_bytes(manifest.model_dump(mode="json"))
    bundle_bytes = len(encoding.data) + len(manifest_bytes)
    validate_scene_limits(
        SceneCounts(
            points=encoding.counts.points,
            edges=encoding.counts.edges,
            quads=encoding.counts.quads,
            bundle_bytes=bundle_bytes,
        )
    )
    return PreparedSceneBundle(
        encoding=encoding,
        manifest=manifest,
        manifest_bytes=manifest_bytes,
        bundle_bytes=bundle_bytes,
    )


def write_scene_bundle(
    lease: SceneLease,
    assembly: SceneGeometryAssembly,
) -> WrittenSceneBundle:
    """Create one complete scene exclusively, publishing its manifest last."""

    verify_scene_lease(lease)
    _require_empty_scene_destination(lease)
    prepared = prepare_scene_bundle(assembly)
    verify_scene_lease(lease)
    _require_empty_scene_destination(lease)

    binary_path = lease.path / SCENE_BINARY_NAME
    manifest_path = lease.path / SCENE_MANIFEST_NAME
    write_scene_exclusive_regular_file(
        binary_path,
        prepared.encoding.data,
        label="scene binary",
    )
    verify_scene_lease(lease)
    write_scene_exclusive_regular_file(
        manifest_path,
        prepared.manifest_bytes,
        label="scene manifest",
    )
    return WrittenSceneBundle(
        lease=lease,
        manifest=prepared.manifest,
        manifest_path=manifest_path,
        binary_path=binary_path,
        manifest_size=len(prepared.manifest_bytes),
        binary_size=len(prepared.encoding.data),
        bundle_size=prepared.bundle_bytes,
    )


def _scientific_payload(
    assembly: SceneGeometryAssembly,
    encoding: SceneBinaryEncoding,
) -> SceneScientificPayload:
    topology_buffers = {buffer.name: buffer for buffer in encoding.buffers}
    topology = SceneManifestTopology(
        status=assembly.profile.topology.status,
        context_fields=assembly.profile.topology.context_fields,
        axes=tuple(
            SceneManifestTopologyAxis(
                index=index,
                field_id=axis.field_id,
                source_column=axis.source_column,
                unit=axis.unit,
                level_count=len(axis.levels),
                levels_sha256=topology_buffers[f"topology_levels.{index}"].sha256,
            )
            for index, axis in enumerate(assembly.profile.topology.axes)
        ),
        reason_code=assembly.profile.topology.reason_code,
        reason=assembly.profile.topology.reason,
    )
    blocks = tuple(
        _scientific_block(topology_block, edge_block, cell_block)
        for topology_block, edge_block, cell_block in zip(
            assembly.topology.blocks,
            assembly.cells.edge_projection.blocks,
            assembly.cells.blocks,
            strict=True,
        )
    )
    return SceneScientificPayload(
        scene_profile_schema_version=assembly.profile.scene_profile_schema_version,
        request=assembly.request,
        source_row_count=assembly.profile.source_row_count,
        retained_row_count=len(assembly.points),
        excluded_row_count=len(assembly.topology.projection.excluded_rows),
        stable_id_field=assembly.topology.projection.stable_id_field,
        fields=assembly.profile.fields,
        topology=topology,
        value_extents=tuple(
            SceneManifestValueExtent(
                role=extent.role,
                field_id=extent.field_id,
                minimum=extent.minimum,
                maximum=extent.maximum,
                logarithmic_available=extent.logarithmic_available,
            )
            for extent in assembly.value_extents
        ),
        point_exclusions=assembly.topology.projection.exclusions,
        primitive_omissions=assembly.cells.omissions,
        capabilities=assembly.capabilities,
        blocks=blocks,
        orphan_exclusions=tuple(
            SceneManifestOrphanExclusions(
                context=group.context,
                excluded_row_count=len(group.exclusions),
            )
            for group in assembly.topology.orphan_exclusions
        ),
    )


def _scientific_block(
    topology_block: SceneTopologyBlock,
    edge_block: SceneBlockEdges,
    cell_block: SceneBlockCells,
) -> SceneManifestScientificBlock:
    topology = topology_block.topology
    return SceneManifestScientificBlock(
        index=topology_block.index,
        context=topology_block.context,
        retained_point_count=len(topology_block.point_indices),
        excluded_row_count=len(topology_block.exclusions),
        topology_status=topology.status,
        topology_dimension=topology.dimension,
        topology_reason_code=topology.reason_code,
        topology_reason=topology.reason,
        topology_location_count=len(topology.locations),
        duplicate_topology_location_count=len(topology.duplicate_locations),
        gap_location_count=len(topology.gap_locations),
        missing_intermediate_level_count=sum(
            len(evidence.level_indices) for evidence in topology.missing_intermediate_levels
        ),
        unlocated_point_count=len(topology.unlocated_point_indices),
        omitted_zero_length_edge_count=edge_block.omitted_zero_length_count,
        omitted_missing_corner_count=cell_block.omitted_missing_corner_count,
        omitted_repeated_vertex_count=cell_block.omitted_repeated_vertex_count,
        omitted_collinear_count=cell_block.omitted_collinear_count,
    )


def _require_empty_scene_destination(lease: SceneLease) -> None:
    for name in (SCENE_BINARY_NAME, SCENE_MANIFEST_NAME):
        path = lease.path / name
        try:
            path.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise SceneBundleError(
                "scene_write_failed",
                f"scene destination cannot be inspected safely: {path}",
            ) from exc
        raise SceneBundleError(
            "scene_write_failed",
            f"scene destination already exists and will not be replaced: {path}",
        )
