from __future__ import annotations

import hashlib
import math
import re
import struct
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Final, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    ValidationError,
    field_validator,
    model_validator,
)

from carnopy.app.scene_contracts import (
    MAX_SCENE_BUNDLE_BYTES,
    MAX_SCENE_EDGES,
    MAX_SCENE_POINTS,
    MAX_SCENE_QUADS,
    SceneBlockContext,
    SceneContractError,
    SceneFieldProfile,
    SceneGapCode,
    SceneGapSummary,
    SceneRepresentationCapability,
    SceneRequest,
    SceneTopologyStatus,
    canonical_gap_summaries,
    validate_scene_request,
)
from carnopy.app.scene_integrity import (
    SCENE_BINARY_NAME,
    SCENE_MANIFEST_NAME,
    SceneBundleError,
    canonical_scene_json_bytes,
    parse_canonical_scene_json_object,
    read_scene_regular_file,
)
from carnopy.app.scene_leases import SceneLease, verify_scene_lease

SCENE_SCHEMA_VERSION: Final[Literal[1]] = 1
SCENE_BINARY_HEADER_VERSION: Final[Literal[1]] = 1
SCENE_BINARY_MAGIC: Final = b"CARN3D\0\0"
SCENE_ENDIAN_MARKER: Final = 0x01020304
SCENE_BINARY_HEADER: Final = struct.Struct("<8sHHI")

_TOPOLOGY_BUFFER_PATTERN = re.compile(r"^topology_levels\.([0-9]+)$")

NonNegativeInt = Annotated[StrictInt, Field(ge=0)]
PositiveInt = Annotated[StrictInt, Field(gt=0)]
CanonicalSha256 = Annotated[StrictStr, Field(pattern=r"^[0-9a-f]{64}$")]

SceneBufferDType = Literal["float64", "uint64", "uint32"]
SceneManifestValueRole = Literal["x", "y", "z", "scalar"]
SceneManifestStableIdField = Literal["case_id", "prepared_row_id"]
SceneManifestBlockTopologyStatus = Literal[
    "unavailable",
    "zero_dimensional",
    "exact",
    "incomplete",
    "missing_context",
    "duplicate_locations",
    "unsupported_dimension",
]

_DTYPE_ITEM_SIZES: Final[dict[SceneBufferDType, int]] = {
    "float64": 8,
    "uint64": 8,
    "uint32": 4,
}


class SceneBundleCounts(BaseModel):
    """Primitive counts declared independently of binary buffer sizes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    points: Annotated[StrictInt, Field(gt=0, le=MAX_SCENE_POINTS)]
    edges: Annotated[StrictInt, Field(ge=0, le=MAX_SCENE_EDGES)]
    quads: Annotated[StrictInt, Field(ge=0, le=MAX_SCENE_QUADS)]


class SceneBinaryDescriptor(BaseModel):
    """Whole-file identity for the fixed little-endian binary payload."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: Literal["scene.bin"] = SCENE_BINARY_NAME
    header_version: Literal[1] = SCENE_BINARY_HEADER_VERSION
    byte_order: Literal["little"] = "little"
    size: Annotated[StrictInt, Field(ge=SCENE_BINARY_HEADER.size, le=MAX_SCENE_BUNDLE_BYTES)]
    sha256: CanonicalSha256


