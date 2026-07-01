from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import cast
from uuid import uuid4

import pandas as pd

from carnopy._execution import ExecutionControl
from carnopy.backends.coolprop import CoolPropBackend
from carnopy.config.io import LoadedConfig
from carnopy.config.models import NormalizedConfig
from carnopy.config.normalize import canonical_json_bytes, normalize_config
from carnopy.domain.failures import OutputError
from carnopy.generation import (
    generate_property_table,
    generate_saturation_table,
    generate_vapor_mass_fraction_table,
)
from carnopy.outputs import (
    build_metadata,
    build_report,
    cleanup_run_layout,
    create_run_layout,
    dataset_columns,
    dataset_unit_map,
    determine_run_status,
    finalize_run_layout,
    hash_artifacts,
    write_bytes,
    write_dataset_formats,
    write_json,
)
from carnopy.provenance import build_identity, build_output_request_id
from carnopy.results import RunResult, ValidationResult
from carnopy.templates import TemplateError, template_text
from carnopy.visualization.automation import (
    ensure_visualization_dependencies,
    render_configured_visualizations,
)
from carnopy.visualization.configuration import (
    NormalizedVisualization,
    normalize_visualization,
)


@dataclass(frozen=True)
class ValidatedRunConfig:
    result: ValidationResult
    normalized: NormalizedConfig
    normalized_bytes: bytes
    visualization: NormalizedVisualization | None
    output_request_id: str
    dataset_formats: tuple[str, ...]


def validate_loaded_config(
    loaded: LoadedConfig,
    backend: CoolPropBackend | None = None,
) -> ValidatedRunConfig:
    selected_backend = backend or CoolPropBackend(model=loaded.model.backend.model)
    normalized = normalize_config(loaded.model, selected_backend)
    normalized_bytes = canonical_json_bytes(normalized.executable_dict())
    dataset_formats = loaded.model.outputs.dataset_formats
    output_request_id = build_output_request_id(dataset_formats)
    identity = build_identity(
        raw_config=loaded.raw_bytes,
        normalized_config=normalized_bytes,
        backend_name=selected_backend.name,
        backend_model=selected_backend.model,
        backend_version=selected_backend.version,
        output_request_id=output_request_id,
    )
    result = ValidationResult(
        backend=selected_backend.name,
        backend_model=selected_backend.model,
        backend_version=selected_backend.version,
        mode=normalized.mode,
        projected_rows=normalized.projected_rows,
        canonical_fluids=tuple(normalized.fluids),
        normalized_config_sha256=identity.normalized_config_sha256,
        output_request_id=output_request_id,
        dataset_formats=dataset_formats,
    )
    visualization = normalize_visualization(
        loaded.model.visualization,
        scientific_config=normalized,
    )
    if visualization is not None:
        ensure_visualization_dependencies()
    return ValidatedRunConfig(
        result=result,
        normalized=normalized,
        normalized_bytes=normalized_bytes,
        visualization=visualization,
        output_request_id=output_request_id,
        dataset_formats=dataset_formats,
    )


