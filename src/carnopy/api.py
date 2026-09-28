from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from carnopy.config.io import LoadedConfig, load_config_file, load_sweep_config_file

if TYPE_CHECKING:
    from carnopy.results import PreparationResult, RunResult, SweepResult, ValidationResult
    from carnopy.sources.preview import ImportPreview
    from carnopy.sources.results import ImportResult


def load_config(path: str | Path) -> LoadedConfig:
    return load_config_file(path)


def preview_source_import(source: str | Path, *, config: str | Path) -> ImportPreview:
    """Inspect local ThermoML evidence without writing outputs or calling a backend."""
    from carnopy.sources.preview import plan_source_import

    return plan_source_import(source, config).preview


def import_source(
    source: str | Path, *, config: str | Path, output_root: str | Path = "outputs"
) -> ImportResult:
    """Normalize local ThermoML density evidence into a new immutable source bundle."""
    from carnopy.sources.pipeline import run_source_import

    return run_source_import(source, config, output_root=output_root)


def validate_config(path: str | Path) -> ValidationResult:
    from carnopy.pipeline import validate_loaded_config

    loaded = load_config_file(path)
    return validate_loaded_config(loaded).result


def generate_dataset(
    path: str | Path,
    *,
    output_root: str | Path = "outputs",
    figures_root: str | Path = "figures",
) -> RunResult:
    from carnopy.pipeline import run_generation

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
    from carnopy.sweeps.pipeline import run_model_sweep

    loaded = load_sweep_config_file(path)
    return run_model_sweep(loaded, Path(output_root))


def prepare_dataset(
    source: str | Path,
    *,
    config: str | Path,
    output_root: str | Path = "prepared",
) -> PreparationResult:
    from carnopy.preparation.pipeline import prepare_dataset as run_preparation

    return run_preparation(source, config, output_root=output_root)
