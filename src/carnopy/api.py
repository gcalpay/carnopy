from __future__ import annotations

from pathlib import Path

from carnopy.config.io import LoadedConfig, load_config_file
from carnopy.pipeline import run_generation, validate_loaded_config
from carnopy.results import RunResult, ValidationResult


def load_config(path: str | Path) -> LoadedConfig:
    return load_config_file(path)


def validate_config(path: str | Path) -> ValidationResult:
    loaded = load_config_file(path)
    result, _, _ = validate_loaded_config(loaded)
    return result


def generate_dataset(
    path: str | Path,
    *,
    output_root: str | Path = "outputs",
) -> RunResult:
    loaded = load_config_file(path)
    return run_generation(loaded, Path(output_root))
