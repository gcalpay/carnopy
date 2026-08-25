from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pandas as pd

from carnopy.app.scene_contracts import (
    SceneSourceBinding,
    SceneTopologyAxis,
    SceneTopologyEvidence,
)
from carnopy.app.scene_profiles import (
    _COORDINATES,
    _REQUIRED_DATASET_COLUMNS,
    _SOURCE_CONTEXTS,
    Checkpoint,
    LoadedSceneProfileSource,
    SceneFieldData,
    _categorical_field,
    _exact_int,
    _finite_float,
    _label,
    _numeric_field,
    _read_json_identity,
    _read_table,
    _require_recorded_hash,
    _require_unique_field_ids,
    _require_version,
    _stable_uint64,
    _strict_boolean_series,
    _string_list,
    _string_mapping,
    _unsupported,
    _validate_control_hashes,
)
from carnopy.domain.properties import PROPERTY_REGISTRY


def load_dataset_source(
    binding: SceneSourceBinding,
    *,
    checkpoint: Checkpoint | None,
) -> LoadedSceneProfileSource:
    selected = binding.selected_table()
    if selected.metadata is None:
        _unsupported("dataset scene sources require recorded metadata")
    metadata = _read_json_identity(selected.metadata, "dataset metadata", checkpoint)
    _require_version(metadata, "metadata_schema_version", 1, "dataset metadata")
    _require_version(metadata, "dataset_schema_version", 2, "dataset")
    _require_recorded_hash(
        metadata,
        selected.artifact,
        selected.artifact.path,
        source_root=Path(selected.artifact.path).parent,
    )
    if binding.source_kind == "dataset":
        controls = {control.name: control.artifact for control in binding.controls}
        if not {"metadata.json", "report.json"}.issubset(controls):
            _unsupported("dataset scene sources require metadata and report controls")
        if controls["metadata.json"] != selected.metadata:
            _unsupported("dataset metadata identities disagree within the Inspect binding")
        _validate_control_hashes(
            metadata,
            binding,
            source_root=Path(binding.source_path),
            unhashed_names={"metadata.json"},
        )
    if binding.source_kind == "model_sweep":
        _validate_sweep_parent(binding, selected.table_id, metadata, checkpoint)
    frame = _read_table(selected, checkpoint)
    stable_ids = _validate_dataset_frame(frame, metadata)
    source_valid = _strict_boolean_series(frame["valid"], "dataset valid")
    fields: list[SceneFieldData] = []
    topology_axes = _dataset_topology_axes(metadata, frame)
    topology_ids = {axis.field_id for axis in topology_axes}
    units = _string_mapping(metadata.get("canonical_units"), "canonical_units")
    for field_id, (column, expected_unit) in _COORDINATES.items():
        if column not in frame.columns:
            continue
        unit = units.get(column)
        if unit != expected_unit:
            _unsupported(
                f"dataset coordinate {field_id!r} does not record canonical unit {expected_unit!r}"
            )
        fields.append(
            _numeric_field(
                field_id,
                column,
                _label(field_id),
                frame[column],
                "source_coordinate",
                "table",
                unit,
            )
        )
    properties = _string_list(metadata.get("canonical_properties"), "canonical_properties")
    if len(set(properties)) != len(properties):
        _unsupported("dataset metadata repeats a canonical property")
    for name in properties:
        definition = PROPERTY_REGISTRY.get(name)
        if definition is None or definition.column not in frame.columns:
            _unsupported(f"dataset property {name!r} is unknown or absent")
        if units.get(definition.column) != definition.unit:
            _unsupported(f"dataset property {name!r} does not record its canonical unit")
        fields.append(
            _numeric_field(
                name,
                definition.column,
                _label(name),
                frame[definition.column],
                "emitted_property",
                "table",
                definition.unit,
            )
        )
    for field_id, column, label in _SOURCE_CONTEXTS:
        if column in frame.columns and not frame[column].isna().all():
            fields.append(
                _categorical_field(
                    field_id,
                    column,
                    label,
                    frame[column],
                    "context",
                    "table",
                )
            )
    _require_unique_field_ids(fields)
    context_fields = ["source_artifact", "source_run_id"]
    context_fields.extend(
        name
        for name in ("fluid", "backend_model", "phase", "saturation_endpoint")
        if name in frame.columns and not frame[name].isna().all()
    )
    topology = SceneTopologyEvidence(
        status="exact",
        axes=topology_axes,
        context_fields=tuple(context_fields),
    )
    priority = (
        *(axis.field_id for axis in topology_axes),
        *(name for name in _COORDINATES if name not in topology_ids),
        *properties,
    )
    return LoadedSceneProfileSource(
        binding=binding,
        source_row_count=len(frame),
        source_valid=source_valid,
        stable_id_field="case_id",
        stable_ids=stable_ids,
        fields=tuple(fields),
        topology=topology,
        default_priority=tuple(priority),
    )


