from __future__ import annotations

import hashlib
import io
import json
import math
import os
import stat
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, NoReturn, cast, overload

import numpy as np
import pandas as pd

from carnopy.app.scene_contracts import (
    SceneBlockContext,
    SceneContractError,
    SceneFieldClassification,
    SceneFieldOrigin,
    SceneFieldProfile,
    SceneProfile,
    SceneSelectionDefaults,
    SceneSourceBinding,
    SceneTopologyEvidence,
    SceneUnitStatus,
)
from carnopy.app.source_inspection import revalidate_scene_binding

Checkpoint = Callable[[], None]
FieldKind = Literal["numeric", "categorical"]
StableIdField = Literal["case_id", "prepared_row_id"]
SceneBlockContextKey = tuple[
    str,
    str,
    str | None,
    str | None,
    str | None,
    str | None,
    str | None,
    str | None,
]

_UINT64_MAX = 2**64 - 1

_COORDINATES: dict[str, tuple[str, str]] = {
    "temperature": ("temperature_K", "K"),
    "pressure": ("pressure_Pa", "Pa"),
    "vapor_mass_fraction": ("vapor_mass_fraction", "1"),
}
_SOURCE_CONTEXTS: tuple[tuple[str, str, str], ...] = (
    ("fluid", "fluid", "Fluid"),
    ("backend_model", "backend_model", "Backend model"),
    ("phase", "phase", "Phase"),
    ("saturation_endpoint", "saturation_endpoint", "Saturation endpoint"),
)
_PREPARED_SOURCE_CONTEXTS: tuple[tuple[str, str, str], ...] = (
    ("source.artifact", "source_artifact", "Source artifact"),
    ("source.run_id", "source_run_id", "Source run ID"),
    ("source.fluid", "source_fluid", "Source fluid"),
    ("source.backend_model", "backend_model", "Source backend model"),
    ("source.phase", "source_phase", "Source phase"),
    (
        "source.saturation_endpoint",
        "source_saturation_endpoint",
        "Source saturation endpoint",
    ),
)
_REQUIRED_DATASET_COLUMNS = {
    "run_id",
    "case_id",
    "mode",
    "fluid",
    "backend",
    "backend_model",
    "backend_version",
    "phase",
    "backend_phase",
    "valid",
    "failure_layer",
    "failure_code",
    "failure_message",
    "failure_property",
    "backend_error_type",
    "backend_error_message",
}
_PREPARED_ID = "prepared_row_id"


@dataclass(frozen=True)
class SceneFieldData:
    field_id: str
    column: str
    label: str
    values: pd.Series
    kind: FieldKind
    classification: SceneFieldClassification
    origin: SceneFieldOrigin
    unit: str | None
    unit_status: SceneUnitStatus


@dataclass(frozen=True)
class LoadedSceneProfileSource:
    binding: SceneSourceBinding
    source_row_count: int
    source_valid: pd.Series
    stable_id_field: StableIdField
    stable_ids: tuple[int, ...]
    row_contexts: tuple[SceneBlockContext, ...]
    fields: tuple[SceneFieldData, ...]
    topology: SceneTopologyEvidence
    default_priority: tuple[str, ...]


def profile_scene(
    binding: SceneSourceBinding,
    *,
    checkpoint: Checkpoint | None = None,
) -> SceneProfile:
    """Revalidate and authoritatively profile one descriptor copied from Inspect."""

    loaded = _load_scene_profile_source(binding, checkpoint=checkpoint)
    return _profile_loaded_scene_source(loaded, checkpoint=checkpoint)


def _load_scene_profile_source(
    binding: SceneSourceBinding,
    *,
    checkpoint: Checkpoint | None,
) -> LoadedSceneProfileSource:
    """Read one exact source once for profiling and later scene projection."""

    accepted = revalidate_scene_binding(binding)
    _checkpoint(checkpoint)
    if accepted.source_kind in {"dataset", "model_sweep"}:
        from carnopy.app.scene_dataset_profiles import load_dataset_source

        return load_dataset_source(accepted, checkpoint=checkpoint)
    from carnopy.app.scene_prepared_profiles import load_prepared_source

    return load_prepared_source(accepted, checkpoint=checkpoint)


