from __future__ import annotations

import copy
import hashlib
import json
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from carnopy.app.plot_context import build_plot_context
from carnopy.domain.failures import ConfigError
from carnopy.domain.properties import PROPERTY_REGISTRY
from carnopy.inspection import PreparationInspection, SweepInspection, inspect_source
from carnopy.preparation.derived import DERIVED_FEATURE_REGISTRY
from carnopy.preparation.fields import (
    CATEGORICAL_FIELDS,
    ResolvedField,
    compute_derived_value,
    preparation_field_capabilities,
)
from carnopy.preparation.models import DerivedFeature
from carnopy.preparation.reference import assess_reference_context
from carnopy.preparation.source import LoadedPreparationSource, load_preparation_source
from carnopy.provenance import sha256_file
from carnopy.visualization.inspect import PlotInspection
from carnopy.visualization.models import VisualizationError


@dataclass(frozen=True)
class ResolvedTable:
    table_id: str
    label: str
    path: Path
    source_format: str
    units: dict[str, str]
    sha256: str
    metadata_path: Path | None = None
    metadata_sha256: str | None = None

    def public_descriptor(self) -> dict[str, object]:
        return {
            "id": self.table_id,
            "label": self.label,
            "format": self.source_format,
            "sha256": self.sha256,
        }

    def private_descriptor(self) -> dict[str, object]:
        descriptor: dict[str, object] = {
            **self.public_descriptor(),
            "path": str(self.path.resolve(strict=True)),
        }
        descriptor.update(_file_identity_descriptor(self.path, self.sha256))
        if self.metadata_path is not None:
            metadata_digest = self.metadata_sha256
            if metadata_digest is None:
                metadata_digest = sha256_file(self.metadata_path)
            descriptor["metadata"] = {
                "path": str(self.metadata_path.resolve(strict=True)),
                **_file_identity_descriptor(self.metadata_path, metadata_digest),
            }
        return descriptor


@dataclass(frozen=True)
class ResolvedInspection:
    source: Path
    source_kind: str
    summary: dict[str, Any]
    revision: str
    tables: tuple[ResolvedTable, ...]
    arrays: tuple[dict[str, Any], ...]
    plot_context: dict[str, Any] | None = None
    preparation_eligible: bool = False
    preparation_ineligible_reason: str = ""
    preparation_source_descriptor: dict[str, Any] | None = None
    preparation_profile: dict[str, Any] | None = None

    def public_payload(self) -> dict[str, Any]:
        return {
            "source": str(self.source),
            "source_kind": self.source_kind,
            "revision": self.revision,
            "summary": self.summary,
            "tables": [table.public_descriptor() for table in self.tables],
            "arrays": list(self.arrays),
            "plot_context": self.plot_context,
            "preparation_eligible": self.preparation_eligible,
            "preparation_ineligible_reason": self.preparation_ineligible_reason,
            "preparation_source_descriptor": self.preparation_source_descriptor,
            "preparation_profile": self.preparation_profile,
        }


@dataclass(frozen=True)
class ResolvedCatalog:
    source_kind: str
    revision: str
    tables: tuple[ResolvedTable, ...]
    arrays: tuple[dict[str, Any], ...]
    controls: dict[str, Any]


def inspect_for_app(source: str | Path) -> ResolvedInspection:
    requested = Path(source).expanduser().absolute()
    catalog = _resolve_catalog(requested)
    inspection = inspect_source(requested)
    if isinstance(inspection, PlotInspection):
        kind = "dataset"
        plot_context = build_plot_context(inspection)
    elif isinstance(inspection, SweepInspection):
        kind = "model_sweep"
        plot_context = None
    elif isinstance(inspection, PreparationInspection):
        kind = "preparation"
        plot_context = None
    else:  # pragma: no cover - closed inspection union
        raise VisualizationError("unsupported inspection result")
    if kind != catalog.source_kind:
        raise VisualizationError("inspection source classification changed during inspection")
    summary = inspection.to_dict()
    eligible, ineligible_reason, preparation_descriptor, preparation_profile = (
        _preparation_eligibility(
            requested,
            kind,
            catalog,
            summary,
        )
    )
    return ResolvedInspection(
        source=requested,
        source_kind=kind,
        summary=summary,
        revision=catalog.revision,
        tables=catalog.tables,
        arrays=catalog.arrays,
        plot_context=plot_context,
        preparation_eligible=eligible,
        preparation_ineligible_reason=ineligible_reason,
        preparation_source_descriptor=preparation_descriptor,
        preparation_profile=preparation_profile,
    )


