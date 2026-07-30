from __future__ import annotations

from pathlib import Path

import pytest

from carnopy.app.jobs import JobStore
from carnopy.app.recovery import remove_staging_candidate, scan_staging_candidates


def test_job_store_persists_exact_snapshot_progress_and_terminal_envelope(
    tmp_path: Path,
) -> None:
    store = JobStore(tmp_path / ".carnopy-gui")
    record = store.start(
        request_id="e7191ad4-8875-460e-a6fe-e2cb8c53f403",
        operation="generate",
        config_relative_path="configs/dataset.yaml",
        yaml_snapshot="schema_version: 2\n",
        config_sha256="a" * 64,
    )
    store.update_event(record, "phase", {"name": "generation", "cancellable": True})
    store.update_event(record, "progress", {"completed": 7, "total": 10})
    envelope = {
        "request_id": record["request_id"],
        "request_type": "generate_dataset",
        "terminal_event": {
            "protocol_version": 1,
            "request_id": record["request_id"],
            "type": "result",
            "payload": {"run_status": "completed"},
        },
        "stderr": "backend note\n",
        "exit_code": 0,
        "exit_status": "normal",
        "force_stopped": False,
    }
    store.finish(record, envelope)

    loaded = store.load()

    assert len(loaded) == 1
    assert loaded[0].data is not None
    assert loaded[0].data["configuration"]["yaml_snapshot"] == "schema_version: 2\n"
    assert loaded[0].data["progress"] == {"completed": 7, "total": 10}
    assert loaded[0].data["terminal_envelope"] == envelope
    assert loaded[0].data["status"] == "completed"


def test_job_store_retains_records_and_reports_malformed_records(tmp_path: Path) -> None:
    store = JobStore(tmp_path / ".carnopy-gui")
    for index in range(2):
        store.start(
            request_id=f"00000000-0000-0000-0000-00000000000{index}",
            operation="validate",
            config_relative_path="configs/dataset.yaml",
            yaml_snapshot="value\n",
            config_sha256="b" * 64,
        )
    malformed = store.directory / "malformed.json"
    malformed.write_text("{", encoding="utf-8")

    loaded = store.load()

    assert len(loaded) == 3
    assert any(item.path == malformed and item.error for item in loaded)
    assert len(list(store.directory.glob("*.json"))) == 3


def test_job_store_keeps_schema_one_backward_readable_and_records_start_failure(
    tmp_path: Path,
) -> None:
    store = JobStore(tmp_path / ".carnopy-gui")
    legacy = store.start(
        request_id="00000000-0000-0000-0000-000000000010",
        operation="generate",
        config_relative_path="configs/legacy.yaml",
        yaml_snapshot="legacy\n",
        config_sha256="c" * 64,
    )
    failed = store.start(
        request_id="00000000-0000-0000-0000-000000000011",
        operation="validate",
        config_relative_path="configs/dataset.yaml",
        yaml_snapshot="value\n",
        config_sha256="d" * 64,
    )

    store.finish_start_failure(
        failed,
        request_type="validate_config",
        category="process",
        code="worker_start_failed",
        message="worker could not start",
    )

    loaded = {item.path.stem: item for item in store.load()}
    assert loaded[str(legacy["request_id"])].data is not None
    failed_data = loaded[str(failed["request_id"])].data
    assert failed_data is not None
    assert failed_data["job_schema_version"] == 1
    assert failed_data["status"] == "failed"
    assert failed_data["summary"] == {
        "category": "process",
        "code": "worker_start_failed",
        "message": "worker could not start",
    }


@pytest.mark.parametrize(
    "slug",
    ["property", "saturation", "vapor_fraction", "model_sweep", "preparation"],
)
def test_staging_scan_recognizes_all_direct_run_slugs(tmp_path: Path, slug: str) -> None:
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    candidate = outputs / f".20260702T120000Z_{slug}_1a2b3c4d.staging"
    candidate.mkdir()
    (outputs / f".20260702T120000Z_{slug}_nothex.staging").mkdir()
    nested = outputs / "nested"
    nested.mkdir()
    (nested / f".20260702T120000Z_{slug}_1a2b3c4d.staging").mkdir()

    found = scan_staging_candidates(outputs)

    assert [item.path for item in found] == [candidate]
    assert found[0].removable


def test_staging_removal_rejects_symlinks_and_inode_replacement(tmp_path: Path) -> None:
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    name = ".20260702T120000Z_property_1a2b3c4d.staging"
    original = outputs / name
    original.mkdir()
    scanned = scan_staging_candidates(outputs)[0]
    moved = outputs / "moved"
    original.rename(moved)
    original.mkdir()

    with pytest.raises(ValueError, match="replaced"):
        remove_staging_candidate(scanned, outputs)
    assert original.is_dir()

    symlink = outputs / ".20260702T120001Z_property_1a2b3c4d.staging"
    symlink.symlink_to(moved, target_is_directory=True)
    found = {item.path.name: item for item in scan_staging_candidates(outputs)}
    assert not found[symlink.name].removable
    with pytest.raises(ValueError, match="regular directory"):
        remove_staging_candidate(found[symlink.name], outputs)


def test_staging_removal_deletes_only_revalidated_candidate(tmp_path: Path) -> None:
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    candidate = outputs / ".20260702T120000Z_property_1a2b3c4d.staging"
    candidate.mkdir()
    (candidate / "partial.txt").write_text("partial", encoding="utf-8")
    scanned = scan_staging_candidates(outputs)[0]

    remove_staging_candidate(scanned, outputs)

    assert not candidate.exists()
