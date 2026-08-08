from __future__ import annotations

import hashlib
import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import IO, Any, Literal, cast

import pandas as pd

from carnopy.domain.failures import ConfigError

SourceKind = Literal["dataset_run", "model_sweep_child"]


@dataclass(frozen=True)
class SourceArtifactDescriptor:
    path: Path
    sha256: str
    device: int
    inode: int
    size: int
    modified_ns: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "sha256": self.sha256,
            "device": self.device,
            "inode": self.inode,
            "size": self.size,
            "modified_ns": self.modified_ns,
        }


@dataclass(frozen=True)
class SourceTable:
    kind: SourceKind
    root: Path
    run_directory: Path
    artifact_path: Path
    artifact_relative_path: str
    artifact_sha256: str
    artifact_descriptor: SourceArtifactDescriptor
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

    def revision_descriptor(self) -> dict[str, Any]:
        return {
            "source_path": str(self.requested_path),
            "source_kind": self.source_kind,
            "source_identity": self.source_identity,
            "tables": [
                {
                    "artifact": table.artifact_relative_path,
                    **table.artifact_descriptor.as_dict(),
                }
                for table in self.tables
            ],
        }


def load_preparation_source(
    source: str | Path,
    *,
    allow_partial_sweep: bool,
    accepted_descriptor: dict[str, Any] | None = None,
) -> LoadedPreparationSource:
    requested_input = Path(source).expanduser().absolute()
    if requested_input.is_symlink():
        raise ConfigError("preparation source must not be a symbolic link")
    try:
        requested = requested_input.resolve(strict=True)
    except OSError as exc:
        raise ConfigError(f"preparation source is unavailable: {requested_input}") from exc
    if not requested.is_dir():
        raise ConfigError(
            "preparation source must be a dataset run directory or model-sweep bundle"
        )
    if (requested / "sweep.normalized.json").is_file() and (requested / "models").is_dir():
        loaded = _load_sweep_source(
            requested,
            allow_partial_sweep=allow_partial_sweep,
            accepted_descriptor=accepted_descriptor,
        )
    else:
        loaded = _load_dataset_run_source(
            requested,
            accepted_descriptor=accepted_descriptor,
        )
    _verify_accepted_source_identity(loaded, accepted_descriptor)
    return loaded


def verify_loaded_source_unchanged(source: LoadedPreparationSource) -> None:
    """Revalidate every consumed table against its accepted descriptor."""
    for table in source.tables:
        _verify_artifact_unchanged(table.artifact_descriptor)


def _load_dataset_run_source(
    source: Path,
    *,
    accepted_descriptor: dict[str, Any] | None,
) -> LoadedPreparationSource:
    metadata = _read_json(source / "metadata.json", label="dataset metadata")
    artifact = _select_dataset_artifact(source)
    frame, descriptor = _read_verified_dataset(
        artifact,
        metadata,
        accepted_descriptor=accepted_descriptor,
    )
    run_id = _metadata_text(metadata, "run_id")
    table = SourceTable(
        kind="dataset_run",
        root=source,
        run_directory=source,
        artifact_path=artifact,
        artifact_relative_path=artifact.name,
        artifact_sha256=descriptor.sha256,
        artifact_descriptor=descriptor,
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
            "artifact_sha256": descriptor.sha256,
        },
        partial_sweep_source=False,
        included_child_models=(),
        missing_child_models=(),
    )


