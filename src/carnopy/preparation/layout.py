from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from carnopy.domain.failures import OutputError


@dataclass(frozen=True)
class PreparationLayout:
    staging_directory: Path
    final_directory: Path


def create_preparation_layout(
    output_root: Path,
    *,
    preparation_run_id: str,
    created_at: datetime,
) -> PreparationLayout:
    try:
        output_root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise OutputError(f"could not create preparation output root {output_root}: {exc}") from exc
    timestamp = created_at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    try:
        prefix = UUID(preparation_run_id).hex[:8]
    except ValueError as exc:
        raise OutputError(f"invalid preparation_run_id: {preparation_run_id}") from exc
    name = f"{timestamp}_preparation_{prefix}"
    final = output_root / name
    staging = output_root / f".{name}.staging"
    if final.exists() or staging.exists():
        raise OutputError(f"immutable preparation path already exists: {final}")
    try:
        staging.mkdir()
    except OSError as exc:
        raise OutputError(f"could not create preparation staging directory: {exc}") from exc
    return PreparationLayout(staging, final)


def finalize_preparation_layout(layout: PreparationLayout) -> None:
    if layout.final_directory.exists():
        raise OutputError(f"refusing to overwrite preparation directory {layout.final_directory}")
    try:
        layout.staging_directory.rename(layout.final_directory)
    except OSError as exc:
        raise OutputError(f"could not finalize preparation directory: {exc}") from exc


def cleanup_staging(path: Path) -> None:
    if not path.exists():
        return
    for child in sorted(path.rglob("*"), reverse=True):
        try:
            if child.is_file() or child.is_symlink():
                child.unlink()
            elif child.is_dir():
                child.rmdir()
        except OSError:
            return
    try:
        path.rmdir()
    except OSError:
        return
