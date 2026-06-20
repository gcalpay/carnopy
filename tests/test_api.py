from __future__ import annotations

from pathlib import Path

from carnopy import generate_dataset, load_config, validate_config


def test_public_api(property_config_path: Path, tmp_path: Path) -> None:
    loaded = load_config(property_config_path)
    validation = validate_config(property_config_path)
    run = generate_dataset(property_config_path, output_root=tmp_path)
    assert loaded.model.mode == "property_table"
    assert validation.projected_rows == 2
    assert run.row_count == 2
    assert run.run_status == "completed"