def run_generation(
    loaded: LoadedConfig,
    output_root: Path,
    figures_root: Path = Path("figures"),
    *,
    public_output_root: Path | None = None,
    add_state_keys: bool = False,
    execution: ExecutionControl | None = None,
) -> RunResult:
    if execution is not None:
        execution.phase("validation")
    backend = CoolPropBackend(model=loaded.model.backend.model)
    validated = validate_loaded_config(loaded, backend)
    normalized = validated.normalized
    normalized_bytes = validated.normalized_bytes
    identity = build_identity(
        raw_config=loaded.raw_bytes,
        normalized_config=normalized_bytes,
        backend_name=backend.name,
        backend_model=backend.model,
        backend_version=backend.version,
        output_request_id=validated.output_request_id,
    )
    run_id = str(uuid4())
    created_at = datetime.now(timezone.utc)
    layout = create_run_layout(
        output_root=output_root,
        mode=normalized.mode,
        run_id=run_id,
        created_at=created_at,
        public_output_root=public_output_root,
    )
    try:
        if validated.visualization is not None:
            planned_figure_directory = (
                figures_root.expanduser().resolve() / layout.public_final_directory.name
            )
            if (
                planned_figure_directory == layout.public_final_directory.resolve()
                or planned_figure_directory.exists()
            ):
                raise OutputError(
                    "configured visualization output directory conflicts with the immutable "
                    "run directory or already exists: "
                    f"{planned_figure_directory}"
                )

        if execution is not None:
            execution.phase("backend_initialization")
        backend.initialize_reference_states(normalized.fluids)
        if execution is not None:
            execution.phase("generation")
            execution.checkpoint(0, normalized.projected_rows)
        rows = _generate_rows(normalized, backend, run_id, execution=execution)
        columns = dataset_columns(normalized)
        frame = pd.DataFrame(rows, columns=columns)
        if add_state_keys:
            frame = _with_state_key_columns(frame, normalized)
        run_status = determine_run_status(frame)
        unit_map = dataset_unit_map(normalized)
        input_columns = _input_columns(normalized.mode)

        if execution is not None:
            execution.phase("writing")
        dataset_files = write_dataset_formats(
            frame,
            layout.staging_directory,
            unit_map,
            dataset_formats=validated.dataset_formats,
        )
        write_bytes(layout.staging_directory / "config.original.yaml", loaded.raw_bytes)
        write_bytes(
            layout.staging_directory / "config.normalized.json",
            normalized_bytes,
        )
        try:
            reference_bytes = template_text(normalized.mode, full=True).encode("utf-8")
        except TemplateError as exc:
            raise OutputError(
                f"could not load the packaged run configuration reference: {exc}"
            ) from exc
        write_bytes(
            layout.staging_directory / "config.reference.yaml",
            reference_bytes,
        )
        report = build_report(
            frame=frame,
            run_id=run_id,
            run_status=run_status,
            output_directory=layout.public_final_directory,
            input_columns=input_columns,
            backend=backend.name,
            backend_model=backend.model,
            backend_version=backend.version,
        )
        write_json(layout.staging_directory / "report.json", report)
        hashed_names = [
            *dataset_files,
            "config.original.yaml",
            "config.normalized.json",
            "config.reference.yaml",
            "report.json",
        ]
        artifact_hashes = hash_artifacts(layout.staging_directory, hashed_names)
        output_files = [*hashed_names, "metadata.json"]
        metadata = build_metadata(
            frame=frame,
            config=normalized,
            identity=identity,
            run_id=run_id,
            run_status=run_status,
            created_at_utc=created_at.isoformat().replace("+00:00", "Z"),
            backend_version=backend.version,
            output_directory=layout.public_final_directory,
            output_files=output_files,
            artifact_hashes=artifact_hashes,
            unit_map=unit_map,
            output_request_id=validated.output_request_id,
            dataset_formats=validated.dataset_formats,
        )
        write_json(layout.staging_directory / "metadata.json", metadata)
        if execution is not None:
            execution.phase("finalization")
            execution.raise_if_cancelled()
        finalize_run_layout(layout)
    except Exception as exc:
        try:
            cleanup_run_layout(layout)
        except OutputError as cleanup_error:
            raise OutputError(f"{exc}; staging cleanup also failed: {cleanup_error}") from exc
        raise

    if execution is not None:
        execution.disable_cancellation()
    visualization_summary = None
    if validated.visualization is not None:
        if execution is not None:
            execution.phase("configured_visualization", cancellable=False)
        visualization_summary = render_configured_visualizations(
            source_run=layout.final_directory,
            figures_root=figures_root,
            run_status=run_status,
            run_id=run_id,
            spec_id=identity.spec_id,
            generation_context_id=identity.generation_context_id,
            visualization=validated.visualization,
        )
    return RunResult(
        run_id=run_id,
        run_status=run_status,
        mode=normalized.mode,
        backend=backend.name,
        backend_model=backend.model,
        backend_version=backend.version,
        output_directory=layout.public_final_directory,
        row_count=len(frame),
        valid_row_count=int(frame["valid"].sum()),
        invalid_row_count=int((~frame["valid"]).sum()),
        spec_id=identity.spec_id,
        generation_context_id=identity.generation_context_id,
        output_request_id=validated.output_request_id,
        dataset_formats=validated.dataset_formats,
        visualization=visualization_summary,
    )


def _generate_rows(
    config: NormalizedConfig,
    backend: CoolPropBackend,
    run_id: str,
    *,
    execution: ExecutionControl | None = None,
) -> list[dict[str, object]]:
    if config.mode == "property_table":
        return generate_property_table(config, backend, run_id, execution=execution)
    if config.mode == "saturation_table":
        return generate_saturation_table(config, backend, run_id, execution=execution)
    return generate_vapor_mass_fraction_table(config, backend, run_id, execution=execution)


