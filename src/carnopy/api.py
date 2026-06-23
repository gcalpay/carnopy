from __future__ import annotations

from pathlib import Path

from carnopy.config.io import LoadedConfig, load_config_file, load_sweep_config_file
from carnopy.pipeline import run_generation, validate_loaded_config
from carnopy.results import RunResult, SweepResult, ValidationResult
from carnopy.sweeps.pipeline import run_model_sweep


def load_config(path: str | Path) -> LoadedConfig:
    return load_config_file(path)


def validate_config(path: str | Path) -> ValidationResult:
    loaded = load_config_file(path)
    return validate_loaded_config(loaded).result


def generate_dataset(
    path: str | Path,
    *,
    output_root: str | Path = "outputs",
    figures_root: str | Path = "figures",
) -> RunResult:
    loaded = load_config_file(path)
    return run_generation(
        loaded,
        Path(output_root),
        Path(figures_root),
    )


def generate_model_sweep(
    path: str | Path,
    *,
    output_root: str | Path = "outputs",
) -> SweepResult:
    loaded = load_sweep_config_file(path)
    return run_model_sweep(loaded, Path(output_root))