class SceneBufferDescriptor(BaseModel):
    """One absolute, typed, hash-bound range in ``scene.bin``."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: StrictStr
    dtype: SceneBufferDType
    offset: Annotated[StrictInt, Field(ge=SCENE_BINARY_HEADER.size)]
    shape: tuple[PositiveInt, ...]
    byte_length: PositiveInt
    sha256: CanonicalSha256

    @field_validator("name")
    @classmethod
    def valid_name(cls, value: str) -> str:
        if value in {
            "points",
            "scalars",
            "row_positions",
            "stable_ids",
            "edges",
            "quads",
        }:
            return value
        match = _TOPOLOGY_BUFFER_PATTERN.fullmatch(value)
        if match is None or (match.group(1) != "0" and match.group(1).startswith("0")):
            raise ValueError(f"unsupported scene buffer name: {value!r}")
        return value

    @field_validator("shape")
    @classmethod
    def valid_shape(cls, value: tuple[int, ...]) -> tuple[int, ...]:
        if not value or len(value) > 2:
            raise ValueError("scene buffer shape must have one or two dimensions")
        return value

    @model_validator(mode="after")
    def consistent_byte_length(self) -> SceneBufferDescriptor:
        item_count = math.prod(self.shape)
        expected = item_count * _DTYPE_ITEM_SIZES[self.dtype]
        if self.byte_length != expected:
            raise ValueError(
                f"scene buffer {self.name!r} byte length {self.byte_length} "
                f"does not match shape and dtype ({expected})"
            )
        if self.offset % 8 != 0:
            raise ValueError(f"scene buffer {self.name!r} offset is not 8-byte aligned")
        return self


class SceneBlockRange(BaseModel):
    """One connectivity-isolated range in the global scene arrays."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    index: NonNegativeInt
    context: SceneBlockContext
    point_start: NonNegativeInt
    point_count: PositiveInt
    edge_start: NonNegativeInt
    edge_count: NonNegativeInt
    quad_start: NonNegativeInt
    quad_count: NonNegativeInt


class SceneManifestTopologyAxis(BaseModel):
    """One manifest-bound topology buffer and its semantic identity."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    index: NonNegativeInt
    field_id: StrictStr
    source_column: StrictStr
    unit: StrictStr
    level_count: PositiveInt
    levels_sha256: CanonicalSha256


class SceneManifestTopology(BaseModel):
    """Verified source-topology evidence without duplicating binary levels."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: SceneTopologyStatus
    context_fields: tuple[StrictStr, ...]
    axes: tuple[SceneManifestTopologyAxis, ...]
    reason_code: StrictStr = ""
    reason: StrictStr = ""

    @model_validator(mode="after")
    def consistent_topology(self) -> SceneManifestTopology:
        if tuple(axis.index for axis in self.axes) != tuple(range(len(self.axes))):
            raise ValueError("scene manifest topology axes must be contiguous and ordered")
        if len({axis.field_id for axis in self.axes}) != len(self.axes) or len(
            {axis.source_column for axis in self.axes}
        ) != len(self.axes):
            raise ValueError("scene manifest topology axes require unique fields and columns")
        context_order = tuple(SceneBlockContext.model_fields)
        expected_contexts = tuple(field for field in context_order if field in self.context_fields)
        if self.context_fields != expected_contexts:
            raise ValueError("scene manifest topology context fields are not canonical")
        if self.status == "exact":
            if not self.axes or self.reason_code or self.reason:
                raise ValueError("exact scene manifest topology is inconsistent")
        elif self.axes or not self.reason_code or not self.reason:
            raise ValueError("unavailable scene manifest topology is inconsistent")
        return self


class SceneManifestValueExtent(BaseModel):
    """Exact retained range and presentation-domain evidence for one selection."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    role: SceneManifestValueRole
    field_id: StrictStr
    minimum: float
    maximum: float
    logarithmic_available: StrictBool

    @field_validator("minimum", "maximum", mode="before")
    @classmethod
    def finite_bound(cls, value: object) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("scene manifest value extent must be numeric")
        numeric = float(value)
        if not math.isfinite(numeric):
            raise ValueError("scene manifest value extent must be finite")
        return numeric

    @model_validator(mode="after")
    def consistent_extent(self) -> SceneManifestValueExtent:
        if self.minimum > self.maximum:
            raise ValueError("scene manifest value extent bounds are reversed")
        if self.logarithmic_available != (self.minimum > 0.0):
            raise ValueError("scene manifest logarithmic availability is inconsistent")
        return self


class SceneManifestScientificBlock(BaseModel):
    """Scientific evidence and omission counts for one retained block."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    index: NonNegativeInt
    context: SceneBlockContext
    retained_point_count: PositiveInt
    excluded_row_count: NonNegativeInt
    topology_status: SceneManifestBlockTopologyStatus
    topology_dimension: NonNegativeInt | None
    topology_reason_code: StrictStr = ""
    topology_reason: StrictStr = ""
    topology_location_count: NonNegativeInt
    duplicate_topology_location_count: NonNegativeInt
    gap_location_count: NonNegativeInt
    missing_intermediate_level_count: NonNegativeInt
    unlocated_point_count: NonNegativeInt
    omitted_zero_length_edge_count: NonNegativeInt
    omitted_missing_corner_count: NonNegativeInt
    omitted_repeated_vertex_count: NonNegativeInt
    omitted_collinear_count: NonNegativeInt

    @model_validator(mode="after")
    def consistent_status(self) -> SceneManifestScientificBlock:
        if self.duplicate_topology_location_count > self.topology_location_count:
            raise ValueError("scene manifest duplicate topology count is inconsistent")
        if self.topology_status == "unavailable":
            valid_dimension = self.topology_dimension is None
        elif self.topology_status == "zero_dimensional":
            valid_dimension = self.topology_dimension == 0
        elif self.topology_status == "exact":
            valid_dimension = self.topology_dimension in {1, 2}
        else:
            valid_dimension = self.topology_dimension is not None
        if not valid_dimension:
            raise ValueError("scene manifest block topology dimension is inconsistent")
        blocked = self.topology_status not in {"zero_dimensional", "exact"}
        valid_reason = (
            bool(self.topology_reason_code and self.topology_reason)
            if blocked
            else not self.topology_reason_code and not self.topology_reason
        )
        if not valid_reason:
            raise ValueError("scene manifest block topology reason is inconsistent")
        return self