def _load_sweep_source(
    source: Path,
    *,
    allow_partial_sweep: bool,
    accepted_descriptor: dict[str, Any] | None,
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
        if model_root.is_symlink():
            raise ConfigError(f"sweep model {model!r} directory must not be a symbolic link")
        if not model_root.is_dir():
            continue
        child_dirs = sorted(path for path in model_root.iterdir() if path.is_dir())
        if any(path.is_symlink() for path in child_dirs):
            raise ConfigError(f"sweep model {model!r} child directory must not be a symlink")
        if not child_dirs:
            continue
        if len(child_dirs) != 1:
            raise ConfigError(f"sweep model {model!r} must contain exactly one child run")
        child = child_dirs[0]
        child_metadata = _read_json(child / "metadata.json", label=f"{model} child metadata")
        artifact = _select_dataset_artifact(child)
        frame, descriptor = _read_verified_dataset(
            artifact,
            child_metadata,
            accepted_descriptor=accepted_descriptor,
        )
        relative = _relative_posix(artifact, source)
        tables.append(
            SourceTable(
                kind="model_sweep_child",
                root=source,
                run_directory=child,
                artifact_path=artifact,
                artifact_relative_path=relative,
                artifact_sha256=descriptor.sha256,
                artifact_descriptor=descriptor,
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
    for name in ("dataset.parquet", "dataset.csv"):
        candidate = run_directory / name
        if candidate.is_symlink():
            raise ConfigError(f"source dataset must not be a symbolic link: {candidate}")
        try:
            info = candidate.stat(follow_symlinks=False)
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise ConfigError(f"could not inspect source dataset {candidate}: {exc}") from exc
        if stat.S_ISREG(info.st_mode):
            return candidate
        raise ConfigError(f"source dataset is not a regular file: {candidate}")
    raise ConfigError(
        f"source run contains neither dataset.parquet nor dataset.csv: {run_directory}"
    )


def _read_verified_dataset(
    path: Path,
    metadata: dict[str, Any],
    *,
    accepted_descriptor: dict[str, Any] | None,
) -> tuple[pd.DataFrame, SourceArtifactDescriptor]:
    expected_digest = _metadata_artifact_digest(path, metadata)
    accepted = _accepted_table_descriptor(path, accepted_descriptor)
    try:
        with path.open("rb") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode):
                raise ConfigError(f"source dataset is not a regular file: {path}")
            digest = _hash_stream(stream)
            descriptor = SourceArtifactDescriptor(
                path=path.resolve(strict=True),
                sha256=digest,
                device=before.st_dev,
                inode=before.st_ino,
                size=before.st_size,
                modified_ns=before.st_mtime_ns,
            )
            if digest != expected_digest:
                raise ConfigError(f"source artifact hash mismatch for {path.name}")
            _compare_accepted_table(descriptor, accepted)
            stream.seek(0)
            frame = _read_dataset_stream(path, stream)
            after = os.fstat(stream.fileno())
            if _stat_identity(after) != _stat_identity(before):
                raise ConfigError(f"source artifact changed while loading {path.name}")
            stream.seek(0)
            if _hash_stream(stream) != digest:
                raise ConfigError(f"source artifact digest changed while loading {path.name}")
    except ConfigError:
        raise
    except OSError as exc:
        raise ConfigError(f"could not load source dataset {path}: {exc}") from exc
    _verify_artifact_unchanged(descriptor)
    return frame, descriptor


def _read_dataset_stream(path: Path, stream: IO[bytes]) -> pd.DataFrame:
    try:
        if path.suffix == ".parquet":
            return pd.read_parquet(stream)
        return pd.read_csv(stream)
    except Exception as exc:
        raise ConfigError(f"could not load source dataset {path}: {exc}") from exc


def _hash_stream(stream: IO[bytes]) -> str:
    digest = hashlib.sha256()
    for block in iter(lambda: stream.read(1024 * 1024), b""):
        digest.update(block)
    return digest.hexdigest()


def _verify_artifact_unchanged(descriptor: SourceArtifactDescriptor) -> None:
    path = descriptor.path
    if path.is_symlink():
        raise ConfigError(f"source artifact was replaced by a symbolic link: {path}")
    try:
        path_info = path.stat(follow_symlinks=False)
        with path.open("rb") as stream:
            descriptor_info = os.fstat(stream.fileno())
            digest = _hash_stream(stream)
    except OSError as exc:
        raise ConfigError(f"could not revalidate source artifact {path}: {exc}") from exc
    expected_stat = (
        descriptor.device,
        descriptor.inode,
        descriptor.size,
        descriptor.modified_ns,
    )
    if (
        _stat_identity(path_info) != expected_stat
        or _stat_identity(descriptor_info) != expected_stat
    ):
        raise ConfigError(f"source artifact changed after loading: {path.name}")
    if digest != descriptor.sha256:
        raise ConfigError(f"source artifact digest changed after loading: {path.name}")


def _metadata_artifact_digest(path: Path, metadata: dict[str, Any]) -> str:
    artifact_hashes = metadata.get("artifact_hashes")
    if not isinstance(artifact_hashes, dict):
        raise ConfigError("source metadata does not contain artifact_hashes")
    expected = artifact_hashes.get(path.name)
    if not isinstance(expected, str):
        raise ConfigError(f"source metadata does not record a hash for {path.name}")
    return expected


def _accepted_table_descriptor(
    path: Path,
    accepted_descriptor: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if accepted_descriptor is None:
        return None
    tables = accepted_descriptor.get("tables")
    if not isinstance(tables, list):
        raise ConfigError("accepted inspection descriptor is missing table identities")
    resolved = str(path.resolve(strict=True))
    for value in tables:
        if isinstance(value, dict) and value.get("path") == resolved:
            return value
    raise ConfigError(f"source table is absent from the accepted inspection: {path.name}")


def _compare_accepted_table(
    descriptor: SourceArtifactDescriptor,
    accepted: dict[str, Any] | None,
) -> None:
    if accepted is None:
        return
    expected_sha = accepted.get("sha256")
    if expected_sha != descriptor.sha256:
        raise ConfigError(f"source table changed after inspection: {descriptor.path.name}")
    for key, actual in (
        ("device", descriptor.device),
        ("inode", descriptor.inode),
        ("size", descriptor.size),
        ("modified_ns", descriptor.modified_ns),
    ):
        expected = accepted.get(key)
        if expected is not None and expected != actual:
            raise ConfigError(
                f"source table identity changed after inspection: {descriptor.path.name}"
            )


def _verify_accepted_source_identity(
    loaded: LoadedPreparationSource,
    accepted_descriptor: dict[str, Any] | None,
) -> None:
    if accepted_descriptor is None:
        return
    expected_path = accepted_descriptor.get("source_path")
    expected_kind = accepted_descriptor.get("source_kind")
    if expected_path != str(loaded.requested_path) or expected_kind != loaded.source_kind:
        raise ConfigError("preparation source no longer matches the accepted inspection")


def _stat_identity(value: os.stat_result) -> tuple[int, int, int, int]:
    return value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns


def _read_json(path: Path, *, label: str) -> dict[str, Any]:
    if path.is_symlink():
        raise ConfigError(f"{label} must not be a symbolic link: {path}")
    try:
        info = path.stat(follow_symlinks=False)
        if not stat.S_ISREG(info.st_mode):
            raise ConfigError(f"{label} is not a regular file: {path}")
        value = json.loads(path.read_text(encoding="utf-8"))
    except ConfigError:
        raise
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
