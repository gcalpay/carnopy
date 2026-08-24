from __future__ import annotations

import hashlib
import math
import re
import struct
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Final, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
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
    scientific_payload: dict[StrictStr, Any]

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
    _verify_point_identity_buffers(buffers)
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


def _verify_point_identity_buffers(buffers: Mapping[str, memoryview]) -> None:
    for name in ("row_positions", "stable_ids"):
        values = [value for (value,) in struct.iter_unpack("<Q", buffers[name])]
        if len(values) != len(set(values)):
            raise SceneBundleError(
                "scene_integrity_error",
                f"scene point identity buffer {name!r} contains duplicates",
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
