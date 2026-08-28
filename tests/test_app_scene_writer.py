from __future__ import annotations

import hashlib
import json
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from carnopy.api import generate_dataset
from carnopy.app import scene_contracts, scene_writer
from carnopy.app.scene_assembly import SceneGeometryAssembly, build_scene_geometry
from carnopy.app.scene_bundle import (
    SceneManifestValueExtent,
    scene_content_id,
    verify_scene_bundle,
)
from carnopy.app.scene_contracts import (
    NumericRangeFilter,
    SceneContractError,
    SceneProfile,
    SceneRequest,
)
from carnopy.app.scene_integrity import (
    SCENE_BINARY_NAME,
    SCENE_MANIFEST_NAME,
    SceneBundleError,
    canonical_scene_json_bytes,
)
from carnopy.app.scene_leases import (
    SceneLease,
    acquire_scene_session,
    create_scene_lease,
)
from carnopy.app.scene_profiles import profile_scene
from carnopy.app.scene_writer import prepare_scene_bundle, write_scene_bundle
from carnopy.app.source_inspection import inspect_for_app
from carnopy.app.workspace import initialize_workspace


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def exact_scene_assembly(tmp_path_factory: pytest.TempPathFactory) -> SceneGeometryAssembly:
    root = tmp_path_factory.mktemp("scene-writer-source")
    config = root / "scene-writer.yaml"
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
    run = generate_dataset(config, output_root=root / "runs").output_directory
    dataset = run / "dataset.parquet"
    base = pd.read_parquet(dataset)
    rows: list[pd.Series] = []
    for _index, row in base.iterrows():
        for phase in ("gas", "liquid"):
            copied = row.copy()
            copied["phase"] = phase
            rows.append(copied)
    frame = pd.DataFrame(rows).reset_index(drop=True)
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
    inspected = inspect_for_app(run)
    assert len(inspected.scene_bindings) == 1
    profile: SceneProfile = profile_scene(inspected.scene_bindings[0])
    request = SceneRequest(
        binding=profile.binding,
        x_field="temperature",
        y_field="pressure",
        z_field="specific_enthalpy",
        scalar_field="mass_density",
    )
    return build_scene_geometry(profile, request)


@contextmanager
def _lease(tmp_path: Path) -> Iterator[SceneLease]:
    workspace = initialize_workspace(tmp_path / "workspace")
    session = acquire_scene_session(workspace.root)
    try:
        yield create_scene_lease(session)
    finally:
        session.close()


def test_manifest_binds_complete_canonical_scientific_evidence(
    exact_scene_assembly: SceneGeometryAssembly,
) -> None:
    assembly = exact_scene_assembly

    prepared = prepare_scene_bundle(assembly)

    manifest = prepared.manifest
    payload = manifest.scientific_payload
    identity_payload = manifest.model_dump(mode="json", exclude={"content_id"})
    assert manifest.request_id == assembly.request.request_id
    assert manifest.content_id == scene_content_id(identity_payload)
    assert payload.request == assembly.request
    assert payload.request.binding == assembly.profile.binding
    assert payload.fields == assembly.profile.fields
    assert payload.stable_id_field == "case_id"
    assert (
        payload.source_row_count,
        payload.retained_row_count,
        payload.excluded_row_count,
    ) == (8, 8, 0)
    assert payload.value_extents == tuple(
        SceneManifestValueExtent(
            role=extent.role,
            field_id=extent.field_id,
            minimum=extent.minimum,
            maximum=extent.maximum,
            logarithmic_available=extent.logarithmic_available,
        )
        for extent in assembly.value_extents
    )
    assert payload.capabilities == assembly.capabilities
    assert payload.point_exclusions == assembly.topology.projection.exclusions
    assert payload.primitive_omissions == assembly.cells.omissions
    assert tuple(axis.field_id for axis in payload.topology.axes) == (
        "temperature",
        "pressure",
    )
    for axis in payload.topology.axes:
        descriptor = next(
            buffer for buffer in manifest.buffers if buffer.name == f"topology_levels.{axis.index}"
        )
        assert axis.level_count == descriptor.shape[0]
        assert axis.levels_sha256 == descriptor.sha256
    assert tuple(block.context for block in payload.blocks) == tuple(
        block.context for block in manifest.blocks
    )
    assert tuple(block.retained_point_count for block in payload.blocks) == (4, 4)
    assert prepared.bundle_bytes == len(prepared.encoding.data) + len(prepared.manifest_bytes)
    assert canonical_scene_json_bytes(manifest.model_dump(mode="json")) == (prepared.manifest_bytes)
    assert "triangles" not in manifest.model_dump(mode="json")


