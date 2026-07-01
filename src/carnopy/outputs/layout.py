from __future__ import annotations

import shutil
import stat
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from carnopy.domain.failures import OutputError

MODE_SLUGS = {
    "property_table": "property",
    "saturation_table": "saturation",
    "vapor_mass_fraction_table": "vapor_fraction",
}


@dataclass(frozen=True)
class RunLayout:
    output_root: Path
    staging_directory: Path
    final_directory: Path
    public_final_directory: Path
    staging_device: int
    staging_inode: int


def create_run_layout(
    *,
    output_root: Path,
    mode: str,
    run_id: str,
    created_at: datetime,
    public_output_root: Path | None = None,
) -> RunLayout:
    try:
        output_root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise OutputError(f"could not create output root {output_root}: {exc}") from exc
    timestamp = created_at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    try:
        mode_slug = MODE_SLUGS[mode]
    except KeyError as exc:
        raise OutputError(f"unsupported dataset mode for run layout: {mode}") from exc
    try:
        run_prefix = UUID(run_id).hex[:8]
    except ValueError as exc:
        raise OutputError(f"invalid run_id for run layout: {run_id}") from exc
    name = f"{timestamp}_{mode_slug}_{run_prefix}"
    final_directory = output_root / name
    staging_directory = output_root / f".{name}.staging"
    selected_public_root = public_output_root if public_output_root is not None else output_root
    public_final_directory = selected_public_root / name
    if final_directory.exists() or staging_directory.exists():
        raise OutputError(f"immutable run path already exists: {final_directory}")
    try:
        staging_directory.mkdir()
        staging_stat = staging_directory.stat(follow_symlinks=False)
    except OSError as exc:
        raise OutputError(f"could not create staging directory: {exc}") from exc
    return RunLayout(
        output_root,
        staging_directory,
        final_directory,
        public_final_directory,
        staging_stat.st_dev,
        staging_stat.st_ino,
    )


def finalize_run_layout(layout: RunLayout) -> None:
    if layout.final_directory.exists():
        raise OutputError(f"refusing to overwrite existing run directory {layout.final_directory}")
    _verify_staging_directory(layout)
    try:
        layout.staging_directory.rename(layout.final_directory)
    except OSError as exc:
        raise OutputError(f"could not finalize run directory: {exc}") from exc


def cleanup_run_layout(layout: RunLayout) -> None:
    """Remove only the known, unfinalized staging directory."""

    staging = layout.staging_directory
    if not staging.exists() and not staging.is_symlink():
        return
    _verify_staging_directory(layout)
    try:
        shutil.rmtree(staging)
    except OSError as exc:
        raise OutputError(f"could not clean staging directory {staging}: {exc}") from exc


def _verify_staging_directory(layout: RunLayout) -> None:
    staging = layout.staging_directory
    if staging.is_symlink():
        raise OutputError(f"refusing to use staging symlink {staging}")
    try:
        staging_stat = staging.stat(follow_symlinks=False)
    except OSError as exc:
        raise OutputError(f"could not inspect staging directory {staging}: {exc}") from exc
    if not stat.S_ISDIR(staging_stat.st_mode):
        raise OutputError(f"refusing to use non-directory staging path {staging}")
    if (staging_stat.st_dev, staging_stat.st_ino) != (
        layout.staging_device,
        layout.staging_inode,
    ):
        raise OutputError(f"refusing to use replaced staging directory {staging}")