def resolve_table(
    source: str | Path,
    table_id: str,
    revision: str,
) -> ResolvedTable:
    catalog = _resolve_catalog(Path(source).expanduser().absolute())
    if catalog.revision != revision:
        raise VisualizationError("inspection source changed; refresh before previewing data")
    for table in catalog.tables:
        if table.table_id == table_id:
            return table
    raise VisualizationError(f"inspection source does not contain table ID {table_id!r}")


def revalidate_preparation_inspection(
    source: str | Path,
    *,
    inspection_revision: str,
    inspection_descriptor: dict[str, Any],
) -> None:
    """Recheck an accepted preparation source without parsing table contents."""
    requested = Path(source).expanduser().absolute()
    catalog = _resolve_catalog(requested)
    if catalog.revision != inspection_revision:
        raise VisualizationError("preparation source changed after inspection")
    if catalog.source_kind == "preparation":
        raise VisualizationError("prepared bundles cannot be used as preparation sources")
    if catalog.source_kind == "dataset" and not requested.is_dir():
        raise VisualizationError(
            "standalone CSV and Parquet files cannot be used as preparation sources"
        )
    descriptor = _preparation_descriptor(requested, catalog.source_kind, catalog)
    if descriptor != inspection_descriptor:
        raise VisualizationError("preparation source identity changed after inspection")


def _resolve_catalog(source: Path) -> ResolvedCatalog:
    if source.is_dir() and (source / "preparation.normalized.json").is_file():
        manifest = _read_json(source / "manifest.json", "preparation manifest")
        tables = _preparation_tables(source, manifest)
        arrays = _preparation_arrays(manifest)
        controls = _control_hashes(
            source,
            (
                "preparation.normalized.json",
                "manifest.json",
                "diagnostics.json",
                "scenario_report.json",
            ),
        )
        return ResolvedCatalog(
            "preparation",
            _catalog_revision("preparation", tables, controls),
            tables,
            arrays,
            controls,
        )
    if source.is_dir() and (source / "sweep.normalized.json").is_file():
        metadata = _read_json(source / "metadata.json", "sweep metadata")
        tables = _sweep_tables(source, metadata)
        controls = _control_hashes(
            source,
            ("sweep.normalized.json", "metadata.json", "report.json"),
        )
        return ResolvedCatalog(
            "model_sweep",
            _catalog_revision("model_sweep", tables, controls),
            tables,
            (),
            controls,
        )
    table = _dataset_table(source)
    controls = _control_hashes(table.path.parent, ("metadata.json", "report.json"))
    return ResolvedCatalog(
        "dataset",
        _catalog_revision("dataset", (table,), controls),
        (table,),
        (),
        controls,
    )


def _dataset_table(source: Path) -> ResolvedTable:
    if source.is_symlink():
        raise VisualizationError("dataset source must not be a symbolic link")
    if source.is_dir():
        dataset = _preferred_dataset(source)
    elif source.is_file() and source.suffix.lower() in {".csv", ".parquet"}:
        dataset = source
    else:
        raise VisualizationError("dataset source must be a run directory, CSV, or Parquet")
    units: dict[str, str] = {}
    metadata_path = dataset.parent / "metadata.json"
    digest = sha256_file(dataset)
    if metadata_path.is_file():
        metadata = _read_json(metadata_path, "dataset metadata")
        hashes = metadata.get("artifact_hashes")
        expected = hashes.get(dataset.name) if isinstance(hashes, dict) else None
        if isinstance(expected, str) and expected != digest:
            raise VisualizationError(f"dataset hash mismatch for {dataset.name}")
        value = metadata.get("canonical_units")
        if isinstance(value, dict):
            units = {str(key): str(unit) for key, unit in value.items() if unit is not None}
    return ResolvedTable(
        table_id="dataset",
        label="Dataset",
        path=dataset,
        source_format=dataset.suffix.removeprefix("."),
        units=units,
        sha256=digest,
        metadata_path=metadata_path if metadata_path.is_file() else None,
        metadata_sha256=(sha256_file(metadata_path) if metadata_path.is_file() else None),
    )