def test_writer_round_trips_through_the_lightweight_verifier(
    exact_scene_assembly: SceneGeometryAssembly,
    tmp_path: Path,
) -> None:
    with _lease(tmp_path) as lease:
        written = write_scene_bundle(lease, exact_scene_assembly)

        verified = verify_scene_bundle(lease)

        assert verified.manifest == written.manifest
        assert verified.binary_size == written.binary_size
        assert verified.manifest_size == written.manifest_size
        assert written.bundle_size == written.binary_size + written.manifest_size
        assert (
            written.binary_path.read_bytes()
            == prepare_scene_bundle(exact_scene_assembly).encoding.data
        )
        assert written.manifest_path.read_bytes() == canonical_scene_json_bytes(
            written.manifest.model_dump(mode="json")
        )
        assert stat.S_IMODE(written.binary_path.stat().st_mode) == 0o600
        assert stat.S_IMODE(written.manifest_path.stat().st_mode) == 0o600


def test_writer_preserves_exact_one_and_zero_dimensional_variants(
    exact_scene_assembly: SceneGeometryAssembly,
    tmp_path: Path,
) -> None:
    profile = exact_scene_assembly.profile
    levels = {axis.field_id: axis.levels for axis in profile.topology.axes}
    temperature_filter = NumericRangeFilter(
        field_id="temperature",
        minimum=levels["temperature"][0],
        maximum=levels["temperature"][0],
    )
    pressure_filter = NumericRangeFilter(
        field_id="pressure",
        minimum=levels["pressure"][0],
        maximum=levels["pressure"][0],
    )
    cases = (
        ((temperature_filter,), 1, 2),
        ((temperature_filter, pressure_filter), 0, 0),
    )
    for index, (filters, expected_dimension, expected_edges) in enumerate(cases):
        request = SceneRequest(
            binding=profile.binding,
            x_field="temperature",
            y_field="pressure",
            z_field="specific_enthalpy",
            filters=filters,
        )
        assembly = build_scene_geometry(profile, request)
        with _lease(tmp_path / str(index)) as lease:
            verified = verify_scene_bundle(write_scene_bundle(lease, assembly).lease)

        assert verified.manifest.counts.edges == expected_edges
        assert verified.manifest.counts.quads == 0
        assert {
            block.topology_dimension for block in verified.manifest.scientific_payload.blocks
        } == {expected_dimension}
        assert "scalars" not in {buffer.name for buffer in verified.manifest.buffers}


def test_repeated_preparation_and_separate_lease_writes_are_byte_identical(
    exact_scene_assembly: SceneGeometryAssembly,
    tmp_path: Path,
) -> None:
    first = prepare_scene_bundle(exact_scene_assembly)
    second = prepare_scene_bundle(exact_scene_assembly)
    assert first == second

    workspace = initialize_workspace(tmp_path / "workspace")
    session = acquire_scene_session(workspace.root)
    try:
        first_lease = create_scene_lease(session)
        second_lease = create_scene_lease(session)
        write_scene_bundle(first_lease, exact_scene_assembly)
        write_scene_bundle(second_lease, exact_scene_assembly)

        assert (first_lease.path / SCENE_BINARY_NAME).read_bytes() == (
            second_lease.path / SCENE_BINARY_NAME
        ).read_bytes()
        assert (first_lease.path / SCENE_MANIFEST_NAME).read_bytes() == (
            second_lease.path / SCENE_MANIFEST_NAME
        ).read_bytes()
    finally:
        session.close()


@pytest.mark.parametrize("existing_name", [SCENE_BINARY_NAME, SCENE_MANIFEST_NAME])
def test_writer_never_replaces_an_existing_bundle_path(
    exact_scene_assembly: SceneGeometryAssembly,
    tmp_path: Path,
    existing_name: str,
) -> None:
    with _lease(tmp_path) as lease:
        existing = lease.path / existing_name
        existing.write_bytes(b"belongs to another attempt")

        with pytest.raises(SceneBundleError, match="will not be replaced") as error:
            write_scene_bundle(lease, exact_scene_assembly)

        assert error.value.code == "scene_write_failed"
        assert existing.read_bytes() == b"belongs to another attempt"
        other_name = (
            SCENE_MANIFEST_NAME if existing_name == SCENE_BINARY_NAME else SCENE_BINARY_NAME
        )
        assert not (lease.path / other_name).exists()


