from __future__ import annotations

import hashlib
import json
import stat
import struct
import subprocess
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from carnopy.app import scene_leases as scene_leases_module
from carnopy.app.scene_bundle import (
    SCENE_BINARY_HEADER,
    SCENE_BINARY_MAGIC,
    SCENE_BINARY_NAME,
    SCENE_ENDIAN_MARKER,
    SCENE_MANIFEST_NAME,
    scene_content_id,
    verify_scene_bundle,
)
from carnopy.app.scene_contracts import SceneRequest
from carnopy.app.scene_integrity import SceneBundleError, canonical_scene_json_bytes
from carnopy.app.scene_leases import (
    SCENE_LEASE_NAME,
    SceneLease,
    acquire_scene_session,
    cleanup_abandoned_scene_leases,
    create_scene_lease,
    remove_scene_lease,
    validate_scene_lease,
)
from carnopy.app.workspace import initialize_workspace

Manifest = dict[str, Any]
ManifestMutation = Callable[[Manifest], None]
BinaryMutation = Callable[[Manifest, bytearray], None]


@contextmanager
def _lease(tmp_path: Path) -> Iterator[SceneLease]:
    workspace = initialize_workspace(tmp_path / "workspace")
    session = acquire_scene_session(workspace.root)
    try:
        yield create_scene_lease(session)
    finally:
        session.close()


def _pack(format_string: str, rows: list[tuple[int | float, ...]]) -> bytes:
    return b"".join(struct.pack(format_string, *row) for row in rows)


def _valid_buffers() -> list[tuple[str, str, tuple[int, ...], bytes]]:
    points = [
        (0.0, 0.0, 0.0),
        (1.0, 0.0, 0.0),
        (1.0, 1.0, 0.0),
        (0.0, 1.0, 0.0),
        (10.0, 0.0, 0.0),
        (11.0, 0.0, 0.0),
        (11.0, 1.0, 0.0),
        (10.0, 1.0, 0.0),
    ]
    edges = [
        (0, 1),
        (1, 2),
        (2, 3),
        (3, 0),
        (4, 5),
        (5, 6),
        (6, 7),
        (7, 4),
    ]
    quads = [(0, 1, 2, 3), (4, 5, 6, 7)]
    return [
        ("points", "float64", (8, 3), _pack("<ddd", points)),
        ("scalars", "float64", (8,), _pack("<d", [(float(i),) for i in range(8)])),
        ("row_positions", "uint64", (8,), _pack("<Q", [(i,) for i in range(8)])),
        ("stable_ids", "uint64", (8,), _pack("<Q", [(100 + i,) for i in range(8)])),
        ("edges", "uint32", (8, 2), _pack("<II", edges)),
        ("quads", "uint32", (2, 4), _pack("<IIII", quads)),
        ("topology_levels.0", "float64", (2,), _pack("<d", [(0.0,), (1.0,)])),
        ("topology_levels.1", "float64", (2,), _pack("<d", [(0.0,), (1.0,)])),
    ]


def _numeric_field(
    field_id: str,
    *,
    minimum: float,
    maximum: float,
    classification: str = "source_coordinate",
    axis_eligible: bool = True,
    scalar_eligible: bool = True,
) -> Manifest:
    return {
        "axis_eligible": axis_eligible,
        "classification": classification,
        "column": field_id,
        "distinct_values": [],
        "dtype": "float64",
        "field_id": field_id,
        "filter_kind": "numeric_range",
        "finite_count": 8,
        "ineligible_reason": "",
        "kind": "numeric",
        "label": field_id.upper(),
        "maximum": maximum,
        "minimum": minimum,
        "missing_count": 0,
        "origin": "table",
        "positive_domain": minimum > 0.0,
        "scalar_eligible": scalar_eligible,
        "source_row_count": 8,
        "source_valid_count": 8,
        "unit": "m",
        "unit_status": "canonical",
        "value_count": 8,
        "varying": minimum != maximum,
    }


