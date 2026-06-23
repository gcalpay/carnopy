from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from carnopy.domain.failures import OutputError


@dataclass(frozen=True)
class SweepLayout:
    output_root: Path
    staging_directory: Path
    final_directory: Path


def create_sweep_layout(
    *,
    output_root: Path,
    sweep_run_id: str,
    created_at: datetime,
) -> SweepLayout:
    try:
        output_root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise OutputError(f"could not create sweep output root {output_root}: {exc}") from exc
    timestamp = created_at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    try:
        run_prefix = UUID(sweep_run_id).hex[:8]
    except ValueError as exc:
        raise OutputError(f"invalid sweep run_id for layout: {sweep_run_id}") from exc
    name = f"{timestamp}_model_sweep_{run_prefix}"
    final_directory = output_root / name
    staging_directory = output_root / f".{name}.staging"
    if final_directory.exists() or staging_directory.exists():
        raise OutputError(f"immutable sweep path already exists: {final_directory}")
    try:
        staging_directory.mkdir()
    except OSError as exc:
        raise OutputError(f"could not create sweep staging directory: {exc}") from exc
    return SweepLayout(output_root, staging_directory, final_directory)


def finalize_sweep_layout(layout: SweepLayout) -> None:
    if layout.final_directory.exists():
        raise OutputError(
            f"refusing to overwrite existing sweep directory {layout.final_directory}"
        )
    try:
        layout.staging_directory.rename(layout.final_directory)
    except OSError as exc:
        raise OutputError(f"could not finalize sweep directory: {exc}") from exc
