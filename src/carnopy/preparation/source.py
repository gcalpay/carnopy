from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Literal, cast

import pandas as pd

from carnopy.domain.failures import ConfigError
from carnopy.provenance import sha256_file

SourceKind = Literal["dataset_run", "model_sweep_child"]


@dataclass(frozen=True)
class SourceTable:
    kind: SourceKind
    root: Path
    run_directory: Path
    artifact_path: Path
    artifact_relative_path: str
    artifact_sha256: str
    frame: pd.DataFrame
    metadata: dict[str, Any]
    run_id: str
    backend_model: str | None
    sweep_id: str | None = None
    sweep_run_id: str | None = None


@dataclass(frozen=True)
class LoadedPreparationSource:
    requested_path: Path
    source_kind: Literal["dataset_run", "model_sweep"]
    tables: tuple[SourceTable, ...]
    source_identity: dict[str, Any]
    partial_sweep_source: bool
    included_child_models: tuple[str, ...]
    missing_child_models: tuple[str, ...]


def load_preparation_source(
    source: str | Path,
    *,
    allow_partial_sweep: bool,
) -> LoadedPreparationSource:
    requested = Path(source).expanduser().resolve()
    if not requested.is_dir():
        raise ConfigError(
            "preparation source must be a dataset run directory or model-sweep bundle"
        )
    if (requested / "sweep.normalized.json").is_file() and (requested / "models").is_dir():
        return _load_sweep_source(requested, allow_partial_sweep=allow_partial_sweep)
    return _load_dataset_run_source(requested)


def _load_dataset_run_source(source: Path) -> LoadedPreparationSource:
    metadata = _read_json(source / "metadata.json", label="dataset metadata")
    artifact = _select_dataset_artifact(source)
    artifact_hash = _verify_dataset_hash(artifact, metadata)
    frame = _read_dataset(artifact)
    run_id = _metadata_text(metadata, "run_id")
    table = SourceTable(
        kind="dataset_run",
        root=source,
        run_directory=source,
        artifact_path=artifact,
        artifact_relative_path=artifact.name,
        artifact_sha256=artifact_hash,
        frame=frame,
        metadata=metadata,
        run_id=run_id,
        backend_model=_optional_metadata_text(metadata, "backend_model"),
    )
    return LoadedPreparationSource(
        requested_path=source,
        source_kind="dataset_run",
        tables=(table,),
        source_identity={
            "source_kind": "dataset_run",
            "run_id": run_id,
            "spec_id": metadata.get("spec_id"),
            "generation_context_id": metadata.get("generation_context_id"),
            "artifact": artifact.name,
            "artifact_sha256": artifact_hash,
        },
        partial_sweep_source=False,
        included_child_models=(),
        missing_child_models=(),
    )


def _load_sweep_source(
    source: Path,
    *,
    allow_partial_sweep: bool,
) -> LoadedPreparationSource:
    metadata = _read_json(source / "metadata.json", label="sweep metadata")
    status = _metadata_text(metadata, "sweep_status")
    models = _metadata_string_tuple(metadata, "models")
    child_runs = metadata.get("child_runs")
    if not isinstance(child_runs, list):
        raise ConfigError("sweep metadata child_runs must be a list")
    included = tuple(
        str(item.get("backend_model"))
        for item in child_runs
        if isinstance(item, dict) and isinstance(item.get("backend_model"), str)
    )
    missing = tuple(model for model in models if model not in set(included))
    partial = status != "completed" or bool(missing)
    if partial and not allow_partial_sweep:
        raise ConfigError(
            "model-sweep source is incomplete; set source_policy.allow_partial_sweep: true "
            "to prepare completed child runs"
        )
    tables: list[SourceTable] = []
    for model in models:
        model_root = source / "models" / model
        if not model_root.is_dir():
            continue
        child_dirs = sorted(path for path in model_root.iterdir() if path.is_dir())
        if not child_dirs:
            continue
        if len(child_dirs) != 1:
            raise ConfigError(f"sweep model {model!r} must contain exactly one child run")
        child = child_dirs[0]
        child_metadata = _read_json(child / "metadata.json", label=f"{model} child metadata")
        artifact = _select_dataset_artifact(child)
        artifact_hash = _verify_dataset_hash(artifact, child_metadata)
        frame = _read_dataset(artifact)
        relative = _relative_posix(artifact, source)
        tables.append(
            SourceTable(
                kind="model_sweep_child",
                root=source,
                run_directory=child,
                artifact_path=artifact,
                artifact_relative_path=relative,
                artifact_sha256=artifact_hash,
                frame=frame,
                metadata=child_metadata,
                run_id=_metadata_text(child_metadata, "run_id"),
                backend_model=_optional_metadata_text(child_metadata, "backend_model") or model,
                sweep_id=_optional_metadata_text(metadata, "sweep_id"),
                sweep_run_id=_optional_metadata_text(metadata, "sweep_run_id"),
            )
        )
    if not tables:
        raise ConfigError("model-sweep source contains no readable completed child runs")
    return LoadedPreparationSource(
        requested_path=source,
        source_kind="model_sweep",
        tables=tuple(tables),
        source_identity={
            "source_kind": "model_sweep",
            "sweep_id": metadata.get("sweep_id"),
            "sweep_run_id": metadata.get("sweep_run_id"),
            "sweep_status": status,
            "models": list(models),
        },
        partial_sweep_source=partial,
        included_child_models=tuple(table.backend_model or "" for table in tables),
        missing_child_models=missing,
    )


def _select_dataset_artifact(run_directory: Path) -> Path:
    parquet = run_directory / "dataset.parquet"
    csv = run_directory / "dataset.csv"
    if parquet.is_file():
        return parquet
    if csv.is_file():
        return csv
    raise ConfigError(
        f"source run contains neither dataset.parquet nor dataset.csv: {run_directory}"
    )


def _read_dataset(path: Path) -> pd.DataFrame:
    try:
        if path.suffix == ".parquet":
            return pd.read_parquet(path)
        return pd.read_csv(path)
    except Exception as exc:
        raise ConfigError(f"could not load source dataset {path}: {exc}") from exc


def _verify_dataset_hash(path: Path, metadata: dict[str, Any]) -> str:
    try:
        digest = sha256_file(path)
    except OSError as exc:
        raise ConfigError(f"could not hash source dataset {path}: {exc}") from exc
    artifact_hashes = metadata.get("artifact_hashes")
    if not isinstance(artifact_hashes, dict):
        raise ConfigError("source metadata does not contain artifact_hashes")
    expected = artifact_hashes.get(path.name)
    if not isinstance(expected, str):
        raise ConfigError(f"source metadata does not record a hash for {path.name}")
    if expected != digest:
        raise ConfigError(f"source artifact hash mismatch for {path.name}")
    return digest


def _read_json(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"could not read {label} {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ConfigError(f"{label} root must be an object")
    return cast(dict[str, Any], value)


def _metadata_text(metadata: dict[str, Any], key: str) -> str:
    value = metadata.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"source metadata is missing required text field {key!r}")
    return value


def _optional_metadata_text(metadata: dict[str, Any], key: str) -> str | None:
    value = metadata.get(key)
    if isinstance(value, str) and value.strip():
        return value
    return None


def _metadata_string_tuple(metadata: dict[str, Any], key: str) -> tuple[str, ...]:
    value = metadata.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ConfigError(f"sweep metadata {key!r} must be a list of strings")
    return tuple(value)


def _relative_posix(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return PurePosixPath(path.name).as_posix()
