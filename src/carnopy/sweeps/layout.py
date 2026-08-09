from __future__ import annotations

import shutil
import stat
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from carnopy.domain.failures import OutputError
from carnopy.outputs.finalization import rename_directory_no_replace


@dataclass(frozen=True)
class SweepLayout:
    output_root: Path
    staging_directory: Path
    final_directory: Path
    staging_device: int
    staging_inode: int


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
    timestamp = created_at.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
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
        staging_info = staging_directory.stat(follow_symlinks=False)
    except OSError as exc:
        raise OutputError(f"could not create sweep staging directory: {exc}") from exc
    return SweepLayout(
        output_root,
        staging_directory,
        final_directory,
        staging_info.st_dev,
        staging_info.st_ino,
    )


def finalize_sweep_layout(layout: SweepLayout) -> None:
    if layout.final_directory.exists() or layout.final_directory.is_symlink():
        raise OutputError(
            f"refusing to overwrite existing sweep directory {layout.final_directory}"
        )
    _verify_sweep_staging(layout)
    try:
        rename_directory_no_replace(layout.staging_directory, layout.final_directory)
    except OSError as exc:
        raise OutputError(f"could not finalize sweep directory: {exc}") from exc


def cleanup_sweep_layout(layout: SweepLayout) -> None:
    staging = layout.staging_directory
    if not staging.exists() and not staging.is_symlink():
        return
    _verify_sweep_staging(layout)
    try:
        shutil.rmtree(staging)
    except OSError as exc:
        raise OutputError(f"could not clean sweep staging directory {staging}: {exc}") from exc


def _verify_sweep_staging(layout: SweepLayout) -> None:
    staging = layout.staging_directory
    if staging.is_symlink():
        raise OutputError(f"refusing to use sweep staging symlink {staging}")
    try:
        root = layout.output_root.resolve(strict=True)
        if staging.parent.resolve(strict=True) != root:
            raise OutputError(f"sweep staging directory escapes output root {staging}")
        info = staging.stat(follow_symlinks=False)
    except OutputError:
        raise
    except OSError as exc:
        raise OutputError(f"could not inspect sweep staging directory {staging}: {exc}") from exc
    if not stat.S_ISDIR(info.st_mode):
        raise OutputError(f"refusing to use non-directory sweep staging path {staging}")
    if (info.st_dev, info.st_ino) != (layout.staging_device, layout.staging_inode):
        raise OutputError(f"refusing to use replaced sweep staging directory {staging}")
