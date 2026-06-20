from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from carnopy.domain.failures import OutputError


@dataclass(frozen=True)
class RunLayout:
    output_root: Path
    staging_directory: Path
    final_directory: Path


def create_run_layout(
    *,
    output_root: Path,
    mode: str,
    spec_id: str,
    run_id: str,
    created_at: datetime,
) -> RunLayout:
    try:
        output_root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise OutputError(f"could not create output root {output_root}: {exc}") from exc
    timestamp = created_at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    name = f"{timestamp}_{mode}_{spec_id.removeprefix('spec-')[:12]}_{run_id[:8]}"
    final_directory = output_root / name
    staging_directory = output_root / f".{name}.staging"
    if final_directory.exists() or staging_directory.exists():
        raise OutputError(f"immutable run path already exists: {final_directory}")
    try:
        staging_directory.mkdir()
    except OSError as exc:
        raise OutputError(f"could not create staging directory: {exc}") from exc
    return RunLayout(output_root, staging_directory, final_directory)


def finalize_run_layout(layout: RunLayout) -> None:
    if layout.final_directory.exists():
        raise OutputError(f"refusing to overwrite existing run directory {layout.final_directory}")
    try:
        layout.staging_directory.rename(layout.final_directory)
    except OSError as exc:
        raise OutputError(f"could not finalize run directory: {exc}") from exc
