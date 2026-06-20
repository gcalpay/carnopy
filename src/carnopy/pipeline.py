from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pandas as pd

from carnopy.backends.coolprop import CoolPropBackend
from carnopy.config.io import LoadedConfig
from carnopy.config.models import NormalizedConfig
from carnopy.config.normalize import canonical_json_bytes, normalize_config
from carnopy.generation import (
    generate_property_table,
    generate_saturation_table,
    generate_vapor_mass_fraction_table,
)
from carnopy.outputs import (
    build_metadata,
    build_report,
    create_run_layout,
    dataset_columns,
    dataset_unit_map,
    determine_run_status,
    finalize_run_layout,
    hash_artifacts,
    write_bytes,
    write_dataset,
    write_json,
)
from carnopy.provenance import build_identity
from carnopy.results import RunResult, ValidationResult


def validate_loaded_config(
    loaded: LoadedConfig,
    backend: CoolPropBackend | None = None,
) -> tuple[ValidationResult, NormalizedConfig, bytes]:
    selected_backend = backend or CoolPropBackend()
    normalized = normalize_config(loaded.model, selected_backend)
    normalized_bytes = canonical_json_bytes(normalized.executable_dict())
    identity = build_identity(
        raw_config=loaded.raw_bytes,
        normalized_config=normalized_bytes,
        backend_version=selected_backend.version,
    )
    result = ValidationResult(
        backend=selected_backend.name,
        backend_version=selected_backend.version,
        mode=normalized.mode,
        projected_rows=normalized.projected_rows,
        canonical_fluids=tuple(normalized.fluids),
        normalized_config_sha256=identity.normalized_config_sha256,
    )
    return result, normalized, normalized_bytes


def run_generation(
    loaded: LoadedConfig,
    output_root: Path,
) -> RunResult:
    backend = CoolPropBackend()
    _, normalized, normalized_bytes = validate_loaded_config(loaded, backend)
    identity = build_identity(
        raw_config=loaded.raw_bytes,
        normalized_config=normalized_bytes,
        backend_version=backend.version,
    )
    run_id = str(uuid4())
    created_at = datetime.now(timezone.utc)
    layout = create_run_layout(
        output_root=output_root,
        mode=normalized.mode,
        spec_id=identity.spec_id,
        run_id=run_id,
        created_at=created_at,
    )

    backend.initialize_reference_states(normalized.fluids)
    rows = _generate_rows(normalized, backend, run_id)
    columns = dataset_columns(normalized)
    frame = pd.DataFrame(rows, columns=columns)
    run_status = determine_run_status(frame)
    unit_map = dataset_unit_map(normalized)
    input_columns = _input_columns(normalized.mode)

    write_dataset(frame, layout.staging_directory, unit_map)
    write_bytes(layout.staging_directory / "config.original.yaml", loaded.raw_bytes)
    write_bytes(
        layout.staging_directory / "config.normalized.json",
        normalized_bytes,
    )
    report = build_report(
        frame=frame,
        run_id=run_id,
        run_status=run_status,
        output_directory=layout.final_directory,
        input_columns=input_columns,
    )
    write_json(layout.staging_directory / "report.json", report)
    hashed_names = [
        "dataset.csv",
        "dataset.parquet",
        "config.original.yaml",
        "config.normalized.json",
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
        output_directory=layout.final_directory,
        output_files=output_files,
        artifact_hashes=artifact_hashes,
        unit_map=unit_map,
    )
    write_json(layout.staging_directory / "metadata.json", metadata)
    finalize_run_layout(layout)
    return RunResult(
        run_id=run_id,
        run_status=run_status,
        mode=normalized.mode,
        output_directory=layout.final_directory,
        row_count=len(frame),
        valid_row_count=int(frame["valid"].sum()),
        invalid_row_count=int((~frame["valid"]).sum()),
        spec_id=identity.spec_id,
        generation_context_id=identity.generation_context_id,
    )


def _generate_rows(
    config: NormalizedConfig,
    backend: CoolPropBackend,
    run_id: str,
) -> list[dict[str, object]]:
    if config.mode == "property_table":
        return generate_property_table(config, backend, run_id)
    if config.mode == "saturation_table":
        return generate_saturation_table(config, backend, run_id)
    return generate_vapor_mass_fraction_table(config, backend, run_id)


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
