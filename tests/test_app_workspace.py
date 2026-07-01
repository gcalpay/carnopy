from __future__ import annotations

import json
from pathlib import Path

import pytest

from carnopy.app.workspace import WorkspaceError, initialize_workspace, open_workspace


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

    with pytest.raises(WorkspaceError, match="already initialized"):
        initialize_workspace(workspace.root)


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
