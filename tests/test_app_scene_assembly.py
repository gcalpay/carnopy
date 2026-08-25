from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pandas as pd
import pytest

from carnopy.api import generate_dataset, prepare_dataset
from carnopy.app import scene_contracts
from carnopy.app.scene_assembly import (
    SceneGeometryAssembly,
    _connectivity_blocker,
    build_scene_geometry,
)
from carnopy.app.scene_contracts import (
    NumericRangeFilter,
    SceneContractError,
    SceneProfile,
    SceneRepresentation,
    SceneRepresentationCapability,
    SceneRequest,
    SceneTopologyAxis,
)
from carnopy.app.scene_profiles import profile_scene
from carnopy.app.source_inspection import inspect_for_app


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _generate_grid(
    tmp_path: Path,
    *,
    name: str,
) -> Path:
    config = tmp_path / f"{name}.yaml"
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
properties: [specific_enthalpy, mass_density, specific_entropy]
outputs:
  dataset_formats: [parquet]
""",
        encoding="utf-8",
    )
    return generate_dataset(config, output_root=tmp_path / f"{name}-runs").output_directory


def _rewrite_dataset(run: Path, frame: pd.DataFrame) -> None:
    dataset = run / "dataset.parquet"
    frame.to_parquet(dataset, index=False)
    metadata_path = run / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    valid_count = int(frame["valid"].sum())
    metadata["row_count"] = len(frame)
    metadata["valid_row_count"] = valid_count
    metadata["invalid_row_count"] = len(frame) - valid_count
    metadata["run_status"] = "completed" if valid_count == len(frame) else "incomplete"
    metadata["artifact_hashes"]["dataset.parquet"] = _sha256(dataset)
    metadata_path.write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


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


def _capability_map(
    assembly: SceneGeometryAssembly,
) -> dict[SceneRepresentation, SceneRepresentationCapability]:
    return {capability.representation: capability for capability in assembly.capabilities}


def test_capabilities_follow_zero_one_and_two_dimensional_exact_geometry(
    tmp_path: Path,
) -> None:
    run = _generate_grid(tmp_path, name="dimensions")
    frame = pd.read_parquet(run / "dataset.parquet")
    frame["phase"] = "gas"
    _rewrite_dataset(run, frame)
    profile = _profile(run)
    requests = (
        _request(
            profile,
            NumericRangeFilter(field_id="temperature", minimum=330.0, maximum=330.0),
            NumericRangeFilter(field_id="pressure", minimum=400_000.0, maximum=400_000.0),
        ),
        _request(
            profile,
            NumericRangeFilter(field_id="temperature", minimum=330.0, maximum=330.0),
        ),
        _request(profile),
    )

    zero, one, two = tuple(build_scene_geometry(profile, request) for request in requests)

    assert (zero.counts.points, zero.counts.edges, zero.counts.quads) == (1, 0, 0)
    assert (one.counts.points, one.counts.edges, one.counts.quads) == (2, 1, 0)
    assert (two.counts.points, two.counts.edges, two.counts.quads) == (4, 4, 1)
    assert [capability.available for capability in zero.capabilities] == [True, False, False]
    assert [capability.available for capability in one.capabilities] == [True, True, False]
    assert [capability.available for capability in two.capabilities] == [True, True, True]
    assert _capability_map(zero)["wireframe"].blockers[0].code == "no_valid_edges"
    assert _capability_map(one)["surface"].blockers[0].code == "no_valid_quads"
    assert two.storage.topology_level_count == 4
    assert two.storage.binary_bytes == 288
    assert two.storage.manifest_projection_bytes > 0
    assert two.storage.bundle_projection_bytes == two.counts.bundle_bytes
    assert build_scene_geometry(profile, requests[2]).storage == two.storage
    assert tuple(extent.role for extent in two.value_extents) == ("x", "y", "z", "scalar")
    assert all(extent.logarithmic_available for extent in two.value_extents)
    assert not hasattr(two, "triangles")


def test_capabilities_are_global_and_report_every_blocking_context(tmp_path: Path) -> None:
    run = _generate_grid(tmp_path, name="contexts")
    base = pd.read_parquet(run / "dataset.parquet")
    base["phase"] = ["gas", "gas", "liquid", "liquid"]
    duplicate = base.iloc[[0]].copy()
    duplicate["case_id"] = 4
    missing_context = base.iloc[[1]].copy()
    missing_context["case_id"] = 5
    missing_context["phase"] = None
    frame = pd.concat([base, duplicate, missing_context], ignore_index=True)
    _rewrite_dataset(run, frame)
    profile = _profile(run)

    assembly = build_scene_geometry(profile, _request(profile))

    assert [block.context.phase for block in assembly.topology.blocks] == [None, "gas", "liquid"]
    assert [len(block.edges) for block in assembly.cells.edge_projection.blocks] == [0, 0, 1]
    capabilities = _capability_map(assembly)
    assert capabilities["points"].available
    assert not capabilities["wireframe"].available
    assert [blocker.code for blocker in capabilities["wireframe"].blockers] == [
        "missing_context",
        "duplicate_topology_location",
    ]
    assert not capabilities["surface"].available
    assert [blocker.code for blocker in capabilities["surface"].blockers] == [
        "missing_context",
        "duplicate_topology_location",
        "no_valid_quads",
    ]


def test_degenerate_cell_retains_wireframe_and_exact_log_domain_evidence(
    tmp_path: Path,
) -> None:
    run = _generate_grid(tmp_path, name="degenerate")
    frame = pd.read_parquet(run / "dataset.parquet")
    frame["phase"] = "gas"
    for column in (
        "specific_enthalpy_J_kg",
        "mass_density_kg_m3",
        "specific_entropy_J_kgK",
    ):
        frame[column] = [0.0, 1.0, 2.0, 3.0]
    _rewrite_dataset(run, frame)
    profile = _profile(run)
    request = SceneRequest(
        binding=profile.binding,
        x_field="specific_enthalpy",
        y_field="mass_density",
        z_field="specific_entropy",
        scalar_field="temperature",
    )

    assembly = build_scene_geometry(profile, request)

    assert assembly.counts.edges == 4
    assert assembly.counts.quads == 0
    capabilities = _capability_map(assembly)
    assert capabilities["wireframe"].available
    assert not capabilities["surface"].available
    assert capabilities["surface"].blockers[0].code == "no_valid_quads"
    assert [extent.logarithmic_available for extent in assembly.value_extents] == [
        False,
        False,
        False,
        True,
    ]
    assert assembly.value_extents[0].minimum == 0.0
    assert assembly.cells.blocks[0].omitted_collinear_count == 1


def test_prepared_topology_unavailability_preserves_points_only(
    property_config_path: Path,
    tmp_path: Path,
) -> None:
    run = generate_dataset(property_config_path, output_root=tmp_path / "runs")
    config = tmp_path / "preparation.yaml"
    config.write_text(
        """schema_version: 1