def test_manifest_is_not_created_when_manifest_last_publication_fails(
    exact_scene_assembly: SceneGeometryAssembly,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = prepare_scene_bundle(exact_scene_assembly)
    calls: list[str] = []
    real_write = scene_writer.write_scene_exclusive_regular_file

    def fail_manifest(path: Path, data: bytes, *, label: str) -> None:
        calls.append(label)
        if label == "scene manifest":
            raise SceneBundleError("scene_write_failed", "injected manifest failure")
        real_write(path, data, label=label)

    monkeypatch.setattr(scene_writer, "write_scene_exclusive_regular_file", fail_manifest)
    with _lease(tmp_path) as lease:
        with pytest.raises(SceneBundleError, match="injected manifest failure"):
            write_scene_bundle(lease, exact_scene_assembly)

        assert calls == ["scene binary", "scene manifest"]
        assert (lease.path / SCENE_BINARY_NAME).read_bytes() == prepared.encoding.data
        assert not (lease.path / SCENE_MANIFEST_NAME).exists()


def test_exact_completed_bundle_limit_fails_before_any_scene_file_write(
    exact_scene_assembly: SceneGeometryAssembly,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exact_size = prepare_scene_bundle(exact_scene_assembly).bundle_bytes
    monkeypatch.setattr(scene_contracts, "MAX_SCENE_BUNDLE_BYTES", exact_size - 1)

    with _lease(tmp_path) as lease:
        with pytest.raises(SceneContractError, match="exceeds limit") as error:
            write_scene_bundle(lease, exact_scene_assembly)

        assert error.value.code == "scene_limit_exceeded"
        assert error.value.details == {
            "measure": "bundle_bytes",
            "actual": exact_size,
            "limit": exact_size - 1,
        }
        assert not (lease.path / SCENE_BINARY_NAME).exists()
        assert not (lease.path / SCENE_MANIFEST_NAME).exists()


def test_production_binary_tampering_is_rejected(
    exact_scene_assembly: SceneGeometryAssembly,
    tmp_path: Path,
) -> None:
    with _lease(tmp_path) as lease:
        written = write_scene_bundle(lease, exact_scene_assembly)
        points = next(
            descriptor for descriptor in written.manifest.buffers if descriptor.name == "points"
        )
        tampered = bytearray(written.binary_path.read_bytes())
        tampered[points.offset] ^= 1
        written.binary_path.write_bytes(tampered)

        with pytest.raises(SceneBundleError, match="buffer 'points' hash") as error:
            verify_scene_bundle(lease)

        assert error.value.code == "scene_integrity_error"


def test_recomputed_identity_cannot_hide_contradictory_scientific_evidence(
    exact_scene_assembly: SceneGeometryAssembly,
    tmp_path: Path,
) -> None:
    with _lease(tmp_path) as lease:
        written = write_scene_bundle(lease, exact_scene_assembly)
        raw: dict[str, Any] = json.loads(written.manifest_path.read_text(encoding="utf-8"))
        raw["scientific_payload"]["topology"]["axes"][0]["levels_sha256"] = "0" * 64
        identity_payload = dict(raw)
        identity_payload.pop("content_id")
        raw["content_id"] = scene_content_id(identity_payload)
        written.manifest_path.write_bytes(canonical_scene_json_bytes(raw))

        with pytest.raises(
            SceneBundleError,
            match="topology axis identity disagrees",
        ) as error:
            verify_scene_bundle(lease)

        assert error.value.code == "scene_integrity_error"

        raw = written.manifest.model_dump(mode="json")
        raw["scientific_payload"]["topology"]["axes"][0]["source_column"] = "wrong"
        identity_payload = dict(raw)
        identity_payload.pop("content_id")
        raw["content_id"] = scene_content_id(identity_payload)
        written.manifest_path.write_bytes(canonical_scene_json_bytes(raw))

        with pytest.raises(
            SceneBundleError,
            match="topology axis disagrees with its field",
        ) as error:
            verify_scene_bundle(lease)

        assert error.value.code == "scene_integrity_error"

        raw = written.manifest.model_dump(mode="json")
        raw["scientific_payload"]["blocks"][0]["topology_reason"] = "unexpected"
        identity_payload = dict(raw)
        identity_payload.pop("content_id")
        raw["content_id"] = scene_content_id(identity_payload)
        written.manifest_path.write_bytes(canonical_scene_json_bytes(raw))

        with pytest.raises(
            SceneBundleError,
            match="block topology reason is inconsistent",
        ) as error:
            verify_scene_bundle(lease)

        assert error.value.code == "scene_integrity_error"

        raw = written.manifest.model_dump(mode="json")
        extent = raw["scientific_payload"]["value_extents"][0]
        extent["maximum"] = (extent["minimum"] + extent["maximum"]) / 2.0
        identity_payload = dict(raw)
        identity_payload.pop("content_id")
        raw["content_id"] = scene_content_id(identity_payload)
        written.manifest_path.write_bytes(canonical_scene_json_bytes(raw))

        with pytest.raises(
            SceneBundleError,
            match="value extent 'x' disagrees",
        ) as error:
            verify_scene_bundle(lease)

        assert error.value.code == "scene_integrity_error"
