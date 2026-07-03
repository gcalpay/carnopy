from __future__ import annotations

import json
import os
import shutil
import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from carnopy.app.jobs import write_json_atomic
from carnopy.app.workspace import Workspace, open_workspace
from carnopy.domain.failures import CarnopyError

PLOT_STAGING_SCHEMA_VERSION = 1
MANIFEST_NAME = "promotion-manifest.json"


class PlotStagingError(CarnopyError):
    """A private GUI plot-staging lease cannot be used safely."""


class PlotStagingPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    staging_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    device: int = Field(ge=0)
    inode: int = Field(gt=0)


@dataclass(frozen=True)
class PlotStagingLease:
    workspace_root: Path
    staging_id: str
    path: Path
    device: int
    inode: int

    def worker_payload(self) -> dict[str, int | str]:
        return {
            "staging_id": self.staging_id,
            "device": self.device,
            "inode": self.inode,
        }


def create_plot_staging(workspace_path: Path) -> PlotStagingLease:
    workspace = open_workspace(workspace_path)
    root = _staging_root(workspace, create=True)
    staging_id = uuid4().hex
    path = root / staging_id
    path.mkdir(mode=0o700)
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise PlotStagingError("plot staging lease is not a regular directory")
    return PlotStagingLease(
        workspace_root=workspace.root,
        staging_id=staging_id,
        path=path,
        device=info.st_dev,
        inode=info.st_ino,
    )


def validate_plot_staging(
    workspace: Workspace,
    payload: PlotStagingPayload,
) -> PlotStagingLease:
    lease = PlotStagingLease(
        workspace_root=workspace.root,
        staging_id=payload.staging_id,
        path=_staging_root(workspace, create=False) / payload.staging_id,
        device=payload.device,
        inode=payload.inode,
    )
    _verify_lease(lease)
    return lease


def promote_plot_artifacts(
    lease: PlotStagingLease,
    *,
    staged_image: Path,
    staged_sidecar: Path,
    final_image: Path,
    final_sidecar: Path,
) -> Path:
    _verify_lease(lease)
    artifacts = [
        _artifact_record(lease, staged_image, final_image, "image"),
        _artifact_record(lease, staged_sidecar, final_sidecar, "sidecar"),
    ]
    manifest_path = lease.path / MANIFEST_NAME
    write_json_atomic(
        manifest_path,
        {
            "plot_staging_schema_version": PLOT_STAGING_SCHEMA_VERSION,
            "staging_id": lease.staging_id,
            "artifacts": artifacts,
        },
    )
    try:
        for artifact in artifacts:
            staged = lease.workspace_root / str(artifact["staged_path"])
            final = lease.workspace_root / str(artifact["final_path"])
            os.link(staged, final)
    except OSError as exc:
        raise PlotStagingError(f"could not promote staged plot artifacts: {exc}") from exc
    return manifest_path


def cleanup_plot_staging(lease: PlotStagingLease, *, successful: bool) -> None:
    workspace = open_workspace(lease.workspace_root)
    _staging_root(workspace, create=False)
    _verify_lease(lease)
    if not successful:
        manifest = _read_manifest(lease)
        if manifest is not None:
            for artifact in manifest:
                _remove_matching_final(lease, artifact)
    _verify_lease(lease)
    shutil.rmtree(lease.path)


def _staging_root(workspace: Workspace, *, create: bool) -> Path:
    if workspace.private_directory.is_symlink():
        raise PlotStagingError("workspace private directory must not be a symbolic link")
    root = workspace.private_directory / "plot-staging"
    if root.is_symlink():
        raise PlotStagingError("plot staging root must not be a symbolic link")
    if create:
        root.mkdir(exist_ok=True)
    if not root.is_dir():
        raise PlotStagingError(f"plot staging root is not a directory: {root}")
    if root.resolve().parent != workspace.private_directory.resolve():
        raise PlotStagingError("plot staging root escapes the workspace private directory")
    return root