def _valid_scientific_payload(
    descriptors: list[Manifest],
    blocks: list[Manifest],
) -> Manifest:
    source_root = (Path.cwd() / "fixture-scene-source").resolve()
    binding: Manifest = {
        "controls": [],
        "inspection_revision": "a" * 64,
        "selected_table_id": "dataset",
        "source_kind": "dataset",
        "source_path": str(source_root),
        "tables": [
            {
                "artifact": {
                    "device": 1,
                    "inode": 1,
                    "modified_ns": 1,
                    "path": str(source_root / "dataset.parquet"),
                    "sha256": "b" * 64,
                    "size": 1,
                },
                "label": "Dataset",
                "metadata": None,
                "source_format": "parquet",
                "table_id": "dataset",
            }
        ],
    }
    request: Manifest = {
        "binding": binding,
        "filters": [],
        "scalar_field": "scalar",
        "scene_request_schema_version": 1,
        "x_field": "x",
        "y_field": "y",
        "z_field": "z",
    }
    topology_descriptors = {
        descriptor["name"]: descriptor
        for descriptor in descriptors
        if str(descriptor["name"]).startswith("topology_levels.")
    }
    return {
        "blocks": [
            {
                "context": block["context"],
                "duplicate_topology_location_count": 0,
                "excluded_row_count": 0,
                "gap_location_count": 0,
                "index": index,
                "missing_intermediate_level_count": 0,
                "omitted_collinear_count": 0,
                "omitted_missing_corner_count": 0,
                "omitted_repeated_vertex_count": 0,
                "omitted_zero_length_edge_count": 0,
                "retained_point_count": 4,
                "topology_dimension": 2,
                "topology_location_count": 4,
                "topology_reason": "",
                "topology_reason_code": "",
                "topology_status": "exact",
                "unlocated_point_count": 0,
            }
            for index, block in enumerate(blocks)
        ],
        "capabilities": [
            {"available": True, "blockers": [], "representation": representation}
            for representation in ("points", "wireframe", "surface")
        ],
        "excluded_row_count": 0,
        "fields": [
            _numeric_field("x", minimum=0.0, maximum=11.0),
            _numeric_field("y", minimum=0.0, maximum=1.0),
            _numeric_field("z", minimum=0.0, maximum=0.0),
            _numeric_field(
                "scalar",
                minimum=0.0,
                maximum=7.0,
                classification="emitted_property",
                axis_eligible=False,
            ),
        ],
        "orphan_exclusions": [],
        "point_exclusions": [],
        "primitive_omissions": [],
        "request": request,
        "retained_row_count": 8,
        "scene_profile_schema_version": 1,
        "scientific_payload_schema_version": 1,
        "source_row_count": 8,
        "stable_id_field": "case_id",
        "topology": {
            "axes": [
                {
                    "field_id": field_id,
                    "index": index,
                    "level_count": 2,
                    "levels_sha256": topology_descriptors[f"topology_levels.{index}"]["sha256"],
                    "source_column": field_id,
                    "unit": "m",
                }
                for index, field_id in enumerate(("x", "y"))
            ],
            "context_fields": ["phase"],
            "reason": "",
            "reason_code": "",
            "status": "exact",
        },
        "value_extents": [
            {
                "field_id": field_id,
                "logarithmic_available": minimum > 0.0,
                "maximum": maximum,
                "minimum": minimum,
                "role": role,
            }
            for role, field_id, minimum, maximum in (
                ("x", "x", 0.0, 11.0),
                ("y", "y", 0.0, 1.0),
                ("z", "z", 0.0, 0.0),
                ("scalar", "scalar", 0.0, 7.0),
            )
        ],
    }