def _sweep_tables(root: Path, metadata: dict[str, Any]) -> tuple[ResolvedTable, ...]:
    hashes = metadata.get("artifact_hashes")
    artifact_hashes = hashes if isinstance(hashes, dict) else {}
    tables: list[ResolvedTable] = []
    for table_id, relative in (
        ("comparison.values", "comparison/values.parquet"),
        ("comparison.deltas", "comparison/deltas.parquet"),
    ):
        path = root / relative
        if not path.exists():
            continue
        path = _safe_artifact(root, relative, table_id, artifact_hashes)
        tables.append(_table(table_id, table_id, path))

    child_runs = metadata.get("child_runs")
    if isinstance(child_runs, list):
        for child in child_runs:
            if not isinstance(child, dict):
                continue
            model = child.get("backend_model")
            output = child.get("output_directory")
            if not isinstance(model, str) or not isinstance(output, str):
                continue
            if re.fullmatch(r"[a-z0-9_-]+", model) is None:
                raise VisualizationError(f"invalid child model identifier: {model!r}")
            child_root = _contained_directory(
                root,
                root / "models" / model / Path(output).name,
                f"model {model} child run",
            )
            dataset = _preferred_dataset(child_root)
            child_metadata_path = child_root / "metadata.json"
            child_metadata = _read_json(child_metadata_path, "child metadata")
            child_hashes = child_metadata.get("artifact_hashes")
            expected = child_hashes.get(dataset.name) if isinstance(child_hashes, dict) else None
            digest = sha256_file(dataset)
            if isinstance(expected, str) and digest != expected:
                raise VisualizationError(f"child dataset hash mismatch for model {model}")
            units = child_metadata.get("canonical_units")
            tables.append(
                ResolvedTable(
                    table_id=f"model.{model}.dataset",
                    label=f"{model} child dataset",
                    path=dataset,
                    source_format=dataset.suffix.removeprefix("."),
                    units=(
                        {str(key): str(value) for key, value in units.items()}
                        if isinstance(units, dict)
                        else {}
                    ),
                    sha256=digest,
                    metadata_path=child_metadata_path,
                    metadata_sha256=sha256_file(child_metadata_path),
                )
            )
    return tuple(tables)


def _preparation_tables(
    root: Path,
    manifest: dict[str, Any],
) -> tuple[ResolvedTable, ...]:
    tables: list[ResolvedTable] = []
    artifacts = manifest.get("data_artifacts")
    if not isinstance(artifacts, dict):
        raise VisualizationError("preparation manifest does not contain data_artifacts")
    hashes = manifest.get("artifact_hashes")
    artifact_hashes = hashes if isinstance(hashes, dict) else {}
    units = _preparation_units(manifest)
    for table_id, value in (
        ("table", artifacts.get("table")),
        ("provenance", artifacts.get("provenance")),
        ("diagnostics", artifacts.get("diagnostics")),
        ("exclusions", artifacts.get("exclusions")),
    ):
        if value is not None:
            if not isinstance(value, str):
                raise VisualizationError(f"invalid preparation {table_id} artifact path")
            path = _safe_artifact(root, value, table_id, artifact_hashes)
            tables.append(
                _table(
                    table_id,
                    table_id.title(),
                    path,
                    units=units if table_id == "table" else None,
                )
            )

    scenarios = manifest.get("scenarios")
    scenario_items = scenarios.get("scenarios") if isinstance(scenarios, dict) else None
    if isinstance(scenario_items, list):
        for scenario in scenario_items:
            if not isinstance(scenario, dict) or not isinstance(scenario.get("name"), str):
                continue
            name = str(scenario["name"])
            hashes = scenario.get("partition_artifact_hashes")
            partition_hashes = hashes if isinstance(hashes, dict) else {}
            artifacts = scenario.get("partition_artifacts")
            if not isinstance(artifacts, list):
                continue
            for value in artifacts:
                if not isinstance(value, str) or not value.endswith(".parquet"):
                    continue
                path = _safe_artifact(root, value, f"scenario {name}", partition_hashes)
                partition = path.stem
                table_id = f"scenario.{name}.{partition}"
                tables.append(_table(table_id, f"{name}: {partition}", path, units=units))
    return tuple(tables)


