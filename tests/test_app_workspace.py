from __future__ import annotations

import json
from pathlib import Path

import pytest

from carnopy.app.workspace import (
    WorkspaceError,
    WorkspaceOperation,
    commit_workspace_operation,
    initialize_workspace,
    open_workspace,
    preflight_workspace_operation,
)


def test_initialize_and_reopen_workspace(tmp_path: Path) -> None:
    root = tmp_path / "workspace"

    workspace = initialize_workspace(root)

    assert workspace.root == root.resolve()
    assert workspace.marker.read_text(encoding="utf-8") == ('{"workspace_schema_version":1}\n')
    assert all(
        path.is_dir()
        for path in (
            workspace.configs,
            workspace.outputs,
            workspace.figures,
            workspace.private_directory,
        )
    )
    assert open_workspace(root) == workspace


def test_workspace_path_resolution_failure_is_a_workspace_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_resolution(_path: Path) -> Path:
        raise OSError("simulated resolution failure")

    monkeypatch.setattr(Path, "resolve", fail_resolution)

    with pytest.raises(WorkspaceError, match="cannot be resolved"):
        open_workspace(tmp_path / "workspace")


def test_initialize_allows_nonempty_folder_without_overwriting(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    existing = root / "notes.txt"
    existing.write_text("keep me", encoding="utf-8")

    initialize_workspace(root)

    assert existing.read_text(encoding="utf-8") == "keep me"


def test_initialize_rejects_required_file_conflict(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    conflict = root / "configs"
    conflict.write_text("not a directory", encoding="utf-8")

    with pytest.raises(WorkspaceError, match="conflicts with a file"):
        initialize_workspace(root)

    assert conflict.read_text(encoding="utf-8") == "not a directory"
    assert not (root / ".carnopy-gui" / "workspace.json").exists()


def test_initialize_refuses_existing_marker(tmp_path: Path) -> None:
    workspace = initialize_workspace(tmp_path / "workspace")

    with pytest.raises(WorkspaceError, match="already initialized") as error:
        initialize_workspace(workspace.root)

    assert "use Open Workspace" in str(error.value)


@pytest.mark.parametrize(
    "marker",
    [
        {},
        {"workspace_schema_version": 2},
        {"workspace_schema_version": 1, "unexpected": True},
    ],
)
def test_open_rejects_invalid_workspace_marker(
    tmp_path: Path,
    marker: dict[str, object],
) -> None:
    workspace = initialize_workspace(tmp_path / "workspace")
    workspace.marker.write_text(json.dumps(marker), encoding="utf-8")

    with pytest.raises(WorkspaceError, match="unsupported workspace marker"):
        open_workspace(workspace.root)


def test_open_rejects_missing_required_directory(tmp_path: Path) -> None:
    workspace = initialize_workspace(tmp_path / "workspace")
    workspace.configs.rmdir()

    with pytest.raises(WorkspaceError, match="required workspace directory is missing"):
        open_workspace(workspace.root)


def test_create_preflight_is_non_writing_and_commit_revalidates_absence(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspace"

    plan = preflight_workspace_operation(root, "create")

    assert not root.exists()
    assert plan.operation == "create"
    assert not plan.root_must_exist

    root.mkdir()
    with pytest.raises(WorkspaceError, match="already exists"):
        commit_workspace_operation(plan)
    assert not (root / ".carnopy-gui" / "workspace.json").exists()


def test_initialize_existing_rejects_root_inode_replacement(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    plan = preflight_workspace_operation(root, "initialize_existing")
    displaced = tmp_path / "displaced"
    root.rename(displaced)
    root.mkdir()

    with pytest.raises(WorkspaceError, match="changed after confirmation"):
        commit_workspace_operation(plan)

    assert not (root / ".carnopy-gui" / "workspace.json").exists()


def test_open_revalidates_workspace_and_rejects_root_inode_replacement(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspace"
    original = initialize_workspace(root)
    plan = preflight_workspace_operation(root, "open")
    displaced = tmp_path / "displaced"
    original.root.rename(displaced)
    replacement = initialize_workspace(root)

    with pytest.raises(WorkspaceError, match="changed after confirmation"):
        commit_workspace_operation(plan)

    assert open_workspace(root) == replacement


@pytest.mark.parametrize("operation", ["create", "initialize_existing", "open"])
def test_workspace_operation_commit_succeeds_after_unchanged_preflight(
    tmp_path: Path,
    operation: WorkspaceOperation,
) -> None:
    root = tmp_path / operation
    if operation == "initialize_existing":
        root.mkdir()
    elif operation == "open":
        initialize_workspace(root)

    plan = preflight_workspace_operation(root, operation)
    workspace = commit_workspace_operation(plan)

    assert open_workspace(root) == workspace