def _valid_bundle() -> tuple[Manifest, bytearray]:
    binary = bytearray(SCENE_BINARY_HEADER.pack(SCENE_BINARY_MAGIC, 1, 1, SCENE_ENDIAN_MARKER))
    descriptors: list[Manifest] = []
    for name, dtype, shape, payload in _valid_buffers():
        offset = (len(binary) + 7) & ~7
        binary.extend(b"\0" * (offset - len(binary)))
        binary.extend(payload)
        descriptors.append(
            {
                "byte_length": len(payload),
                "dtype": dtype,
                "name": name,
                "offset": offset,
                "sha256": hashlib.sha256(payload).hexdigest(),
                "shape": list(shape),
            }
        )
    blocks: list[Manifest] = [
        {
            "context": {
                "backend_model": "HEOS",
                "fluid": "Water",
                "partition": None,
                "phase": phase,
                "saturation_endpoint": None,
                "scenario": None,
                "source_artifact": f"dataset-{suffix}",
                "source_run_id": f"run-{suffix}",
            },
            "edge_count": 4,
            "edge_start": index * 4,
            "index": index,
            "point_count": 4,
            "point_start": index * 4,
            "quad_count": 1,
            "quad_start": index,
        }
        for index, (phase, suffix) in enumerate((("liquid", "a"), ("gas", "b")))
    ]
    scientific_payload = _valid_scientific_payload(descriptors, blocks)
    request = SceneRequest.model_validate(scientific_payload["request"])
    manifest: Manifest = {
        "binary": {
            "byte_order": "little",
            "header_version": 1,
            "name": SCENE_BINARY_NAME,
            "sha256": hashlib.sha256(binary).hexdigest(),
            "size": len(binary),
        },
        "blocks": blocks,
        "buffers": descriptors,
        "counts": {"edges": 8, "points": 8, "quads": 2},
        "request_id": request.request_id,
        "scene_schema_version": 1,
        "scientific_payload": scientific_payload,
    }
    _refresh_content_id(manifest)
    return manifest, binary


def _refresh_content_id(manifest: Manifest) -> None:
    manifest.pop("content_id", None)
    manifest["content_id"] = scene_content_id(manifest)


def _refresh_binary_identity(manifest: Manifest, binary: bytearray) -> None:
    manifest["binary"]["sha256"] = hashlib.sha256(binary).hexdigest()
    manifest["binary"]["size"] = len(binary)
    _refresh_content_id(manifest)


def _replace_buffer(
    manifest: Manifest,
    binary: bytearray,
    name: str,
    payload: bytes,
) -> None:
    descriptor = next(item for item in manifest["buffers"] if item["name"] == name)
    assert len(payload) == descriptor["byte_length"]
    start = descriptor["offset"]
    binary[start : start + len(payload)] = payload
    descriptor["sha256"] = hashlib.sha256(payload).hexdigest()
    if name.startswith("topology_levels."):
        axis_index = int(name.rsplit(".", 1)[1])
        manifest["scientific_payload"]["topology"]["axes"][axis_index]["levels_sha256"] = (
            descriptor["sha256"]
        )
    _refresh_binary_identity(manifest, binary)


def _write_bundle(
    lease: SceneLease,
    *,
    manifest_mutation: ManifestMutation | None = None,
    binary_mutation: BinaryMutation | None = None,
    canonical_manifest: bool = True,
) -> tuple[Manifest, bytearray]:
    manifest, binary = _valid_bundle()
    if binary_mutation is not None:
        binary_mutation(manifest, binary)
    if manifest_mutation is not None:
        manifest_mutation(manifest)
    manifest_bytes = canonical_scene_json_bytes(manifest)
    if not canonical_manifest:
        manifest_bytes = json.dumps(manifest, indent=2, sort_keys=False).encode("utf-8")
    (lease.path / SCENE_BINARY_NAME).write_bytes(binary)
    (lease.path / SCENE_MANIFEST_NAME).write_bytes(manifest_bytes)
    return manifest, binary


def test_binary_header_contract_is_exactly_sixteen_little_endian_bytes() -> None:
    assert SCENE_BINARY_HEADER.format == "<8sHHI"
    assert SCENE_BINARY_HEADER.size == 16
    assert (
        SCENE_BINARY_HEADER.pack(
            SCENE_BINARY_MAGIC,
            1,
            1,
            SCENE_ENDIAN_MARKER,
        )
        == b"CARN3D\0\0\x01\0\x01\0\x04\x03\x02\x01"
    )


def test_parent_creates_canonical_uuid_lease_and_worker_revalidates_it(
    tmp_path: Path,
) -> None:
    workspace = initialize_workspace(tmp_path / "workspace")
    session = acquire_scene_session(workspace.root)
    try:
        lease = create_scene_lease(session)

        assert lease.path.parent == workspace.private_directory / "scene-leases"
        assert len(lease.lease_id) == 32
        record_path = lease.path / SCENE_LEASE_NAME
        record = json.loads(record_path.read_text(encoding="utf-8"))
        assert record == {
            "device": lease.device,
            "inode": lease.inode,
            "lease_id": lease.lease_id,
            "scene_lease_schema_version": 1,
            "session_id": session.session_id,
        }
        assert record_path.read_bytes() == canonical_scene_json_bytes(record)
        assert stat.S_IMODE(record_path.stat().st_mode) == 0o600
        assert validate_scene_lease(workspace.root, lease.worker_payload()) == lease
    finally:
        session.close()


