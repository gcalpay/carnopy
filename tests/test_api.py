from __future__ import annotations

from pathlib import Path
from typing import get_args

import carnopy
from carnopy import generate_dataset, load_config, validate_config


def test_public_api(property_config_path: Path, tmp_path: Path) -> None:
    loaded = load_config(property_config_path)
    validation = validate_config(property_config_path)
    run = generate_dataset(property_config_path, output_root=tmp_path)
    assert loaded.model.mode == "property_table"
    assert validation.projected_rows == 2
    assert run.row_count == 2
    assert run.run_status == "completed"
    assert run.backend == "coolprop"
    assert run.backend_model == "heos"
    assert run.dataset_formats == ("csv", "parquet")
    assert run.output_request_id.startswith("out-")


def test_package_level_public_exports_remain_available() -> None:
    assert carnopy.generate_dataset is generate_dataset
    assert carnopy.load_config is load_config
    assert carnopy.validate_config is validate_config
    assert carnopy.CarnopyConfig.__name__ == "CarnopyConfig"
    assert carnopy.BackendConfig.__name__ == "BackendConfig"
    assert get_args(carnopy.CoolPropModel) == ("heos", "pr", "srk")
    assert carnopy.NormalizedConfig.__name__ == "NormalizedConfig"
    assert carnopy.OutputConfig.__name__ == "OutputConfig"
    assert carnopy.RunResult.__name__ == "RunResult"
    assert carnopy.ValidationResult.__name__ == "ValidationResult"
    assert carnopy.VisualizationConfig.__name__ == "VisualizationConfig"
    assert carnopy.VisualizationPlotConfig.__name__ == "VisualizationPlotConfig"
    assert carnopy.VisualizationSummary.__name__ == "VisualizationSummary"