def _validate_sweep_parent(
    binding: SceneSourceBinding,
    table_id: str,
    child_metadata: Mapping[str, Any],
    checkpoint: Checkpoint | None,
) -> None:
    controls = {control.name: control.artifact for control in binding.controls}
    if not {"sweep.normalized.json", "metadata.json", "report.json"}.issubset(controls):
        _unsupported("model-sweep scene sources require normalized, metadata, and report controls")
    sweep_identity = controls.get("metadata.json")
    if sweep_identity is None:
        _unsupported("model-sweep scene sources require sweep metadata")
    sweep = _read_json_identity(sweep_identity, "sweep metadata", checkpoint)
    _require_version(sweep, "sweep_metadata_schema_version", 1, "model-sweep metadata")
    _validate_control_hashes(
        sweep,
        binding,
        source_root=Path(binding.source_path),
        unhashed_names={"metadata.json"},
    )
    if not table_id.startswith("model.") or not table_id.endswith(".dataset"):
        _unsupported("only model-sweep child datasets may be profiled")
    model = table_id.removeprefix("model.").removesuffix(".dataset")
    if child_metadata.get("backend_model") != model:
        _unsupported("sweep child metadata disagrees with its selected model")
    child_runs = sweep.get("child_runs")
    if not isinstance(child_runs, list):
        _unsupported("model-sweep metadata does not record child runs")
    matches = [
        child
        for child in child_runs
        if isinstance(child, dict) and child.get("backend_model") == model
    ]
    if len(matches) != 1:
        _unsupported("model-sweep metadata does not identify the selected child exactly once")
    child = matches[0]
    if child.get("run_id") != child_metadata.get("run_id"):
        _unsupported("sweep and child metadata disagree about the selected run")


def _validate_dataset_frame(
    frame: pd.DataFrame,
    metadata: Mapping[str, Any],
) -> tuple[int, ...]:
    missing = sorted(_REQUIRED_DATASET_COLUMNS - set(frame.columns))
    if missing:
        _unsupported("dataset table is missing required columns: " + ", ".join(missing))
    row_count = metadata.get("row_count")
    if not _exact_int(row_count) or row_count != len(frame):
        _unsupported("dataset metadata row count disagrees with the table")
    valid = _strict_boolean_series(frame["valid"], "dataset valid")
    valid_count = metadata.get("valid_row_count")
    invalid_count = metadata.get("invalid_row_count")
    if (
        not _exact_int(valid_count)
        or not _exact_int(invalid_count)
        or valid_count != int(valid.sum())
        or invalid_count != int((~valid).sum())
    ):
        _unsupported("dataset validity counts disagree with the table")
    for column in ("run_id", "case_id", "mode", "backend_model"):
        if frame[column].isna().any():
            _unsupported(f"dataset identity column {column!r} contains missing values")
    if frame["case_id"].duplicated().any():
        _unsupported("dataset case_id values are not unique")
    stable_ids = tuple(
        _stable_uint64(value, "dataset case_id") for value in frame["case_id"].tolist()
    )
    run_id = metadata.get("run_id")
    mode = metadata.get("mode")
    backend_model = metadata.get("backend_model")
    for column, expected in (
        ("run_id", run_id),
        ("mode", mode),
        ("backend_model", backend_model),
    ):
        observed = frame[column].tolist()
        if (
            not isinstance(expected, str)
            or any(not isinstance(value, str) for value in observed)
            or set(observed) != {expected}
        ):
            _unsupported(f"dataset metadata disagrees with table column {column!r}")
    return stable_ids


def _dataset_topology_axes(
    metadata: Mapping[str, Any],
    frame: pd.DataFrame,
) -> tuple[SceneTopologyAxis, ...]:
    sampling = metadata.get("sampling")
    materialized = sampling.get("materialized_si") if isinstance(sampling, dict) else None
    if not isinstance(materialized, dict):
        _unsupported("dataset metadata does not record materialized SI sampling")
    mode = metadata.get("mode")
    expected_options: tuple[tuple[str, ...], ...]
    if mode == "property_table":
        expected_options = (("temperature", "pressure"),)
    elif mode == "saturation_table":
        expected_options = (("temperature",), ("pressure",))
    elif mode == "vapor_mass_fraction_table":
        expected_options = (
            ("temperature", "vapor_mass_fraction"),
            ("pressure", "vapor_mass_fraction"),
        )
    else:
        _unsupported("dataset metadata records an unsupported generation mode")
    keys = tuple(str(key) for key in materialized)
    selected = next((option for option in expected_options if set(option) == set(keys)), None)
    if selected is None:
        _unsupported("dataset sampling axes disagree with the recorded generation mode")
    units = _string_mapping(metadata.get("canonical_units"), "canonical_units")
    axes: list[SceneTopologyAxis] = []
    for field_id in selected:
        column, expected_unit = _COORDINATES[field_id]
        raw_levels = materialized.get(field_id)
        if not isinstance(raw_levels, list) or not raw_levels:
            _unsupported(f"dataset sampling axis {field_id!r} has no ordered levels")
        levels = tuple(
            _finite_float(value, f"sampling level for {field_id}") for value in raw_levels
        )
        if len(set(levels)) != len(levels):
            _unsupported(f"dataset sampling axis {field_id!r} repeats an exact level")
        if column not in frame.columns or units.get(column) != expected_unit:
            _unsupported(f"dataset sampling axis {field_id!r} is absent or has the wrong unit")
        observed = frame[column].dropna()
        if not pd.api.types.is_numeric_dtype(observed.dtype):
            _unsupported(f"dataset sampling column {column!r} is not numeric")
        if any(_finite_float(value, column) not in set(levels) for value in observed.tolist()):
            _unsupported(f"dataset column {column!r} contains an unrecorded sampling level")
        axes.append(
            SceneTopologyAxis(
                field_id=field_id,
                source_column=column,
                unit=expected_unit,
                levels=levels,
            )
        )
    return tuple(axes)