def test_complete_handcrafted_bundle_verifies_without_modification(tmp_path: Path) -> None:
    with _lease(tmp_path) as lease:
        manifest, binary = _write_bundle(lease)

        verified = verify_scene_bundle(lease)

        assert verified.manifest.content_id == manifest["content_id"]
        assert verified.manifest.counts.points == 8
        assert verified.binary_size == len(binary)
        assert verified.manifest_size == (lease.path / SCENE_MANIFEST_NAME).stat().st_size


def test_points_only_bundle_may_omit_scalar_connectivity_and_topology_buffers(
    tmp_path: Path,
) -> None:
    with _lease(tmp_path) as lease:
        manifest, _unused_binary = _valid_bundle()
        binary = bytearray(SCENE_BINARY_HEADER.pack(SCENE_BINARY_MAGIC, 1, 1, SCENE_ENDIAN_MARKER))
        descriptors: list[Manifest] = []
        retained_names = {"points", "row_positions", "stable_ids"}
        for name, dtype, shape, payload in _valid_buffers():
            if name not in retained_names:
                continue
            offset = (len(binary) + 7) & ~7
            binary.extend(b"\0" * (offset - len(binary)))
            binary.extend(payload)
            descriptors.append(
                {
                    "byte_length": len(payload),
                    "dtype": dtype,
                    "name": name,
                    "offset": offset,
                    "sha256": hashlib.sha256(payload).hexdigest(),
                    "shape": list(shape),
                }
            )
        manifest["buffers"] = descriptors
        manifest["counts"] = {"edges": 0, "points": 8, "quads": 0}
        for block in manifest["blocks"]:
            block["edge_count"] = 0
            block["edge_start"] = 0
            block["quad_count"] = 0
            block["quad_start"] = 0
        scientific = manifest["scientific_payload"]
        scientific["request"]["scalar_field"] = None
        scientific["value_extents"] = scientific["value_extents"][:3]
        scientific["topology"] = {
            "axes": [],
            "context_fields": [],
            "reason": "fixture topology is intentionally unavailable",
            "reason_code": "topology_unavailable",
            "status": "unavailable",
        }
        for block in scientific["blocks"]:
            block["topology_dimension"] = None
            block["topology_location_count"] = 0
            block["topology_reason"] = "fixture topology is intentionally unavailable"
            block["topology_reason_code"] = "topology_unavailable"
            block["topology_status"] = "unavailable"
        scientific["capabilities"] = [
            {"available": True, "blockers": [], "representation": "points"},
            {
                "available": False,
                "blockers": [
                    {
                        "block_index": index,
                        "code": "topology_unavailable",
                        "message": f"Block {index} has unavailable fixture topology.",
                    }
                    for index in range(2)
                ],
                "representation": "wireframe",
            },
            {
                "available": False,
                "blockers": [
                    {
                        "block_index": index,
                        "code": "topology_unavailable",
                        "message": f"Block {index} has unavailable fixture topology.",
                    }
                    for index in range(2)
                ],
                "representation": "surface",
            },
        ]
        manifest["request_id"] = SceneRequest.model_validate(scientific["request"]).request_id
        _refresh_binary_identity(manifest, binary)
        (lease.path / SCENE_BINARY_NAME).write_bytes(binary)
        (lease.path / SCENE_MANIFEST_NAME).write_bytes(canonical_scene_json_bytes(manifest))

        verified = verify_scene_bundle(lease)

        assert tuple(buffer.name for buffer in verified.manifest.buffers) == (
            "points",
            "row_positions",
            "stable_ids",
        )
        assert verified.manifest.counts.edges == 0
        assert verified.manifest.counts.quads == 0


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda value: value.__setitem__("scene_schema_version", 2), "unsupported.*schema"),
        (lambda value: value.__setitem__("scene_schema_version", True), "unsupported.*schema"),
    ],
)
def test_manifest_rejects_unsupported_schema_versions(
    tmp_path: Path,
    mutation: ManifestMutation,
    message: str,
) -> None:
    with _lease(tmp_path) as lease:

        def mutate(manifest: Manifest) -> None:
            mutation(manifest)
            _refresh_content_id(manifest)

        _write_bundle(lease, manifest_mutation=mutate)

        with pytest.raises(SceneBundleError, match=message):
            verify_scene_bundle(lease)


