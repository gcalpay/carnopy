from __future__ import annotations

import shutil
import stat
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from carnopy.domain.failures import OutputError


@dataclass(frozen=True)
class PreparationLayout:
    output_root: Path
    staging_directory: Path
    final_directory: Path
    staging_device: int
    staging_inode: int


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
    timestamp = created_at.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
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
        staging_info = staging.stat(follow_symlinks=False)
    except OSError as exc:
        raise OutputError(f"could not create preparation staging directory: {exc}") from exc
    return PreparationLayout(
        output_root,
        staging,
        final,
        staging_info.st_dev,
        staging_info.st_ino,
    )


def finalize_preparation_layout(layout: PreparationLayout) -> None:
    if layout.final_directory.exists() or layout.final_directory.is_symlink():
        raise OutputError(f"refusing to overwrite preparation directory {layout.final_directory}")
    _verify_preparation_staging(layout)
    try:
        layout.staging_directory.rename(layout.final_directory)
    except OSError as exc:
        raise OutputError(f"could not finalize preparation directory: {exc}") from exc


def cleanup_preparation_layout(layout: PreparationLayout) -> None:
    staging = layout.staging_directory
    if not staging.exists() and not staging.is_symlink():
        return
    _verify_preparation_staging(layout)
    try:
        shutil.rmtree(staging)
    except OSError as exc:
        raise OutputError(
            f"could not clean preparation staging directory {staging}: {exc}"
        ) from exc


def _verify_preparation_staging(layout: PreparationLayout) -> None:
    staging = layout.staging_directory
    if staging.is_symlink():
        raise OutputError(f"refusing to use preparation staging symlink {staging}")
    try:
        root = layout.output_root.resolve(strict=True)
        if staging.parent.resolve(strict=True) != root:
            raise OutputError(f"preparation staging directory escapes output root {staging}")
        info = staging.stat(follow_symlinks=False)
    except OutputError:
        raise
    except OSError as exc:
        raise OutputError(
            f"could not inspect preparation staging directory {staging}: {exc}"
        ) from exc
    if not stat.S_ISDIR(info.st_mode):
        raise OutputError(f"refusing to use non-directory preparation staging path {staging}")
    if (info.st_dev, info.st_ino) != (layout.staging_device, layout.staging_inode):
        raise OutputError(f"refusing to use replaced preparation staging directory {staging}")
