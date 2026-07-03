from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from carnopy.app.plot_staging import (
    PlotStagingError,
    PlotStagingLease,
    cleanup_plot_staging,
    create_plot_staging,
    promote_plot_artifacts,
)
from carnopy.app.workspace import initialize_workspace


def _artifacts(tmp_path: Path) -> tuple[PlotStagingLease, Path, Path, Path, Path]:
    workspace = initialize_workspace(tmp_path / "workspace")
    lease = create_plot_staging(workspace.root)
    staged_image = lease.path / "plot.png"
    staged_sidecar = lease.path / "plot.plot.json"
    staged_image.write_bytes(b"image")
    staged_sidecar.write_text("{}\n", encoding="utf-8")
    final_directory = workspace.figures / "dataset"
    final_directory.mkdir()
    return (
        lease,
        staged_image,
        staged_sidecar,
        final_directory / "plot.png",
        final_directory / "plot.plot.json",
    )


def test_successful_promotion_preserves_final_files_and_removes_staging(
    tmp_path: Path,
) -> None:
    lease, staged_image, staged_sidecar, final_image, final_sidecar = _artifacts(tmp_path)

    manifest = promote_plot_artifacts(
        lease,
        staged_image=staged_image,
        staged_sidecar=staged_sidecar,
        final_image=final_image,
        final_sidecar=final_sidecar,
    )

    value = json.loads(manifest.read_text(encoding="utf-8"))
    assert value["staging_id"] == lease.staging_id
    assert {item["kind"] for item in value["artifacts"]} == {"image", "sidecar"}
    assert os.path.samefile(staged_image, final_image)
    assert os.path.samefile(staged_sidecar, final_sidecar)

    cleanup_plot_staging(lease, successful=True)

    assert not lease.path.exists()
    assert final_image.read_bytes() == b"image"
    assert final_sidecar.read_text(encoding="utf-8") == "{}\n"


def test_failed_partial_promotion_removes_only_matching_final_link(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lease, staged_image, staged_sidecar, final_image, final_sidecar = _artifacts(tmp_path)
    original_link = os.link
    calls = 0

    def fail_second_link(source: Path, destination: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("controlled promotion failure")
        original_link(source, destination)

    monkeypatch.setattr(os, "link", fail_second_link)
    with pytest.raises(PlotStagingError, match="controlled promotion failure"):
        promote_plot_artifacts(
            lease,
            staged_image=staged_image,
            staged_sidecar=staged_sidecar,
            final_image=final_image,
            final_sidecar=final_sidecar,
        )

    assert final_image.is_file()
    assert not final_sidecar.exists()
    cleanup_plot_staging(lease, successful=False)

    assert not final_image.exists()
    assert not lease.path.exists()


@pytest.mark.parametrize("manifest_text", [None, "not-json\n", "{}\n"])
def test_unverifiable_manifest_leaves_final_paths_untouched(
    tmp_path: Path,
    manifest_text: str | None,
) -> None:
    lease, _staged_image, _staged_sidecar, final_image, _final_sidecar = _artifacts(tmp_path)
    final_image.write_bytes(b"unrelated")
    if manifest_text is not None:
        (lease.path / "promotion-manifest.json").write_text(
            manifest_text,
            encoding="utf-8",
        )

    cleanup_plot_staging(lease, successful=False)

    assert final_image.read_bytes() == b"unrelated"
    assert not lease.path.exists()


def test_cleanup_rejects_replaced_staging_directory(tmp_path: Path) -> None:
    workspace = initialize_workspace(tmp_path / "workspace")
    lease = create_plot_staging(workspace.root)
    moved = lease.path.with_name(f"{lease.staging_id}-moved")
    lease.path.rename(moved)
    lease.path.mkdir()

    with pytest.raises(PlotStagingError, match="replaced"):
        cleanup_plot_staging(lease, successful=False)

    assert lease.path.is_dir()
    assert moved.is_dir()