@pytest.mark.parametrize(
    ("header", "message"),
    [
        ((b"NOT3D\0\0\0", 1, 1, SCENE_ENDIAN_MARKER), "magic is incorrect"),
        ((SCENE_BINARY_MAGIC, 2, 1, SCENE_ENDIAN_MARKER), "unsupported.*header version"),
        ((SCENE_BINARY_MAGIC, 1, 2, SCENE_ENDIAN_MARKER), "versions disagree"),
        ((SCENE_BINARY_MAGIC, 1, 1, 0x04030201), "endianness marker is incorrect"),
    ],
)
def test_binary_rejects_magic_versions_schema_disagreement_and_endianness(
    tmp_path: Path,
    header: tuple[bytes, int, int, int],
    message: str,
) -> None:
    with _lease(tmp_path) as lease:

        def mutate(manifest: Manifest, binary: bytearray) -> None:
            binary[: SCENE_BINARY_HEADER.size] = SCENE_BINARY_HEADER.pack(*header)
            _refresh_binary_identity(manifest, binary)

        _write_bundle(lease, binary_mutation=mutate)

        with pytest.raises(SceneBundleError, match=message):
            verify_scene_bundle(lease)


def test_manifest_must_be_canonical_finite_unique_key_json(tmp_path: Path) -> None:
    with _lease(tmp_path) as lease:
        _write_bundle(lease, canonical_manifest=False)
        with pytest.raises(SceneBundleError, match="not canonical JSON"):
            verify_scene_bundle(lease)

    with _lease(tmp_path / "duplicate") as lease:
        manifest, binary = _valid_bundle()
        canonical = canonical_scene_json_bytes(manifest)
        duplicated = canonical.replace(
            b'{"binary":',
            b'{"request_id":"scene-' + b"1" * 64 + b'","binary":',
            1,
        )
        (lease.path / SCENE_BINARY_NAME).write_bytes(binary)
        (lease.path / SCENE_MANIFEST_NAME).write_bytes(duplicated)
        with pytest.raises(SceneBundleError, match="valid finite UTF-8 JSON"):
            verify_scene_bundle(lease)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda value: value["buffers"][0].__setitem__("offset", 17),
            "8-byte aligned",
        ),
        (
            lambda value: value["buffers"][0].__setitem__("offset", 8),
            "greater than or equal to 16",
        ),
        (
            lambda value: value["buffers"][1].__setitem__("offset", value["buffers"][0]["offset"]),
            "overlaps or is out of order",
        ),
        (
            lambda value: value["buffers"].insert(1, dict(value["buffers"][0])),
            "missing, duplicated, unknown, or outside canonical order",
        ),
        (
            lambda value: value["buffers"].__setitem__(
                slice(0, 2), list(reversed(value["buffers"][:2]))
            ),
            "canonical order",
        ),
        (
            lambda value: value["buffers"][-1].__setitem__("offset", value["binary"]["size"] + 8),
            "binary size disagrees with its final buffer boundary",
        ),
        (
            lambda value: value["buffers"][0].__setitem__("dtype", "uint64"),
            "wrong dtype",
        ),
        (
            lambda value: value["buffers"][0].__setitem__("shape", [24]),
            "wrong shape",
        ),
        (
            lambda value: value["buffers"][0].__setitem__("shape", [8, 2]),
            "byte length.*does not match",
        ),
        (
            lambda value: value["buffers"][0].__setitem__("byte_length", 8),
            "byte length.*does not match",
        ),
        (
            lambda value: value["counts"].__setitem__("points", 7),
            "wrong shape",
        ),
        (
            lambda value: value["counts"].__setitem__("edges", 7),
            "wrong shape",
        ),
        (
            lambda value: value["counts"].__setitem__("quads", 1),
            "wrong shape",
        ),
    ],
)
def test_manifest_rejects_invalid_buffer_descriptors_and_counts(
    tmp_path: Path,
    mutation: ManifestMutation,
    message: str,
) -> None:
    with _lease(tmp_path) as lease:

        def mutate(manifest: Manifest) -> None:
            mutation(manifest)
            _refresh_content_id(manifest)

        _write_bundle(lease, manifest_mutation=mutate)

        with pytest.raises(SceneBundleError, match=message):
            verify_scene_bundle(lease)