def _input_columns(mode: str) -> list[str]:
    if mode == "property_table":
        return ["fluid", "temperature_K", "pressure_Pa"]
    if mode == "saturation_table":
        return [
            "fluid",
            "temperature_K",
            "pressure_Pa",
            "vapor_mass_fraction",
            "saturation_endpoint",
        ]
    return ["fluid", "temperature_K", "pressure_Pa", "vapor_mass_fraction"]


def _with_state_key_columns(
    frame: pd.DataFrame,
    config: NormalizedConfig,
) -> pd.DataFrame:
    selected = frame.copy()
    selected["state_key_version"] = 1
    selected["state_key"] = [_state_key(config, row) for _, row in selected.iterrows()]
    if config.mode == "property_table":
        selected["state_key_temperature_index"] = [
            _sample_index(config.grid["temperature"], cast(float, row["temperature_K"]))
            for _, row in selected.iterrows()
        ]
        selected["state_key_pressure_index"] = [
            _sample_index(config.grid["pressure"], cast(float, row["pressure_Pa"]))
            for _, row in selected.iterrows()
        ]
    elif config.mode == "saturation_table":
        axis = _saturation_axis(config)
        column = "temperature_K" if axis == "temperature" else "pressure_Pa"
        selected["state_key_saturation_coordinate_name"] = axis
        selected["state_key_saturation_coordinate_index"] = [
            _sample_index(config.grid[axis], cast(float, row[column]))
            for _, row in selected.iterrows()
        ]
        selected["state_key_saturation_endpoint"] = selected["saturation_endpoint"]
    else:
        axis = _saturation_axis(config)
        column = "temperature_K" if axis == "temperature" else "pressure_Pa"
        selected["state_key_saturation_coordinate_name"] = axis
        selected["state_key_saturation_coordinate_index"] = [
            _sample_index(config.grid[axis], cast(float, row[column]))
            for _, row in selected.iterrows()
        ]
        selected["state_key_vapor_mass_fraction_index"] = [
            _sample_index(
                config.grid["vapor_mass_fraction"],
                cast(float, row["vapor_mass_fraction"]),
            )
            for _, row in selected.iterrows()
        ]
    return cast(pd.DataFrame, selected)


def _state_key(config: NormalizedConfig, row: pd.Series) -> str:
    fluid = str(row["fluid"])
    if config.mode == "property_table":
        t_index = _sample_index(config.grid["temperature"], cast(float, row["temperature_K"]))
        p_index = _sample_index(config.grid["pressure"], cast(float, row["pressure_Pa"]))
        return f"v1|property_table|fluid={fluid}|temperature={t_index}|pressure={p_index}"
    if config.mode == "saturation_table":
        axis = _saturation_axis(config)
        column = "temperature_K" if axis == "temperature" else "pressure_Pa"
        index = _sample_index(config.grid[axis], cast(float, row[column]))
        endpoint = str(row["saturation_endpoint"])
        return f"v1|saturation_table|fluid={fluid}|{axis}={index}|endpoint={endpoint}"
    axis = _saturation_axis(config)
    column = "temperature_K" if axis == "temperature" else "pressure_Pa"
    coordinate_index = _sample_index(config.grid[axis], cast(float, row[column]))
    fraction_index = _sample_index(
        config.grid["vapor_mass_fraction"],
        cast(float, row["vapor_mass_fraction"]),
    )
    return (
        "v1|vapor_mass_fraction_table|"
        f"fluid={fluid}|{axis}={coordinate_index}|vapor_mass_fraction={fraction_index}"
    )


def _saturation_axis(config: NormalizedConfig) -> str:
    axes = [axis for axis in ("temperature", "pressure") if axis in config.grid]
    if len(axes) != 1:
        raise OutputError("could not determine sweep saturation coordinate")
    return axes[0]


def _sample_index(values: list[float], value: float) -> int:
    key = _stable_float_key(value)
    for index, candidate in enumerate(values):
        if _stable_float_key(candidate) == key:
            return index
    raise OutputError(f"could not map emitted coordinate {value!r} to a normalized sample")


def _stable_float_key(value: float) -> str:
    if value == 0.0:
        return "0"
    return format(float(value), ".15g")