def _profile_loaded_scene_source(
    loaded: LoadedSceneProfileSource,
    *,
    checkpoint: Checkpoint | None,
) -> SceneProfile:
    if len(loaded.stable_ids) != loaded.source_row_count:
        _unsupported("scene stable IDs are not aligned with source rows")
    if len(loaded.row_contexts) != loaded.source_row_count:
        _unsupported("scene block contexts are not aligned with source rows")
    projected_fields: list[SceneFieldProfile] = []
    for field in loaded.fields:
        _checkpoint(checkpoint)
        projected_fields.append(_profile_field(field, loaded.source_valid, loaded.source_row_count))
    fields = tuple(projected_fields)
    defaults = _selection_defaults(fields, loaded.default_priority)
    axis_count = sum(field.axis_eligible for field in fields)
    if loaded.source_row_count == 0:
        build_eligible = False
        reason = "the selected source table contains no rows"
    elif int(loaded.source_valid.sum()) == 0:
        build_eligible = False
        reason = "the selected source table contains no source-valid rows"
    elif axis_count < 3:
        build_eligible = False
        reason = "the selected source table has fewer than three finite numeric fields"
    else:
        build_eligible = True
        reason = ""
    return SceneProfile(
        binding=loaded.binding,
        source_row_count=loaded.source_row_count,
        fields=fields,
        topology=loaded.topology,
        defaults=defaults,
        build_eligible=build_eligible,
        ineligible_reason=reason,
    )


def _profile_field(
    field: SceneFieldData,
    source_valid: pd.Series,
    source_row_count: int,
) -> SceneFieldProfile:
    if len(field.values) != source_row_count or len(source_valid) != source_row_count:
        _unsupported(f"scene field {field.field_id!r} is not aligned with source rows")
    values = field.values.reset_index(drop=True)[source_valid.reset_index(drop=True)]
    missing = values.isna()
    value_count = int((~missing).sum())
    missing_count = int(missing.sum())
    if field.kind == "categorical":
        present = values[~missing]
        if any(not isinstance(value, str) for value in present.tolist()):
            _unsupported(f"categorical field {field.field_id!r} contains non-text values")
        distinct = tuple(sorted(set(cast(list[str], present.tolist()))))
        return SceneFieldProfile(
            field_id=field.field_id,
            column=field.column,
            label=field.label,
            dtype=str(field.values.dtype),
            kind="categorical",
            classification=field.classification,
            origin=field.origin,
            unit=None,
            unit_status="unreported",
            source_row_count=source_row_count,
            source_valid_count=int(source_valid.sum()),
            value_count=value_count,
            missing_count=missing_count,
            distinct_values=distinct,
            varying=len(distinct) > 1,
            axis_eligible=False,
            scalar_eligible=False,
            filter_kind="categorical_set" if distinct else None,
            ineligible_reason="categorical fields cannot be scene coordinates or scalars",
        )
    if not pd.api.types.is_numeric_dtype(field.values.dtype) or pd.api.types.is_bool_dtype(
        field.values.dtype
    ):
        _unsupported(f"numeric field {field.field_id!r} has unsupported dtype {field.values.dtype}")
    present_numeric = values[~missing]
    finite_values: list[float] = []
    for raw in present_numeric.tolist():
        if isinstance(raw, (bool, np.bool_)):
            _unsupported(f"numeric field {field.field_id!r} contains a boolean")
        if isinstance(raw, (int, np.integer)) and abs(int(raw)) > 2**53:
            _unsupported(
                f"numeric field {field.field_id!r} contains an integer that binary64 "
                "cannot represent exactly"
            )
        try:
            numeric = float(cast(Any, raw))
        except (TypeError, ValueError, OverflowError) as exc:
            raise SceneContractError(
                "unsupported_scene_source",
                f"numeric field {field.field_id!r} contains a non-numeric value",
            ) from exc
        if math.isfinite(numeric):
            finite_values.append(0.0 if numeric == 0.0 else numeric)
    finite_count = len(finite_values)
    minimum = min(finite_values) if finite_values else None
    maximum = max(finite_values) if finite_values else None
    eligible = finite_count > 0
    return SceneFieldProfile(
        field_id=field.field_id,
        column=field.column,
        label=field.label,
        dtype=str(field.values.dtype),
        kind="numeric",
        classification=field.classification,
        origin=field.origin,
        unit=field.unit,
        unit_status=field.unit_status,
        source_row_count=source_row_count,
        source_valid_count=int(source_valid.sum()),
        value_count=value_count,
        missing_count=missing_count,
        finite_count=finite_count,
        minimum=minimum,
        maximum=maximum,
        varying=minimum != maximum if minimum is not None and maximum is not None else False,
        positive_domain=minimum > 0.0 if minimum is not None else None,
        axis_eligible=eligible,
        scalar_eligible=eligible,
        filter_kind="numeric_range" if eligible else None,
        ineligible_reason="" if eligible else "field has no finite source-valid values",
    )