class SceneManifestOrphanExclusions(BaseModel):
    """Excluded source rows in a context with no retained point."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    context: SceneBlockContext
    excluded_row_count: PositiveInt


class SceneScientificPayload(BaseModel):
    """Canonical scientific facts bound by one private scene manifest."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scientific_payload_schema_version: Literal[1] = 1
    scene_profile_schema_version: Literal[1] = 1
    request: SceneRequest
    source_row_count: PositiveInt
    retained_row_count: PositiveInt
    excluded_row_count: NonNegativeInt
    stable_id_field: SceneManifestStableIdField
    fields: tuple[SceneFieldProfile, ...]
    topology: SceneManifestTopology
    value_extents: tuple[SceneManifestValueExtent, ...]
    point_exclusions: tuple[SceneGapSummary, ...]
    primitive_omissions: tuple[SceneGapSummary, ...]
    capabilities: tuple[SceneRepresentationCapability, ...]
    blocks: tuple[SceneManifestScientificBlock, ...]
    orphan_exclusions: tuple[SceneManifestOrphanExclusions, ...]

    @model_validator(mode="after")
    def consistent_scientific_payload(self) -> SceneScientificPayload:
        if not self.fields or any(
            field.source_row_count != self.source_row_count for field in self.fields
        ):
            raise ValueError("scene manifest fields disagree with the source row count")
        try:
            validate_scene_request(self.request, self.fields)
        except SceneContractError as exc:
            raise ValueError(f"scene manifest request is invalid: {exc.message}") from exc
        field_catalog = {field.field_id: field for field in self.fields}
        for axis in self.topology.axes:
            field = field_catalog.get(axis.field_id)
            if (
                field is None
                or field.column != axis.source_column
                or field.unit != axis.unit
                or field.classification != "source_coordinate"
            ):
                raise ValueError("scene manifest topology axis disagrees with its field")
        expected_stable_id = (
            "prepared_row_id" if self.request.binding.source_kind == "preparation" else "case_id"
        )
        if self.stable_id_field != expected_stable_id:
            raise ValueError("scene manifest stable ID field disagrees with its source kind")
        if self.retained_row_count + self.excluded_row_count != self.source_row_count:
            raise ValueError("scene manifest row counts do not account for the source")
        expected_extents: tuple[tuple[SceneManifestValueRole, str], ...] = (
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
        if tuple((extent.role, extent.field_id) for extent in self.value_extents) != (
            expected_extents
        ):
            raise ValueError("scene manifest value extents do not match the request")
        for extent in self.value_extents:
            field = field_catalog[extent.field_id]
            if (
                field.minimum is None
                or field.maximum is None
                or extent.minimum < field.minimum
                or extent.maximum > field.maximum
            ):
                raise ValueError("scene manifest value extent exceeds its source field range")
        if self.point_exclusions != canonical_gap_summaries(self.point_exclusions) or any(
            gap.block_index is not None
            or gap.code
            not in {
                "filtered",
                "source_invalid",
                "missing_selected_value",
                "nonfinite_selected_value",
            }
            for gap in self.point_exclusions
        ):
            raise ValueError("scene manifest point exclusions are not canonical")
        if sum(gap.count for gap in self.point_exclusions) != self.excluded_row_count:
            raise ValueError("scene manifest point exclusions disagree with excluded rows")
        expected_omissions = canonical_gap_summaries(
            gap for block in self.blocks for gap in _manifest_block_omissions(block)
        )
        if self.primitive_omissions != expected_omissions:
            raise ValueError("scene manifest primitive omissions disagree with block counts")
        if (
            tuple(capability.representation for capability in self.capabilities)
            != (
                "points",
                "wireframe",
                "surface",
            )
            or not self.capabilities[0].available
        ):
            raise ValueError("scene manifest capabilities are not canonical")
        if tuple(block.index for block in self.blocks) != tuple(range(len(self.blocks))):
            raise ValueError("scene manifest scientific blocks are not ordered")
        block_contexts = [block.context for block in self.blocks]
        orphan_contexts = [orphan.context for orphan in self.orphan_exclusions]
        if (
            len(set(block_contexts)) != len(block_contexts)
            or len(set(orphan_contexts)) != len(orphan_contexts)
            or set(block_contexts).intersection(orphan_contexts)
        ):
            raise ValueError("scene manifest scientific contexts are not a partition")
        if sum(block.retained_point_count for block in self.blocks) != self.retained_row_count:
            raise ValueError("scene manifest block point counts are inconsistent")
        if (
            sum(block.excluded_row_count for block in self.blocks)
            + sum(orphan.excluded_row_count for orphan in self.orphan_exclusions)
            != self.excluded_row_count
        ):
            raise ValueError("scene manifest block exclusion counts are inconsistent")
        return self


def _manifest_block_omissions(
    block: SceneManifestScientificBlock,
) -> tuple[SceneGapSummary, ...]:
    omissions: list[SceneGapSummary] = []
    values: tuple[tuple[SceneGapCode, int], ...] = (
        ("zero_length_edge", block.omitted_zero_length_edge_count),
        ("missing_topology_corner", block.omitted_missing_corner_count),
        (
            "degenerate_quad",
            block.omitted_repeated_vertex_count + block.omitted_collinear_count,
        ),
    )
    for code, count in values:
        if count:
            omissions.append(SceneGapSummary(code=code, count=count, block_index=block.index))
    return tuple(omissions)


class SceneBundleManifest(BaseModel):
    """Lightweight structural manifest; scientific metadata remains hash-bound."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scene_schema_version: Literal[1] = SCENE_SCHEMA_VERSION
    request_id: Annotated[StrictStr, Field(pattern=r"^scene-[0-9a-f]{64}$")]
    content_id: Annotated[StrictStr, Field(pattern=r"^scene-content-[0-9a-f]{64}$")]
    binary: SceneBinaryDescriptor
    counts: SceneBundleCounts
    blocks: tuple[SceneBlockRange, ...]
    buffers: tuple[SceneBufferDescriptor, ...]
    scientific_payload: SceneScientificPayload

    @field_validator("blocks")
    @classmethod
    def nonempty_blocks(cls, value: tuple[SceneBlockRange, ...]) -> tuple[SceneBlockRange, ...]:
        if not value:
            raise ValueError("scene manifest requires at least one block")
        return value

    @field_validator("buffers")
    @classmethod
    def nonempty_buffers(
        cls,
        value: tuple[SceneBufferDescriptor, ...],
    ) -> tuple[SceneBufferDescriptor, ...]:
        if not value:
            raise ValueError("scene manifest requires binary buffers")
        return value

    @model_validator(mode="after")
    def consistent_structure(self) -> SceneBundleManifest:
        _validate_buffer_descriptors(self)
        _validate_block_descriptors(self)
        _validate_scientific_payload(self)
        return self


@dataclass(frozen=True)
class VerifiedSceneBundle:
    """A fully verified, immutable adoption result."""

    lease: SceneLease
    manifest: SceneBundleManifest
    manifest_path: Path
    binary_path: Path
    manifest_size: int
    binary_size: int


def verify_scene_bundle(lease: SceneLease) -> VerifiedSceneBundle:
    """Verify a complete scene without importing scientific or rendering libraries."""

    verify_scene_lease(lease)
    manifest_path = lease.path / SCENE_MANIFEST_NAME
    binary_path = lease.path / SCENE_BINARY_NAME
    manifest_bytes = read_scene_regular_file(
        manifest_path,
        maximum_bytes=MAX_SCENE_BUNDLE_BYTES,
        label="scene manifest",
    )
    manifest = _parse_scene_manifest(manifest_bytes)
    binary_bytes = read_scene_regular_file(
        binary_path,
        maximum_bytes=MAX_SCENE_BUNDLE_BYTES,
        label="scene binary",
    )
    if len(manifest_bytes) + len(binary_bytes) > MAX_SCENE_BUNDLE_BYTES:
        raise SceneBundleError(
            "scene_integrity_error",
            "scene manifest and binary exceed the 64 MiB bundle limit",
        )
    _verify_binary(manifest, binary_bytes)
    return VerifiedSceneBundle(
        lease=lease,
        manifest=manifest,
        manifest_path=manifest_path,
        binary_path=binary_path,
        manifest_size=len(manifest_bytes),
        binary_size=len(binary_bytes),
    )


def scene_content_id(manifest_without_content_id: Mapping[str, object]) -> str:
    """Hash every manifest fact, including the whole-binary identity."""

    if "content_id" in manifest_without_content_id:
        raise SceneBundleError(
            "scene_integrity_error",
            "scene content identity input must omit content_id",
        )
    digest = hashlib.sha256(canonical_scene_json_bytes(manifest_without_content_id)).hexdigest()
    return f"scene-content-{digest}"


def _validate_buffer_descriptors(manifest: SceneBundleManifest) -> None:
    names = [buffer.name for buffer in manifest.buffers]
    topology_names = [name for name in names if _TOPOLOGY_BUFFER_PATTERN.fullmatch(name)]
    expected = ["points"]
    if "scalars" in names:
        expected.append("scalars")
    expected.extend(("row_positions", "stable_ids"))
    if manifest.counts.edges:
        expected.append("edges")
    if manifest.counts.quads:
        expected.append("quads")
    expected.extend(f"topology_levels.{index}" for index in range(len(topology_names)))
    if names != expected:
        raise ValueError(
            "scene buffers are missing, duplicated, unknown, or outside canonical order"
        )

    expected_shapes: dict[str, tuple[int, ...]] = {
        "points": (manifest.counts.points, 3),
        "row_positions": (manifest.counts.points,),
        "stable_ids": (manifest.counts.points,),
        "edges": (manifest.counts.edges, 2),
        "quads": (manifest.counts.quads, 4),
    }
    if "scalars" in names:
        expected_shapes["scalars"] = (manifest.counts.points,)
    expected_dtypes: dict[str, SceneBufferDType] = {
        "points": "float64",
        "scalars": "float64",
        "row_positions": "uint64",
        "stable_ids": "uint64",
        "edges": "uint32",
        "quads": "uint32",
    }
    previous_end = SCENE_BINARY_HEADER.size
    for descriptor in manifest.buffers:
        expected_offset = _align_to_eight(previous_end)
        if descriptor.offset < expected_offset:
            raise ValueError(f"scene buffer {descriptor.name!r} overlaps or is out of order")
        if descriptor.name.startswith("topology_levels."):
            if descriptor.dtype != "float64" or len(descriptor.shape) != 1:
                raise ValueError("scene topology level buffers must be one-dimensional float64")
        else:
            if descriptor.dtype != expected_dtypes[descriptor.name]:
                raise ValueError(f"scene buffer {descriptor.name!r} has the wrong dtype")
            if descriptor.shape != expected_shapes[descriptor.name]:
                raise ValueError(f"scene buffer {descriptor.name!r} has the wrong shape")
        previous_end = descriptor.offset + descriptor.byte_length
    if manifest.binary.size != previous_end:
        raise ValueError("scene binary size disagrees with its final buffer boundary")


def _validate_block_descriptors(manifest: SceneBundleManifest) -> None:
    contexts: set[SceneBlockContext] = set()
    point_cursor = 0
    edge_cursor = 0
    quad_cursor = 0
    for expected_index, block in enumerate(manifest.blocks):
        if block.index != expected_index:
            raise ValueError("scene block indices must be contiguous and ordered")
        if block.context in contexts:
            raise ValueError("scene block contexts must be unique")
        contexts.add(block.context)
        if block.point_start != point_cursor:
            raise ValueError("scene block point ranges must partition points in order")
        if block.edge_start != edge_cursor:
            raise ValueError("scene block edge ranges must partition edges in order")
        if block.quad_start != quad_cursor:
            raise ValueError("scene block quad ranges must partition quads in order")
        point_cursor += block.point_count
        edge_cursor += block.edge_count
        quad_cursor += block.quad_count
    if point_cursor != manifest.counts.points:
        raise ValueError("scene block point counts disagree with the global point count")
    if edge_cursor != manifest.counts.edges:
        raise ValueError("scene block edge counts disagree with the global edge count")
    if quad_cursor != manifest.counts.quads:
        raise ValueError("scene block quad counts disagree with the global quad count")


def _validate_scientific_payload(manifest: SceneBundleManifest) -> None:
    payload = manifest.scientific_payload
    if payload.request.request_id != manifest.request_id:
        raise ValueError("scene request identity disagrees with the scientific payload")
    if payload.retained_row_count != manifest.counts.points:
        raise ValueError("scene retained row count disagrees with the point count")
    names = {buffer.name for buffer in manifest.buffers}
    if (payload.request.scalar_field is not None) != ("scalars" in names):
        raise ValueError("scene scalar selection disagrees with its binary buffer")

    topology_buffers = {
        buffer.name: buffer
        for buffer in manifest.buffers
        if buffer.name.startswith("topology_levels.")
    }
    if len(topology_buffers) != len(payload.topology.axes):
        raise ValueError("scene topology axes disagree with their binary buffers")
    for axis in payload.topology.axes:
        descriptor = topology_buffers.get(f"topology_levels.{axis.index}")
        if (
            descriptor is None
            or descriptor.shape != (axis.level_count,)
            or descriptor.sha256 != axis.levels_sha256
        ):
            raise ValueError("scene topology axis identity disagrees with its binary buffer")

    if len(payload.blocks) != len(manifest.blocks):
        raise ValueError("scene scientific blocks disagree with binary block ranges")
    for block_range, scientific_block in zip(
        manifest.blocks,
        payload.blocks,
        strict=True,
    ):
        if (
            scientific_block.index != block_range.index
            or scientific_block.context != block_range.context
            or scientific_block.retained_point_count != block_range.point_count
        ):
            raise ValueError("scene scientific block identity disagrees with its range")
        if scientific_block.topology_status != "exact" and (
            block_range.edge_count or block_range.quad_count
        ):
            raise ValueError("blocked scene topology cannot contain connectivity")
        if scientific_block.topology_dimension != 2 and block_range.quad_count:
            raise ValueError("scene quads require two-dimensional exact topology")

    capability_by_name = {
        capability.representation: capability for capability in payload.capabilities
    }
    if capability_by_name["wireframe"].available != all(
        block.edge_count > 0 for block in manifest.blocks
    ):
        raise ValueError("scene wireframe capability disagrees with block edges")
    if capability_by_name["surface"].available != all(
        block.quad_count > 0 for block in manifest.blocks
    ):
        raise ValueError("scene surface capability disagrees with block quads")


def _parse_scene_manifest(data: bytes) -> SceneBundleManifest:
    raw = parse_canonical_scene_json_object(data, label="scene manifest")
    version = raw.get("scene_schema_version")
    if isinstance(version, bool) or version != SCENE_SCHEMA_VERSION:
        raise SceneBundleError(
            "scene_integrity_error",
            f"unsupported scene manifest schema version: {version!r}",
        )
    try:
        # JSON arrays are the wire representation of immutable tuple fields.
        # Scalar fields remain strict through their ``Strict*`` annotations.
        manifest = SceneBundleManifest.model_validate(raw)
    except (ValidationError, ValueError) as exc:
        raise SceneBundleError(
            "scene_integrity_error",
            f"scene manifest structure is invalid: {exc}",
        ) from exc
    canonical = canonical_scene_json_bytes(manifest.model_dump(mode="json"))
    if data != canonical:
        raise SceneBundleError(
            "scene_integrity_error",
            "scene manifest is not canonical JSON",
        )
    identity_payload = manifest.model_dump(mode="json", exclude={"content_id"})
    expected_identity = scene_content_id(identity_payload)
    if manifest.content_id != expected_identity:
        raise SceneBundleError(
            "scene_integrity_error",
            "scene manifest content identity does not match its canonical contents",
        )
    return manifest


def _verify_binary(manifest: SceneBundleManifest, data: bytes) -> None:
    if len(data) != manifest.binary.size:
        raise SceneBundleError(
            "scene_integrity_error",
            "scene binary length disagrees with the manifest",
        )
    if len(data) < SCENE_BINARY_HEADER.size:
        raise SceneBundleError("scene_integrity_error", "scene binary header is truncated")
    magic, header_version, schema_version, endian_marker = SCENE_BINARY_HEADER.unpack_from(data)
    if magic != SCENE_BINARY_MAGIC:
        raise SceneBundleError("scene_integrity_error", "scene binary magic is incorrect")
    if header_version != SCENE_BINARY_HEADER_VERSION:
        raise SceneBundleError(
            "scene_integrity_error",
            f"unsupported scene binary header version: {header_version}",
        )
    if schema_version != manifest.scene_schema_version:
        raise SceneBundleError(
            "scene_integrity_error",
            "scene binary and manifest schema versions disagree",
        )
    if schema_version != SCENE_SCHEMA_VERSION:
        raise SceneBundleError(
            "scene_integrity_error",
            f"unsupported scene binary schema version: {schema_version}",
        )
    if endian_marker != SCENE_ENDIAN_MARKER:
        raise SceneBundleError(
            "scene_integrity_error",
            "scene binary endianness marker is incorrect",
        )
    if manifest.binary.header_version != header_version:
        raise SceneBundleError(
            "scene_integrity_error",
            "scene binary header version disagrees with the manifest descriptor",
        )

    previous_end = SCENE_BINARY_HEADER.size
    buffers: dict[str, memoryview] = {}
    for descriptor in manifest.buffers:
        padding = data[previous_end : descriptor.offset]
        if any(padding):
            raise SceneBundleError(
                "scene_integrity_error",
                f"scene binary padding before {descriptor.name!r} is not zero",
            )
        end = descriptor.offset + descriptor.byte_length
        if end > len(data):
            raise SceneBundleError(
                "scene_integrity_error",
                f"scene buffer {descriptor.name!r} is outside the binary file",
            )
        view = memoryview(data)[descriptor.offset : end]
        digest = hashlib.sha256(view).hexdigest()
        if digest != descriptor.sha256:
            raise SceneBundleError(
                "scene_integrity_error",
                f"scene buffer {descriptor.name!r} hash does not match",
            )
        buffers[descriptor.name] = view
        previous_end = end
    if previous_end != len(data):
        raise SceneBundleError(
            "scene_integrity_error",
            "scene binary contains trailing or unclaimed bytes",
        )
    if hashlib.sha256(data).hexdigest() != manifest.binary.sha256:
        raise SceneBundleError(
            "scene_integrity_error",
            "scene binary hash does not match the manifest",
        )
    _verify_finite_float_buffers(buffers)
    _verify_value_extents(manifest, buffers)
    _verify_point_identity_buffers(manifest, buffers)
    _verify_connectivity(manifest, buffers)


def _verify_finite_float_buffers(buffers: Mapping[str, memoryview]) -> None:
    for name, view in buffers.items():
        if name not in {"points", "scalars"} and not name.startswith("topology_levels."):
            continue
        for (value,) in struct.iter_unpack("<d", view):
            if not math.isfinite(value):
                raise SceneBundleError(
                    "scene_integrity_error",
                    f"scene float buffer {name!r} contains a non-finite value",
                )
        if name.startswith("topology_levels."):
            values = [value for (value,) in struct.iter_unpack("<d", view)]
            if len(values) != len(set(values)):
                raise SceneBundleError(
                    "scene_integrity_error",
                    f"scene topology buffer {name!r} contains duplicate exact levels",
                )


def _verify_value_extents(
    manifest: SceneBundleManifest,
    buffers: Mapping[str, memoryview],
) -> None:
    coordinates = struct.iter_unpack("<ddd", buffers["points"])
    first = next(coordinates)
    minima = list(first)
    maxima = list(first)
    for row in coordinates:
        for index, value in enumerate(row):
            minima[index] = min(minima[index], value)
            maxima[index] = max(maxima[index], value)
    expected = {role: (minima[index], maxima[index]) for index, role in enumerate(("x", "y", "z"))}
    if "scalars" in buffers:
        scalar_values = (value for (value,) in struct.iter_unpack("<d", buffers["scalars"]))
        first_scalar = next(scalar_values)
        scalar_minimum = first_scalar
        scalar_maximum = first_scalar
        for value in scalar_values:
            scalar_minimum = min(scalar_minimum, value)
            scalar_maximum = max(scalar_maximum, value)
        expected["scalar"] = (scalar_minimum, scalar_maximum)
    for extent in manifest.scientific_payload.value_extents:
        if (extent.minimum, extent.maximum) != expected[extent.role]:
            raise SceneBundleError(
                "scene_integrity_error",
                f"scene value extent {extent.role!r} disagrees with binary values",
            )


def _verify_point_identity_buffers(
    manifest: SceneBundleManifest,
    buffers: Mapping[str, memoryview],
) -> None:
    for name in ("row_positions", "stable_ids"):
        values = [value for (value,) in struct.iter_unpack("<Q", buffers[name])]
        if len(values) != len(set(values)):
            raise SceneBundleError(
                "scene_integrity_error",
                f"scene point identity buffer {name!r} contains duplicates",
            )
        if name == "row_positions" and any(
            value >= manifest.scientific_payload.source_row_count for value in values
        ):
            raise SceneBundleError(
                "scene_integrity_error",
                "scene row position is outside the declared source table",
            )


def _verify_connectivity(
    manifest: SceneBundleManifest,
    buffers: Mapping[str, memoryview],
) -> None:
    edges = list(struct.iter_unpack("<II", buffers["edges"])) if manifest.counts.edges else []
    quads = list(struct.iter_unpack("<IIII", buffers["quads"])) if manifest.counts.quads else []
    point_count = manifest.counts.points
    seen_edges: set[tuple[int, int]] = set()
    for edge in edges:
        if any(index >= point_count for index in edge):
            raise SceneBundleError(
                "scene_integrity_error",
                "scene edge contains a globally invalid point index",
            )
        if edge[0] == edge[1]:
            raise SceneBundleError(
                "scene_integrity_error",
                "scene edge repeats one point index",
            )
        edge_identity = tuple(sorted(edge))
        if edge_identity in seen_edges:
            raise SceneBundleError("scene_integrity_error", "scene edges contain duplicates")
        seen_edges.add(edge_identity)
    seen_quads: set[frozenset[int]] = set()
    for quad in quads:
        if any(index >= point_count for index in quad):
            raise SceneBundleError(
                "scene_integrity_error",
                "scene quad contains a globally invalid point index",
            )
        quad_identity = frozenset(quad)
        if len(quad_identity) != 4:
            raise SceneBundleError(
                "scene_integrity_error",
                "scene quad contains repeated point indices",
            )
        if quad_identity in seen_quads:
            raise SceneBundleError("scene_integrity_error", "scene quads contain duplicates")
        seen_quads.add(quad_identity)

    for block in manifest.blocks:
        point_stop = block.point_start + block.point_count
        for edge in edges[block.edge_start : block.edge_start + block.edge_count]:
            if any(index < block.point_start or index >= point_stop for index in edge):
                raise SceneBundleError(
                    "scene_integrity_error",
                    f"scene edge crosses declared block {block.index}",
                )
        for quad in quads[block.quad_start : block.quad_start + block.quad_count]:
            if any(index < block.point_start or index >= point_stop for index in quad):
                raise SceneBundleError(
                    "scene_integrity_error",
                    f"scene quad crosses declared block {block.index}",
                )


def _align_to_eight(value: int) -> int:
    return (value + 7) & ~7
