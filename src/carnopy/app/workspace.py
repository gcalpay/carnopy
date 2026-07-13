from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

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


WorkspaceOperation = Literal["create", "initialize_existing", "open"]


@dataclass(frozen=True)
class WorkspaceOperationPlan:
    """A trusted, non-writing plan for one workspace operation."""

    operation: WorkspaceOperation
    workspace: Workspace
    root_must_exist: bool
    root_device: int | None
    root_inode: int | None


def workspace_paths(path: Path) -> Workspace:
    try:
        root = path.expanduser().resolve()
    except (OSError, RuntimeError) as exc:
        raise WorkspaceError(f"workspace path cannot be resolved: {path}") from exc
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
    _validate_initialization_target(workspace)

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


def preflight_workspace_operation(
    path: Path,
    operation: WorkspaceOperation,
) -> WorkspaceOperationPlan:
    """Validate a workspace operation without changing the filesystem."""

    workspace = workspace_paths(path)
    if operation == "create":
        if workspace.root.exists():
            raise WorkspaceError(
                f"workspace path already exists; use Initialize Existing Folder: {workspace.root}"
            )
        return WorkspaceOperationPlan(
            operation=operation,
            workspace=workspace,
            root_must_exist=False,
            root_device=None,
            root_inode=None,
        )
    if operation == "initialize_existing":
        if not workspace.root.is_dir():
            raise WorkspaceError(f"existing folder does not exist: {workspace.root}")
        _validate_initialization_target(workspace)
        device, inode = _root_identity(workspace.root)
        return WorkspaceOperationPlan(
            operation=operation,
            workspace=workspace,
            root_must_exist=True,
            root_device=device,
            root_inode=inode,
        )
    if operation == "open":
        workspace = open_workspace(workspace.root)
        device, inode = _root_identity(workspace.root)
        return WorkspaceOperationPlan(
            operation=operation,
            workspace=workspace,
            root_must_exist=True,
            root_device=device,
            root_inode=inode,
        )
    raise ValueError(f"unsupported workspace operation: {operation}")


def commit_workspace_operation(plan: WorkspaceOperationPlan) -> Workspace:
    """Revalidate and execute a trusted workspace operation plan."""

    root = plan.workspace.root
    if plan.operation == "create":
        if plan.root_must_exist or plan.root_device is not None or plan.root_inode is not None:
            raise WorkspaceError(f"workspace creation plan is invalid: {root}")
        preflight_workspace_operation(root, "create")
        return initialize_workspace(root)
    if plan.operation == "initialize_existing":
        _require_existing_plan(plan)
        current = preflight_workspace_operation(root, "initialize_existing")
        _require_same_root(plan, current)
        return initialize_workspace(root)
    if plan.operation == "open":
        _require_existing_plan(plan)
        workspace = open_workspace(root)
        device, inode = _root_identity(workspace.root)
        current = WorkspaceOperationPlan(
            operation="open",
            workspace=workspace,
            root_must_exist=True,
            root_device=device,
            root_inode=inode,
        )
        _require_same_root(plan, current)
        return workspace
    raise ValueError(f"unsupported workspace operation: {plan.operation}")


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


def _validate_initialization_target(workspace: Workspace) -> None:
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


def _root_identity(path: Path) -> tuple[int, int]:
    try:
        stat = path.stat()
    except OSError as exc:
        raise WorkspaceError(f"workspace directory cannot be inspected: {path}") from exc
    return stat.st_dev, stat.st_ino


def _require_same_root(
    expected: WorkspaceOperationPlan,
    current: WorkspaceOperationPlan,
) -> None:
    if (
        expected.root_device is None
        or expected.root_inode is None
        or current.root_device != expected.root_device
        or current.root_inode != expected.root_inode
    ):
        raise WorkspaceError(
            f"workspace directory changed after confirmation: {expected.workspace.root}"
        )


def _require_existing_plan(plan: WorkspaceOperationPlan) -> None:
    if not plan.root_must_exist or plan.root_device is None or plan.root_inode is None:
        raise WorkspaceError(f"workspace operation plan is invalid: {plan.workspace.root}")