def test_aligned_zero_padding_is_accepted_and_nonzero_padding_is_rejected(
    tmp_path: Path,
) -> None:
    with _lease(tmp_path) as lease:

        def add_padding(manifest: Manifest, binary: bytearray, padding: bytes) -> None:
            insertion = manifest["buffers"][1]["offset"]
            binary[insertion:insertion] = padding
            for descriptor in manifest["buffers"][1:]:
                descriptor["offset"] += 8
            _refresh_binary_identity(manifest, binary)

        def add_zero_padding(manifest: Manifest, binary: bytearray) -> None:
            add_padding(manifest, binary, b"\0" * 8)

        _write_bundle(lease, binary_mutation=add_zero_padding)

        assert verify_scene_bundle(lease).manifest.counts.points == 8

    with _lease(tmp_path / "nonzero") as lease:

        def add_nonzero_padding(manifest: Manifest, binary: bytearray) -> None:
            add_padding(manifest, binary, b"\x01" + b"\0" * 7)

        _write_bundle(lease, binary_mutation=add_nonzero_padding)

        with pytest.raises(SceneBundleError, match=r"padding.*not zero"):
            verify_scene_bundle(lease)


def test_buffer_and_whole_binary_hashes_are_both_enforced(tmp_path: Path) -> None:
    with _lease(tmp_path) as lease:
        manifest, binary = _write_bundle(lease)
        points = next(item for item in manifest["buffers"] if item["name"] == "points")
        binary[points["offset"]] ^= 1
        manifest["binary"]["sha256"] = hashlib.sha256(binary).hexdigest()
        _refresh_content_id(manifest)
        (lease.path / SCENE_BINARY_NAME).write_bytes(binary)
        (lease.path / SCENE_MANIFEST_NAME).write_bytes(canonical_scene_json_bytes(manifest))
        with pytest.raises(SceneBundleError, match="buffer 'points' hash"):
            verify_scene_bundle(lease)

    with _lease(tmp_path / "whole") as lease:
        manifest, binary = _write_bundle(lease)
        manifest["binary"]["sha256"] = "0" * 64
        _refresh_content_id(manifest)
        (lease.path / SCENE_MANIFEST_NAME).write_bytes(canonical_scene_json_bytes(manifest))
        with pytest.raises(SceneBundleError, match="binary hash"):
            verify_scene_bundle(lease)


@pytest.mark.parametrize(
    ("buffer_name", "payload", "message"),
    [
        (
            "edges",
            _pack(
                "<II",
                [(0, 8), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4)],
            ),
            "globally invalid",
        ),
        (
            "quads",
            _pack("<IIII", [(0, 1, 2, 8), (4, 5, 6, 7)]),
            "globally invalid",
        ),
        (
            "edges",
            _pack(
                "<II",
                [(0, 4), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4)],
            ),
            "edge crosses declared block 0",
        ),
        (
            "quads",
            _pack("<IIII", [(0, 1, 2, 4), (4, 5, 6, 7)]),
            "quad crosses declared block 0",
        ),
        (
            "edges",
            _pack(
                "<II",
                [(0, 0), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4)],
            ),
            "edge repeats one point index",
        ),
        (
            "edges",
            _pack(
                "<II",
                [(0, 1), (1, 0), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4)],
            ),
            "edges contain duplicates",
        ),
        (
            "quads",
            _pack("<IIII", [(0, 1, 2, 2), (4, 5, 6, 7)]),
            "quad contains repeated point indices",
        ),
        (
            "quads",
            _pack("<IIII", [(0, 1, 2, 3), (3, 2, 1, 0)]),
            "quads contain duplicates",
        ),
    ],
)
def test_connectivity_rejects_invalid_repeated_duplicate_and_cross_block_indices(
    tmp_path: Path,
    buffer_name: str,
    payload: bytes,
    message: str,
) -> None:
    with _lease(tmp_path) as lease:

        def mutate(manifest: Manifest, binary: bytearray) -> None:
            _replace_buffer(manifest, binary, buffer_name, payload)

        _write_bundle(lease, binary_mutation=mutate)

        with pytest.raises(SceneBundleError, match=message):
            verify_scene_bundle(lease)