def _preparation_arrays(manifest: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    arrays: list[dict[str, Any]] = []
    arrays.extend(_array_export_entries(manifest.get("array_exports")))
    scenarios = manifest.get("scenarios")
    scenario_items = scenarios.get("scenarios") if isinstance(scenarios, dict) else None
    if isinstance(scenario_items, list):
        for scenario in scenario_items:
            if not isinstance(scenario, dict):
                continue
            arrays.extend(_array_export_entries(scenario.get("array_exports")))
    return tuple(arrays)


def _array_export_entries(value: object) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        exports = value.get("exports")
        return (
            [item for item in exports if isinstance(item, dict)]
            if isinstance(exports, list)
            else []
        )
    if isinstance(value, list):
        result: list[dict[str, Any]] = []
        for item in value:
            result.extend(_array_export_entries(item))
        return result
    return []


def _table(
    table_id: str,
    label: str,
    path: Path,
    *,
    units: dict[str, str] | None = None,
) -> ResolvedTable:
    return ResolvedTable(
        table_id=table_id,
        label=label,
        path=path,
        source_format=path.suffix.removeprefix("."),
        units=units or {},
        sha256=sha256_file(path),
    )


def _preparation_units(manifest: dict[str, Any]) -> dict[str, str]:
    mapping = manifest.get("semantic_field_mapping")
    if not isinstance(mapping, dict):
        return {}
    return {
        str(field): str(details["unit"])
        for field, details in mapping.items()
        if isinstance(details, dict) and details.get("unit") is not None
    }


def _safe_artifact(
    root: Path,
    relative_value: str,
    label: str,
    artifact_hashes: dict[str, Any],
) -> Path:
    relative = Path(relative_value)
    if relative.is_absolute() or ".." in relative.parts:
        raise VisualizationError(f"{label} path must remain relative to its bundle")
    if root.is_symlink():
        raise VisualizationError(f"{label} bundle root must not be a symbolic link")
    resolved_root = root.resolve()
    current = resolved_root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise VisualizationError(f"{label} path contains a symbolic link")
    try:
        path = current.resolve(strict=True)
        path.relative_to(resolved_root)
        info = path.stat()
    except (OSError, ValueError) as exc:
        raise VisualizationError(f"{label} artifact is missing or escapes its bundle") from exc
    if not stat.S_ISREG(info.st_mode):
        raise VisualizationError(f"{label} artifact is not a regular file")
    digest = sha256_file(path)
    expected = artifact_hashes.get(relative.as_posix())
    if isinstance(expected, str) and digest != expected:
        raise VisualizationError(f"{label} artifact hash mismatch")
    return path


def _contained_directory(root: Path, value: Path, label: str) -> Path:
    if root.is_symlink():
        raise VisualizationError("sweep bundle root must not be a symbolic link")
    path = value if value.is_absolute() else root / value
    resolved_root = root.resolve()
    try:
        relative = path.absolute().relative_to(root.absolute())
    except ValueError as exc:
        raise VisualizationError(f"{label} escapes the sweep bundle") from exc
    current = resolved_root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise VisualizationError(f"{label} path contains a symbolic link")
    try:
        current.resolve(strict=True).relative_to(resolved_root)
    except (OSError, ValueError) as exc:
        raise VisualizationError(f"{label} is missing or escapes the sweep bundle") from exc
    if not current.is_dir():
        raise VisualizationError(f"{label} is not a directory")
    return current


def _preferred_dataset(root: Path) -> Path:
    for name in ("dataset.parquet", "dataset.csv"):
        path = root / name
        if path.is_file() and not path.is_symlink():
            return path
    raise VisualizationError(f"child run has no dataset CSV or Parquet file: {root}")


def _read_json(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink():
        raise VisualizationError(f"{label} must not be a symbolic link: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VisualizationError(f"could not read {label} {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise VisualizationError(f"{label} root must be an object")
    return cast(dict[str, Any], value)


def _catalog_revision(
    source_kind: str,
    tables: tuple[ResolvedTable, ...],
    controls: dict[str, Any],
) -> str:
    value = {
        "source_kind": source_kind,
        "tables": [
            {
                "id": item.table_id,
                "sha256": item.sha256,
                **(
                    {"metadata_sha256": item.metadata_sha256}
                    if item.metadata_sha256 is not None
                    else {}
                ),
            }
            for item in tables
        ],
        "controls": controls,
    }
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _control_hashes(root: Path, names: tuple[str, ...]) -> dict[str, dict[str, Any]]:
    return {
        name: _control_descriptor(path)
        for name in names
        if (path := root / name).is_file() and not path.is_symlink()
    }


def _control_descriptor(path: Path) -> dict[str, Any]:
    info = path.stat(follow_symlinks=False)
    return {
        "path": str(path.resolve(strict=True)),
        "sha256": sha256_file(path),
        "device": info.st_dev,
        "inode": info.st_ino,
        "size": info.st_size,
        "modified_ns": info.st_mtime_ns,
    }


def _file_identity_descriptor(path: Path, digest: str) -> dict[str, object]:
    info = path.stat(follow_symlinks=False)
    return {
        "sha256": digest,
        "device": info.st_dev,
        "inode": info.st_ino,
        "size": info.st_size,
        "modified_ns": info.st_mtime_ns,
    }


def _preparation_eligibility(
    source: Path,
    source_kind: str,
    catalog: ResolvedCatalog,
    summary: dict[str, Any],
) -> tuple[bool, str, dict[str, Any] | None, dict[str, Any] | None]:
    if source_kind == "preparation":
        return False, "prepared bundles cannot be used as preparation sources", None, None
    if source_kind == "dataset" and not source.is_dir():
        return (
            False,
            "standalone CSV and Parquet files cannot be used as preparation sources",
            None,
            None,
        )
    descriptor = _preparation_descriptor(source, source_kind, catalog)
    try:
        loaded = load_preparation_source(
            source,
            allow_partial_sweep=True,
            accepted_descriptor=descriptor,
        )
    except ConfigError as exc:
        return False, str(exc), None, None
    return (
        True,
        "",
        descriptor,
        _preparation_profile(
            loaded,
            inspection_revision=catalog.revision,
            inspection_summary=summary,
        ),
    )


def _preparation_profile(
    source_data: LoadedPreparationSource,
    *,
    inspection_revision: str,
    inspection_summary: dict[str, Any],
) -> dict[str, Any]:
    fields = preparation_field_capabilities(source_data.tables)
    numeric = [_field_profile(field) for field in fields.numeric]
    categorical = [_field_profile(field) for field in fields.categorical]
    auxiliary = [_field_profile(field) for field in fields.auxiliary]
    available_models = _available_models(source_data)
    declared_models = _string_values(source_data.source_identity.get("models"))
    reference_model = inspection_summary.get("reference_model")
    if not isinstance(reference_model, str):
        reference_model = available_models[0] if len(available_models) == 1 else None
    completion_status = _completion_status(source_data)
    model_holdout_available = (
        source_data.source_kind == "model_sweep" and len(available_models) >= 2
    )
    return {
        "profile_schema_version": 1,
        "source_path": str(source_data.requested_path),
        "source_kind": source_data.source_kind,
        "inspection_revision": inspection_revision,
        "source_identity": copy.deepcopy(source_data.source_identity),
        "completion": {
            "status": completion_status,
            "partial": source_data.partial_sweep_source,
            "included_child_models": list(source_data.included_child_models),
            "missing_child_models": list(source_data.missing_child_models),
        },
        "available_models": available_models,
        "declared_models": declared_models,
        "reference_model": reference_model,
        "numeric_candidates": numeric,
        "target_candidates": copy.deepcopy(numeric),
        "categorical_candidates": categorical,
        "auxiliary_candidates": auxiliary,
        "observed_category_values": _observed_category_values(source_data),
        "derived_features": _derived_feature_profiles(source_data),
        "model_holdout": {
            "available": model_holdout_available,
            "reason": (
                ""
                if model_holdout_available
                else _model_holdout_unavailable_reason(source_data, available_models)
            ),
        },
        "reference_context": assess_reference_context(source_data),
    }


def _field_profile(field: ResolvedField) -> dict[str, Any]:
    definition = PROPERTY_REGISTRY.get(field.semantic_name)
    return {
        "name": field.semantic_name,
        "column": field.column,
        "unit": field.unit,
        "source": field.source,
        "reference_dependent": bool(definition is not None and definition.reference_dependent),
    }


def _available_models(source_data: LoadedPreparationSource) -> list[str]:
    return list(
        dict.fromkeys(
            model
            for table in source_data.tables
            if (model := table.backend_model) is not None and model
        )
    )


def _completion_status(source_data: LoadedPreparationSource) -> str:
    if source_data.source_kind == "model_sweep":
        value = source_data.source_identity.get("sweep_status")
    else:
        value = source_data.tables[0].metadata.get("run_status")
    return value if isinstance(value, str) and value else "completed"


def _observed_category_values(
    source_data: LoadedPreparationSource,
) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for field, column in CATEGORICAL_FIELDS.items():
        values = {
            str(value)
            for table in source_data.tables
            if column in table.frame.columns
            for value in table.frame[column].dropna().tolist()
        }
        if values:
            result[field] = sorted(values)
    return result


def _derived_feature_profiles(
    source_data: LoadedPreparationSource,
) -> list[dict[str, Any]]:
    total_rows = sum(len(table.frame) for table in source_data.tables)
    profiles: list[dict[str, Any]] = []
    for name, definition in DERIVED_FEATURE_REGISTRY.items():
        ready_rows = 0
        reason_codes: set[str] = set()
        missing_dependencies: set[str] = set()
        for table in source_data.tables:
            for _, row in table.frame.iterrows():
                try:
                    _, reasons, missing = compute_derived_value(
                        cast(DerivedFeature, name),
                        row,
                        table,
                    )
                except (TypeError, ValueError, OverflowError):
                    reasons = ["invalid_derived_dependency"]
                    missing = list(definition.dependencies)
                if reasons:
                    reason_codes.update(reasons)
                    missing_dependencies.update(missing)
                else:
                    ready_rows += 1
        if ready_rows == total_rows and total_rows:
            status = "ready"
            reason = ""
        elif ready_rows:
            status = "partial"
            reason = (
                f"Available for {ready_rows} of {total_rows} source rows; "
                "other rows would be excluded."
            )
        else:
            status = "unavailable"
            reason = (
                "The source contains no rows with every required dependency."
                if total_rows
                else "The source contains no rows."
            )
        profiles.append(
            {
                "name": name,
                "status": status,
                "available": ready_rows > 0,
                "ready_row_count": ready_rows,
                "source_row_count": total_rows,
                "reason": reason,
                "reason_codes": sorted(reason_codes),
                "missing_dependencies": [
                    dependency
                    for dependency in definition.dependencies
                    if dependency in missing_dependencies
                ],
                "dependencies": list(definition.dependencies),
                "unit": definition.unit,
            }
        )
    return profiles


def _model_holdout_unavailable_reason(
    source_data: LoadedPreparationSource,
    available_models: list[str],
) -> str:
    if source_data.source_kind != "model_sweep":
        return "Model holdout scenarios require a model-sweep source."
    if len(available_models) < 2:
        return "Model holdout scenarios require at least two available sweep child models."
    return ""


def _string_values(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _preparation_descriptor(
    source: Path,
    source_kind: str,
    catalog: ResolvedCatalog,
) -> dict[str, Any]:
    preparation_kind = "model_sweep" if source_kind == "model_sweep" else "dataset_run"
    return {
        "source_path": str(source.resolve(strict=True)),
        "source_kind": preparation_kind,
        "inspection_revision": catalog.revision,
        "controls": catalog.controls,
        "tables": [table.private_descriptor() for table in catalog.tables],
    }