document_type: preparation
features:
  numeric: [temperature, pressure, mass_density]
  derived: [specific_volume]
categorical_features: []
targets: [specific_enthalpy]
scenarios:
  - name: baseline
    kind: unsplit
outputs:
  formats: [parquet]
""",
        encoding="utf-8",
    )
    prepared = prepare_dataset(
        run.output_directory,
        config=config,
        output_root=tmp_path / "prepared",
    )
    inspected = inspect_for_app(prepared.output_directory)
    binding = next(
        value
        for value in inspected.scene_bindings
        if value.selected_table_id == "scenario.baseline.all"
    )
    profile = profile_scene(binding)
    request = SceneRequest(
        binding=binding,
        x_field="temperature",
        y_field="pressure",
        z_field="mass_density",
        scalar_field="specific_enthalpy",
    )

    assembly = build_scene_geometry(profile, request)

    assert assembly.counts.points > 0
    assert assembly.counts.edges == assembly.counts.quads == 0
    assert [capability.available for capability in assembly.capabilities] == [True, False, False]
    assert {
        blocker.code for capability in assembly.capabilities[1:] for blocker in capability.blockers
    } == {"topology_unavailable"}


def test_unsupported_topology_dimension_has_an_explicit_capability_blocker(
    tmp_path: Path,
) -> None:
    run = _generate_grid(tmp_path, name="unsupported")
    frame = pd.read_parquet(run / "dataset.parquet")
    frame["phase"] = "gas"
    _rewrite_dataset(run, frame)
    profile = _profile(run)
    assembly = build_scene_geometry(profile, _request(profile))
    block = assembly.topology.blocks[0]
    third_axis = SceneTopologyAxis(
        field_id="mass_density",
        source_column="mass_density_kg_m3",
        unit="kg/m^3",
        levels=(1.0, 2.0),
    )
    unsupported = replace(
        block,
        topology=replace(
            block.topology,
            status="unsupported_dimension",
            dimension=3,
            axes=(*block.topology.axes, third_axis),
            locations=tuple(
                replace(
                    location,
                    level_indices=(*location.level_indices, index % 2),
                )
                for index, location in enumerate(block.topology.locations)
            ),
            reason_code="unsupported_topology_dimension",
            reason="the retained block has 3 varying topology dimensions",
        ),
    )

    blocker = _connectivity_blocker(
        unsupported,
        representation="wireframe",
        primitive_count=0,
    )

    assert blocker is not None
    assert blocker.code == "unsupported_topology_dimension"
    assert blocker.block_index == 0


def test_complete_geometry_enforces_every_hard_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = _generate_grid(tmp_path, name="limits")
    frame = pd.read_parquet(run / "dataset.parquet")
    frame["phase"] = "gas"
    _rewrite_dataset(run, frame)
    profile = _profile(run)
    request = _request(profile)
    accepted = build_scene_geometry(profile, request)
    limits = (
        ("MAX_SCENE_POINTS", accepted.counts.points - 1, "points"),
        ("MAX_SCENE_EDGES", accepted.counts.edges - 1, "edges"),
        ("MAX_SCENE_QUADS", accepted.counts.quads - 1, "quads"),
        (
            "MAX_SCENE_BUNDLE_BYTES",
            accepted.counts.bundle_bytes - 1,
            "bundle_bytes",
        ),
    )

    for constant, limit, measure in limits:
        with monkeypatch.context() as patch:
            patch.setattr(scene_contracts, constant, limit)
            with pytest.raises(SceneContractError, match="exceeds limit") as error:
                build_scene_geometry(profile, request)
        assert error.value.code == "scene_limit_exceeded"
        assert error.value.details["measure"] == measure
        assert error.value.details["actual"] == getattr(accepted.counts, measure)
        assert error.value.details["limit"] == limit