@pytest.mark.parametrize(
    ("name", "payload", "message"),
    [
        (
            "row_positions",
            _pack("<Q", [(0,), (0,), (2,), (3,), (4,), (5,), (6,), (7,)]),
            "identity buffer.*duplicates",
        ),
        (
            "row_positions",
            _pack("<Q", [(0,), (1,), (2,), (3,), (4,), (5,), (6,), (8,)]),
            "row position is outside",
        ),
        (
            "stable_ids",
            _pack("<Q", [(100,), (100,), (102,), (103,), (104,), (105,), (106,), (107,)]),
            "identity buffer.*duplicates",
        ),
        (
            "topology_levels.0",
            _pack("<d", [(0.0,), (0.0,)]),
            "duplicate exact levels",
        ),
        (
            "scalars",
            _pack("<d", [(float("nan"),)] + [(float(i),) for i in range(1, 8)]),
            "non-finite value",
        ),
    ],
)
def test_identity_and_float_buffers_reject_ambiguous_or_nonfinite_values(
    tmp_path: Path,
    name: str,
    payload: bytes,
    message: str,
) -> None:
    with _lease(tmp_path) as lease:

        def mutate(manifest: Manifest, binary: bytearray) -> None:
            _replace_buffer(manifest, binary, name, payload)

        _write_bundle(lease, binary_mutation=mutate)

        with pytest.raises(SceneBundleError, match=message):
            verify_scene_bundle(lease)


def test_manifest_content_identity_and_parent_lease_identity_are_enforced(
    tmp_path: Path,
) -> None:
    with _lease(tmp_path) as lease:
        manifest, _binary = _write_bundle(lease)
        manifest["scientific_payload"]["fields"][0]["label"] = "Tampered X"
        (lease.path / SCENE_MANIFEST_NAME).write_bytes(canonical_scene_json_bytes(manifest))
        with pytest.raises(SceneBundleError, match="content identity"):
            verify_scene_bundle(lease)

    with _lease(tmp_path / "lease") as lease:
        _write_bundle(lease)
        record_path = lease.path / SCENE_LEASE_NAME
        record = json.loads(record_path.read_text(encoding="utf-8"))
        record["inode"] += 1
        record_path.write_bytes(canonical_scene_json_bytes(record))
        with pytest.raises(SceneBundleError, match="parent-held identity"):
            verify_scene_bundle(lease)


def test_explicit_removal_rejects_unrecognized_children(tmp_path: Path) -> None:
    with _lease(tmp_path) as lease:
        (lease.path / "unexpected.txt").write_text("preserve me", encoding="utf-8")

        with pytest.raises(SceneBundleError, match="unrecognized entry"):
            remove_scene_lease(lease)

        assert lease.path.is_dir()
        assert (lease.path / "unexpected.txt").read_text(encoding="utf-8") == "preserve me"


def test_cleanup_removes_abandoned_recognized_lease(tmp_path: Path) -> None:
    workspace = initialize_workspace(tmp_path / "workspace")
    session = acquire_scene_session(workspace.root)
    lease = create_scene_lease(session)
    session.close()

    report = cleanup_abandoned_scene_leases(workspace.root)

    assert report.removed == (lease.path,)
    assert report.preserved == ()
    assert not lease.path.exists()


def test_uuid_creation_collision_never_removes_the_existing_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = initialize_workspace(tmp_path / "workspace")
    session = acquire_scene_session(workspace.root)
    fixed_id = "c" * 32
    root = workspace.private_directory / "scene-leases"
    root.mkdir()
    existing = root / fixed_id
    existing.mkdir()
    sentinel = existing / "sentinel.txt"
    sentinel.write_text("belongs to someone else", encoding="utf-8")
    monkeypatch.setattr(scene_leases_module, "uuid4", lambda: UUID(hex=fixed_id))
    try:
        with pytest.raises(FileExistsError):
            create_scene_lease(session)

        assert sentinel.read_text(encoding="utf-8") == "belongs to someone else"
    finally:
        session.close()