def _selection_defaults(
    fields: tuple[SceneFieldProfile, ...],
    priority: tuple[str, ...],
) -> SceneSelectionDefaults:
    catalog = {field.field_id: field for field in fields}
    ordered = [
        catalog[field_id]
        for field_id in priority
        if field_id in catalog and catalog[field_id].axis_eligible and catalog[field_id].varying
    ]
    ordered.extend(
        field for field in fields if field.axis_eligible and field.varying and field not in ordered
    )
    selected: list[str | None] = [field.field_id for field in ordered[:3]]
    while len(selected) < 3:
        selected.append(None)
    scalar = next(
        (
            field.field_id
            for field in ordered
            if field.scalar_eligible and field.field_id not in set(selected)
        ),
        None,
    )
    if scalar is None:
        scalar = next((field.field_id for field in ordered if field.scalar_eligible), None)
    return SceneSelectionDefaults(
        x_field=selected[0],
        y_field=selected[1],
        z_field=selected[2],
        scalar_field=scalar,
    )


def _numeric_field(
    field_id: str,
    column: str,
    label: str,
    values: pd.Series,
    classification: SceneFieldClassification,
    origin: SceneFieldOrigin,
    unit: str | None,
    *,
    unit_status: SceneUnitStatus | None = None,
) -> SceneFieldData:
    return SceneFieldData(
        field_id=field_id,
        column=column,
        label=label,
        values=values.reset_index(drop=True),
        kind="numeric",
        classification=classification,
        origin=origin,
        unit=unit,
        unit_status=_unit_status(unit) if unit_status is None else unit_status,
    )


def _categorical_field(
    field_id: str,
    column: str,
    label: str,
    values: pd.Series,
    classification: SceneFieldClassification,
    origin: SceneFieldOrigin,
) -> SceneFieldData:
    return SceneFieldData(
        field_id=field_id,
        column=column,
        label=label,
        values=values.reset_index(drop=True),
        kind="categorical",
        classification=classification,
        origin=origin,
        unit=None,
        unit_status="unreported",
    )


def _field_from_dtype(
    field_id: str,
    column: str,
    label: str,
    values: pd.Series,
    classification: SceneFieldClassification,
    origin: SceneFieldOrigin,
    unit: str | None,
    unit_status: SceneUnitStatus,
) -> SceneFieldData:
    if pd.api.types.is_bool_dtype(values.dtype):
        return _categorical_field(
            field_id,
            column,
            label,
            values.map({True: "true", False: "false"}),
            classification,
            origin,
        )
    if pd.api.types.is_numeric_dtype(values.dtype):
        return _numeric_field(
            field_id,
            column,
            label,
            values,
            classification,
            origin,
            unit,
            unit_status=unit_status,
        )
    return _categorical_field(
        field_id,
        column,
        label,
        values,
        classification,
        origin,
    )


def _read_table(table: Any, checkpoint: Checkpoint | None) -> pd.DataFrame:
    data = _read_identity_bytes(table.artifact, f"scene table {table.table_id}", checkpoint)
    try:
        if table.source_format == "parquet":
            frame = pd.read_parquet(io.BytesIO(data))
        elif table.source_format == "csv":
            frame = pd.read_csv(io.BytesIO(data))
        else:  # pragma: no cover - SceneBoundTable closes this union
            _unsupported(f"unsupported scene table format {table.source_format!r}")
    except (OSError, ValueError, TypeError) as exc:
        raise SceneContractError(
            "unsupported_scene_source",
            f"could not read verified scene table {table.table_id!r}: {exc}",
        ) from exc
    if len(set(str(column) for column in frame.columns)) != len(frame.columns):
        _unsupported(f"scene table {table.table_id!r} contains duplicate columns")
    frame.columns = [str(column) for column in frame.columns]
    return frame


