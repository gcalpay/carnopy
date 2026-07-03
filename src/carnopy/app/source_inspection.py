from __future__ import annotations

import hashlib
import json
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from carnopy.inspection import PreparationInspection, SweepInspection, inspect_source
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

    def public_descriptor(self) -> dict[str, object]:
        return {
            "id": self.table_id,
            "label": self.label,
            "format": self.source_format,
            "sha256": self.sha256,
        }


@dataclass(frozen=True)
class ResolvedInspection:
    source: Path
    source_kind: str
    summary: dict[str, Any]
    revision: str
    tables: tuple[ResolvedTable, ...]
    arrays: tuple[dict[str, Any], ...]

    def public_payload(self) -> dict[str, Any]:
        return {
            "source": str(self.source),
            "source_kind": self.source_kind,
            "revision": self.revision,
            "summary": self.summary,
            "tables": [table.public_descriptor() for table in self.tables],
            "arrays": list(self.arrays),
        }


@dataclass(frozen=True)
class ResolvedCatalog:
    source_kind: str
    revision: str
    tables: tuple[ResolvedTable, ...]
    arrays: tuple[dict[str, Any], ...]


def inspect_for_app(source: str | Path) -> ResolvedInspection:
    requested = Path(source).expanduser().absolute()
    catalog = _resolve_catalog(requested)
    inspection = inspect_source(requested)
    if isinstance(inspection, PlotInspection):
        kind = "dataset"
    elif isinstance(inspection, SweepInspection):
        kind = "model_sweep"
    elif isinstance(inspection, PreparationInspection):
        kind = "preparation"
    else:  # pragma: no cover - closed inspection union
        raise VisualizationError("unsupported inspection result")
    if kind != catalog.source_kind:
        raise VisualizationError("inspection source classification changed during inspection")
    summary = inspection.to_dict()
    return ResolvedInspection(
        source=requested,
        source_kind=kind,
        summary=summary,
        revision=catalog.revision,
        tables=catalog.tables,
        arrays=catalog.arrays,
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
        )
    table = _dataset_table(source)
    controls = _control_hashes(table.path.parent, ("metadata.json", "report.json"))
    return ResolvedCatalog(
        "dataset",
        _catalog_revision("dataset", (table,), controls),
        (table,),
        (),
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
            child_metadata = _read_json(child_root / "metadata.json", "child metadata")
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
    controls: dict[str, str],
) -> str:
    value = {
        "source_kind": source_kind,
        "tables": [{"id": item.table_id, "sha256": item.sha256} for item in tables],
        "controls": controls,
    }
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _control_hashes(root: Path, names: tuple[str, ...]) -> dict[str, str]:
    return {
        name: sha256_file(path)
        for name in names
        if (path := root / name).is_file() and not path.is_symlink()
    }