def test_cleanup_preserves_lease_owned_by_current_live_session(tmp_path: Path) -> None:
    workspace = initialize_workspace(tmp_path / "workspace")
    session = acquire_scene_session(workspace.root)
    lease = create_scene_lease(session)
    try:
        report = cleanup_abandoned_scene_leases(workspace.root)

        assert report.preserved == (lease.path,)
        assert lease.path.is_dir()
    finally:
        session.close()


def test_cleanup_preserves_lease_when_its_lock_path_is_not_a_private_regular_file(
    tmp_path: Path,
) -> None:
    workspace = initialize_workspace(tmp_path / "workspace")
    session = acquire_scene_session(workspace.root)
    lease = create_scene_lease(session)
    lock_path = session.lock_path
    session.close()
    target = tmp_path / "external-lock-target"
    target.write_text("must not be touched", encoding="utf-8")
    try:
        lock_path.symlink_to(target)
    except OSError:
        pytest.skip("symbolic links are unavailable")

    report = cleanup_abandoned_scene_leases(workspace.root)

    assert report.preserved == (lease.path,)
    assert lease.path.is_dir()
    assert target.read_text(encoding="utf-8") == "must not be touched"


def test_real_process_lock_preserves_then_releases_the_same_valid_lease(
    tmp_path: Path,
) -> None:
    workspace = initialize_workspace(tmp_path / "workspace")
    script = """
import json
import os
import sys
from pathlib import Path
from carnopy.app.scene_leases import acquire_scene_session, create_scene_lease

session = acquire_scene_session(Path(sys.argv[1]))
lease = create_scene_lease(session)
print(json.dumps({"lease_id": lease.lease_id, "path": str(lease.path)}), flush=True)
sys.stdin.readline()
os._exit(0)
"""
    process = subprocess.Popen(
        [sys.executable, "-c", script, str(workspace.root)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert process.stdout is not None
    assert process.stdin is not None
    try:
        child = json.loads(process.stdout.readline())
        lease_path = Path(child["path"])

        live_report = cleanup_abandoned_scene_leases(workspace.root)

        assert live_report.preserved == (lease_path,)
        assert lease_path.is_dir()

        process.stdin.write("release\n")
        process.stdin.flush()
        return_code = process.wait(timeout=10)
        assert return_code == 0, process.stderr.read() if process.stderr is not None else ""

        abandoned_report = cleanup_abandoned_scene_leases(workspace.root)

        assert abandoned_report.removed == (lease_path,)
        assert not lease_path.exists()
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=10)


def test_cleanup_preserves_malformed_unrecognized_replaced_and_symlinked_entries(
    tmp_path: Path,
) -> None:
    workspace = initialize_workspace(tmp_path / "workspace")
    session = acquire_scene_session(workspace.root)
    replaced = create_scene_lease(session)
    session.close()
    root = replaced.path.parent

    moved = replaced.path.with_name(f"{replaced.lease_id}-moved")
    replaced.path.rename(moved)
    replaced.path.mkdir()
    (replaced.path / SCENE_LEASE_NAME).write_bytes((moved / SCENE_LEASE_NAME).read_bytes())

    malformed = root / ("a" * 32)
    malformed.mkdir()
    (malformed / SCENE_LEASE_NAME).write_text("not-json\n", encoding="utf-8")

    external = tmp_path / "external"
    external.mkdir()
    symlink = root / ("b" * 32)
    try:
        symlink.symlink_to(external, target_is_directory=True)
    except OSError:
        pytest.skip("symbolic links are unavailable")

    unrecognized = root / "leave-me-alone"
    unrecognized.mkdir()

    report = cleanup_abandoned_scene_leases(workspace.root)

    assert set(report.preserved) == {replaced.path, moved, malformed, symlink, unrecognized}
    assert report.removed == ()
    assert all(path.exists() or path.is_symlink() for path in report.preserved)


def test_scene_bundle_import_excludes_heavy_scientific_and_rendering_modules() -> None:
    script = """
import sys
from carnopy.app import scene_bundle

blocked = ("CoolProp", "numpy", "pandas", "pyarrow", "matplotlib", "vtk")
loaded = sorted(name for name in blocked if name in sys.modules)
raise SystemExit("heavy imports: " + ", ".join(loaded) if loaded else 0)
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
