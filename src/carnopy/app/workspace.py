from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

WORKSPACE_SCHEMA_VERSION = 1
MARKER_CONTENT = {"workspace_schema_version": WORKSPACE_SCHEMA_VERSION}


class WorkspaceError(ValueError):
    """A workspace path does not satisfy the desktop application contract."""


@dataclass(frozen=True)
class Workspace:
    root: Path
    configs: Path
    outputs: Path
    figures: Path
    private_directory: Path
    marker: Path


def workspace_paths(path: Path) -> Workspace:
    root = path.expanduser().resolve()
    private_directory = root / ".carnopy-gui"
    return Workspace(
        root=root,
        configs=root / "configs",
        outputs=root / "outputs",
        figures=root / "figures",
        private_directory=private_directory,
        marker=private_directory / "workspace.json",
    )


def initialize_workspace(path: Path) -> Workspace:
    workspace = workspace_paths(path)
    if workspace.root.exists() and not workspace.root.is_dir():
        raise WorkspaceError(f"workspace path is not a directory: {workspace.root}")
    for directory in (
        workspace.configs,
        workspace.outputs,
        workspace.figures,
        workspace.private_directory,
    ):
        if directory.exists() and not directory.is_dir():
            raise WorkspaceError(f"required workspace path conflicts with a file: {directory}")
    if workspace.marker.exists():
        raise WorkspaceError(f"workspace is already initialized: {workspace.root}")

    workspace.root.mkdir(parents=True, exist_ok=True)
    for directory in (
        workspace.configs,
        workspace.outputs,
        workspace.figures,
        workspace.private_directory,
    ):
        directory.mkdir(exist_ok=True)
    try:
        with workspace.marker.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(MARKER_CONTENT, stream, sort_keys=True, separators=(",", ":"))
            stream.write("\n")
    except FileExistsError as exc:
        raise WorkspaceError(f"workspace is already initialized: {workspace.root}") from exc
    return workspace


def open_workspace(path: Path) -> Workspace:
    workspace = workspace_paths(path)
    if not workspace.root.is_dir():
        raise WorkspaceError(f"workspace directory does not exist: {workspace.root}")
    if not workspace.marker.is_file():
        raise WorkspaceError(f"workspace marker is missing: {workspace.marker}")
    try:
        marker = json.loads(workspace.marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkspaceError(f"workspace marker is invalid: {workspace.marker}") from exc
    if marker != MARKER_CONTENT:
        raise WorkspaceError(
            f"unsupported workspace marker in {workspace.marker}; "
            f"expected schema version {WORKSPACE_SCHEMA_VERSION}"
        )
    for directory in (
        workspace.configs,
        workspace.outputs,
        workspace.figures,
        workspace.private_directory,
    ):
        if not directory.is_dir():
            raise WorkspaceError(f"required workspace directory is missing: {directory}")
    return workspace