def _verify_lease(lease: PlotStagingLease) -> None:
    root = lease.path.parent
    if lease.path.name != lease.staging_id or root.name != "plot-staging":
        raise PlotStagingError("plot staging lease path is invalid")
    if root.is_symlink() or lease.path.is_symlink():
        raise PlotStagingError("plot staging lease must not use symbolic links")
    try:
        info = lease.path.lstat()
    except OSError as exc:
        raise PlotStagingError(f"plot staging lease is unavailable: {lease.path}") from exc
    if not stat.S_ISDIR(info.st_mode):
        raise PlotStagingError("plot staging lease is not a regular directory")
    if (info.st_dev, info.st_ino) != (lease.device, lease.inode):
        raise PlotStagingError("plot staging lease was replaced")
    workspace_root = lease.workspace_root.resolve()
    if lease.path.resolve().parent.parent != workspace_root / ".carnopy-gui":
        raise PlotStagingError("plot staging lease escapes the workspace")


def _artifact_record(
    lease: PlotStagingLease,
    staged_path: Path,
    final_path: Path,
    kind: str,
) -> dict[str, int | str]:
    staged = _staged_artifact(lease, staged_path)
    final = _final_artifact(lease, final_path, require_file=False)
    if os.path.lexists(final):
        raise PlotStagingError(f"refusing to overwrite existing plot artifact: {final}")
    info = staged.lstat()
    return {
        "kind": kind,
        "staged_path": staged.relative_to(lease.workspace_root).as_posix(),
        "final_path": final.relative_to(lease.workspace_root).as_posix(),
        "device": info.st_dev,
        "inode": info.st_ino,
    }


def _read_manifest(lease: PlotStagingLease) -> list[dict[str, object]] | None:
    path = lease.path / MANIFEST_NAME
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            return None
        if value.get("plot_staging_schema_version") != PLOT_STAGING_SCHEMA_VERSION:
            return None
        if value.get("staging_id") != lease.staging_id:
            return None
        artifacts = value.get("artifacts")
        if not isinstance(artifacts, list) or len(artifacts) != 2:
            return None
        parsed = [item for item in artifacts if isinstance(item, dict)]
        return parsed if len(parsed) == len(artifacts) else None
    except (OSError, json.JSONDecodeError):
        return None


def _remove_matching_final(lease: PlotStagingLease, artifact: dict[str, object]) -> None:
    try:
        staged_relative = _relative_path(artifact["staged_path"])
        final_relative = _relative_path(artifact["final_path"])
        device = artifact["device"]
        inode = artifact["inode"]
        if not isinstance(device, int) or not isinstance(inode, int):
            return
        staged = _staged_artifact(lease, lease.workspace_root / staged_relative)
        final = _final_artifact(
            lease,
            lease.workspace_root / final_relative,
            require_file=True,
        )
        staged_info = staged.lstat()
        final_info = final.lstat()
    except (KeyError, TypeError, ValueError, OSError, PlotStagingError):
        return
    expected = (device, inode)
    if (staged_info.st_dev, staged_info.st_ino) != expected:
        return
    if (final_info.st_dev, final_info.st_ino) != expected:
        return
    try:
        final.unlink()
    except OSError:
        return


def _staged_artifact(lease: PlotStagingLease, path: Path) -> Path:
    candidate = path.absolute()
    if candidate.parent != lease.path or candidate.name == MANIFEST_NAME:
        raise PlotStagingError("staged plot artifact is outside its lease directory")
    info = candidate.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise PlotStagingError("staged plot artifact is not a regular file")
    return candidate


def _final_artifact(
    lease: PlotStagingLease,
    path: Path,
    *,
    require_file: bool,
) -> Path:
    workspace = open_workspace(lease.workspace_root)
    candidate = path.absolute()
    if candidate.parent.parent != workspace.figures:
        raise PlotStagingError("final plot artifact is not nested directly under figures")
    if candidate.parent.is_symlink() or workspace.figures.is_symlink():
        raise PlotStagingError("final plot path must not use symbolic links")
    if candidate.parent.resolve().parent != workspace.figures.resolve():
        raise PlotStagingError("final plot artifact escapes the workspace figures directory")
    if require_file:
        info = candidate.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            raise PlotStagingError("final plot artifact is not a regular file")
    return candidate


def _relative_path(value: object) -> Path:
    if not isinstance(value, str):
        raise ValueError("artifact path is not text")
    parsed = PurePosixPath(value)
    if parsed.is_absolute() or not parsed.parts or ".." in parsed.parts:
        raise ValueError("artifact path is not workspace-relative")
    return Path(*parsed.parts)