def _read_json_identity(
    identity: Any,
    label: str,
    checkpoint: Checkpoint | None,
) -> dict[str, Any]:
    data = _read_identity_bytes(identity, label, checkpoint)

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate key {key!r}")
            result[key] = value
        return result

    try:
        value = json.loads(
            data.decode("utf-8"),
            parse_constant=lambda constant: _raise_json_constant(constant),
            object_pairs_hook=unique_object,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        _unsupported(f"{label} is not finite UTF-8 JSON: {exc}")
    if not isinstance(value, dict):
        _unsupported(f"{label} must contain one JSON object")
    return cast(dict[str, Any], value)


def _read_identity_bytes(
    identity: Any,
    label: str,
    checkpoint: Checkpoint | None,
) -> bytes:
    path = Path(identity.path)
    try:
        before = path.lstat()
    except OSError as exc:
        _changed(f"{label} is unavailable", exc)
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        _changed(f"{label} is no longer a regular file")
    expected = (
        identity.device,
        identity.inode,
        identity.size,
        identity.modified_ns,
    )
    if _stat_identity(before) != expected:
        _changed(f"{label} identity changed after inspection")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        _changed(f"{label} cannot be opened safely", exc)
    digest = hashlib.sha256()
    chunks: list[bytes] = []
    try:
        with os.fdopen(descriptor, "rb", closefd=True) as stream:
            opened = os.fstat(stream.fileno())
            if _stat_identity(opened) != expected:
                _changed(f"{label} changed while it was opened")
            while chunk := stream.read(8 * 1024 * 1024):
                chunks.append(chunk)
                digest.update(chunk)
                _checkpoint(checkpoint)
            after = os.fstat(stream.fileno())
    except SceneContractError:
        raise
    except OSError as exc:
        _changed(f"{label} cannot be read safely", exc)
    if _stat_identity(after) != expected or digest.hexdigest() != identity.sha256:
        _changed(f"{label} changed while it was read")
    return b"".join(chunks)


def _require_recorded_hash(
    metadata: Mapping[str, Any],
    identity: Any,
    path_value: str,
    *,
    source_root: Path,
) -> None:
    hashes = metadata.get("artifact_hashes")
    if not isinstance(hashes, dict):
        _unsupported("source metadata does not contain artifact hashes")
    path = Path(path_value)
    candidates = {path.name}
    if path.is_relative_to(source_root):
        candidates.add(path.relative_to(source_root).as_posix())
    if not any(hashes.get(candidate) == identity.sha256 for candidate in candidates):
        _unsupported(f"source metadata does not record the accepted hash for {path.name}")


def _validate_control_hashes(
    metadata: Mapping[str, Any],
    binding: SceneSourceBinding,
    *,
    source_root: Path,
    unhashed_names: set[str],
) -> None:
    for control in binding.controls:
        if control.name in unhashed_names:
            continue
        _require_recorded_hash(
            metadata,
            control.artifact,
            control.artifact.path,
            source_root=source_root,
        )


def _prepared_ids(frame: pd.DataFrame, label: str) -> list[int]:
    if _PREPARED_ID not in frame.columns:
        _unsupported(f"{label} has no prepared_row_id")
    values = [
        _stable_uint64(raw, f"{label} prepared_row_id") for raw in frame[_PREPARED_ID].tolist()
    ]
    if len(set(values)) != len(values):
        _unsupported(f"{label} repeats a prepared_row_id")
    return values


def _parse_scenario_table_id(table_id: str) -> tuple[str, str]:
    parts = table_id.split(".")
    if len(parts) != 3 or parts[0] != "scenario":
        _unsupported("selected prepared table is not a recognized scenario partition")
    return parts[1], parts[2]


def _strict_boolean_series(series: pd.Series, label: str) -> pd.Series:
    if series.isna().any() or any(not isinstance(value, (bool, np.bool_)) for value in series):
        _unsupported(f"{label} values must be complete booleans")
    return series.astype(bool).reset_index(drop=True)


def _finite_float(value: object, label: str) -> float:
    if isinstance(value, (bool, np.bool_)):
        _unsupported(f"{label} contains a boolean where a number is required")
    if isinstance(value, (int, np.integer)) and abs(int(value)) > 2**53:
        _unsupported(f"{label} contains an integer that binary64 cannot represent exactly")
    try:
        numeric = float(cast(Any, value))
    except (TypeError, ValueError, OverflowError) as exc:
        raise SceneContractError(
            "unsupported_scene_source",
            f"{label} contains a non-numeric value",
        ) from exc
    if not math.isfinite(numeric):
        raise SceneContractError(
            "unsupported_scene_source",
            f"{label} contains a non-finite value",
        )
    return 0.0 if numeric == 0.0 else numeric


def _unit_status(unit: str | None) -> SceneUnitStatus:
    if unit == "1":
        return "dimensionless"
    return "canonical" if unit is not None else "unreported"


def _require_version(
    value: Mapping[str, Any],
    key: str,
    expected: int,
    label: str,
) -> None:
    if value.get(key) != expected or not _exact_int(value.get(key)):
        _unsupported(f"{label} schema version is unsupported")


def _string_mapping(value: object, label: str) -> dict[str, str]:
    if not isinstance(value, dict) or any(
        not isinstance(key, str) or not isinstance(item, str) for key, item in value.items()
    ):
        _unsupported(f"{label} must be an exact string mapping")
    return cast(dict[str, str], value)


def _string_list(value: object, label: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        _unsupported(f"{label} must be an exact string list")
    return cast(list[str], value)


def _require_unique_field_ids(fields: Sequence[SceneFieldData]) -> None:
    identifiers = [field.field_id for field in fields]
    if len(set(identifiers)) != len(identifiers):
        _unsupported("scene source resolves multiple columns to one semantic field ID")


def _label(value: str) -> str:
    return value.replace(".", " ").replace("__", " / ").replace("_", " ").strip().title()


def _exact_int(value: object) -> bool:
    return isinstance(value, (int, np.integer)) and not isinstance(value, (bool, np.bool_))


def _stable_uint64(value: object, label: str) -> int:
    if not _exact_int(value):
        _unsupported(f"{label} must be an exact unsigned 64-bit integer")
    numeric = int(cast(int, value))
    if numeric < 0 or numeric > _UINT64_MAX:
        _unsupported(f"{label} must be an exact unsigned 64-bit integer")
    return numeric


@overload
def _context_text(value: object, label: str, *, required: Literal[True]) -> str: ...


@overload
def _context_text(
    value: object,
    label: str,
    *,
    required: Literal[False] = False,
) -> str | None: ...


def _context_text(
    value: object,
    label: str,
    *,
    required: bool = False,
) -> str | None:
    try:
        missing = bool(pd.isna(cast(Any, value)))
    except (TypeError, ValueError):
        missing = False
    if missing:
        if required:
            _unsupported(f"{label} is missing")
        return None
    if not isinstance(value, str) or not value or "\x00" in value:
        _unsupported(f"{label} must be exact non-empty text")
    return value


def _intern_block_context(
    cache: dict[SceneBlockContextKey, SceneBlockContext],
    *,
    source_artifact: str,
    source_run_id: str,
    fluid: str | None,
    backend_model: str | None,
    phase: str | None,
    saturation_endpoint: str | None,
    scenario: str | None = None,
    partition: str | None = None,
) -> SceneBlockContext:
    key: SceneBlockContextKey = (
        source_artifact,
        source_run_id,
        fluid,
        backend_model,
        phase,
        saturation_endpoint,
        scenario,
        partition,
    )
    existing = cache.get(key)
    if existing is not None:
        return existing
    context = SceneBlockContext(
        source_artifact=source_artifact,
        source_run_id=source_run_id,
        fluid=fluid,
        backend_model=backend_model,
        phase=phase,
        saturation_endpoint=saturation_endpoint,
        scenario=scenario,
        partition=partition,
    )
    cache[key] = context
    return context


def _stat_identity(value: os.stat_result) -> tuple[int, int, int, int]:
    return value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns


def _checkpoint(checkpoint: Checkpoint | None) -> None:
    if checkpoint is not None:
        checkpoint()


def _unsupported(message: str) -> NoReturn:
    raise SceneContractError("unsupported_scene_source", message)


def _changed(message: str, cause: BaseException | None = None) -> NoReturn:
    error = SceneContractError("scene_source_changed", message)
    if cause is None:
        raise error
    raise error from cause


def _raise_json_constant(value: str) -> NoReturn:
    raise ValueError(f"non-finite JSON constant {value}")
