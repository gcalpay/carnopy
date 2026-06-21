from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal, cast

import pandas as pd

from carnopy.domain.units import AXIS_SI_UNITS, UNITS, validate_axis_unit
from carnopy.provenance import sha256_file
from carnopy.visualization.models import PlotCoordinate, PlotSource, VisualizationError

SUPPORTED_MODES = {
    "property_table",
    "saturation_table",
    "vapor_mass_fraction_table",
}
REQUIRED_IDENTITY_COLUMNS = {
    "run_id",
    "mode",
    "fluid",
    "backend",
    "backend_version",
    "valid",
}
MODE_COLUMNS = {
    "property_table": {"temperature_K", "pressure_Pa"},
    "saturation_table": {
        "temperature_K",
        "pressure_Pa",
        "vapor_mass_fraction",
        "saturation_endpoint",
    },
    "vapor_mass_fraction_table": {
        "temperature_K",
        "pressure_Pa",
        "vapor_mass_fraction",
    },
}


def load_plot_source(
    source: str | Path,
    *,
    saturation_coordinate: PlotCoordinate | None = None,
) -> PlotSource:
    requested_path = Path(source).expanduser().resolve()
    dataset_path = _resolve_dataset_path(requested_path)
    source_format: Literal["csv", "parquet"] = (
        "parquet" if dataset_path.suffix.lower() == ".parquet" else "csv"
    )
    metadata_path = dataset_path.parent / "metadata.json"
    metadata = _load_metadata(metadata_path) if metadata_path.is_file() else None
    source_sha256 = _hash_source(dataset_path)
    integrity = _verify_integrity(dataset_path, source_sha256, metadata)
    frame = _read_dataset(dataset_path, source_format)
    mode, run_id = _validate_dataset_identity(frame)
    if mode not in SUPPORTED_MODES:
        raise VisualizationError(f"unsupported Carnopy dataset mode for visualization: {mode!r}")
    missing = sorted(MODE_COLUMNS[mode] - set(frame.columns))
    if missing:
        raise VisualizationError(
            f"{mode} dataset is missing required columns: {', '.join(missing)}"
        )
    selected_coordinate = _resolve_saturation_coordinate(
        mode,
        metadata,
        saturation_coordinate,
    )
    coordinate_column = (
        None
        if selected_coordinate is None
        else ("pressure_Pa" if selected_coordinate == "pressure" else "temperature_K")
    )
    display_unit = (
        None if selected_coordinate is None else _display_unit(metadata, selected_coordinate)
    )
    if selected_coordinate is not None and display_unit is not None:
        try:
            validate_axis_unit(selected_coordinate, display_unit)
        except ValueError as exc:
            raise VisualizationError(
                f"metadata declares invalid display unit {display_unit!r} for {selected_coordinate}"
            ) from exc
    return PlotSource(
        requested_path=requested_path,
        dataset_path=dataset_path,
        source_format=source_format,
        frame=frame,
        metadata=metadata,
        metadata_path=metadata_path if metadata is not None else None,
        source_sha256=source_sha256,
        source_integrity=integrity,
        mode=mode,
        run_id=run_id,
        spec_id=_optional_metadata_text(metadata, "spec_id"),
        generation_context_id=_optional_metadata_text(metadata, "generation_context_id"),
        saturation_coordinate=selected_coordinate,
        saturation_coordinate_column=coordinate_column,
        saturation_coordinate_si_unit=(
            None if selected_coordinate is None else AXIS_SI_UNITS[selected_coordinate]
        ),
        saturation_coordinate_display_unit=display_unit,
    )


def convert_field_for_display(
    plot_source: PlotSource,
    field: PlotCoordinate,
    frame: pd.DataFrame | None = None,
) -> pd.Series:
    display_unit = display_unit_for_field(plot_source, field)
    definition = UNITS[display_unit]
    selected_frame = frame if frame is not None else plot_source.frame
    column = "pressure_Pa" if field == "pressure" else "temperature_K"
    return selected_frame[column].map(definition.from_si)


def display_unit_for_field(plot_source: PlotSource, field: PlotCoordinate) -> str:
    return _display_unit(plot_source.metadata, field)


def _resolve_dataset_path(source: Path) -> Path:
    if source.is_dir():
        parquet = source / "dataset.parquet"
        csv = source / "dataset.csv"
        if parquet.is_file():
            return parquet
        if csv.is_file():
            return csv
        raise VisualizationError(
            f"run directory contains neither dataset.parquet nor dataset.csv: {source}"
        )
    if not source.is_file():
        raise VisualizationError(f"plot source does not exist: {source}")
    if source.suffix.lower() not in {".csv", ".parquet"}:
        raise VisualizationError("plot source must be a run directory, CSV, or Parquet")
    return source


def _hash_source(path: Path) -> str:
    try:
        return sha256_file(path)
    except OSError as exc:
        raise VisualizationError(f"could not hash plot source {path}: {exc}") from exc


def _load_metadata(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VisualizationError(f"could not read metadata {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise VisualizationError(f"metadata root must be an object: {path}")
    return cast(dict[str, Any], value)


def _verify_integrity(
    dataset_path: Path,
    source_sha256: str,
    metadata: dict[str, Any] | None,
) -> Literal["verified", "unverified"]:
    if metadata is None:
        return "unverified"
    artifact_hashes = metadata.get("artifact_hashes")
    if not isinstance(artifact_hashes, dict):
        raise VisualizationError("metadata does not contain artifact_hashes")
    expected = artifact_hashes.get(dataset_path.name)
    if not isinstance(expected, str):
        raise VisualizationError(f"metadata does not record a hash for {dataset_path.name}")
    if expected != source_sha256:
        raise VisualizationError(
            f"dataset hash mismatch for {dataset_path.name}; "
            "the source may have been modified or corrupted"
        )
    return "verified"


def _read_dataset(
    path: Path,
    source_format: Literal["csv", "parquet"],
) -> pd.DataFrame:
    try:
        frame = pd.read_parquet(path) if source_format == "parquet" else pd.read_csv(path)
    except Exception as exc:
        raise VisualizationError(f"could not load dataset {path}: {exc}") from exc
    missing = sorted(REQUIRED_IDENTITY_COLUMNS - set(frame.columns))
    if missing:
        raise VisualizationError(f"dataset is missing required columns: {', '.join(missing)}")
    return frame


def _validate_dataset_identity(frame: pd.DataFrame) -> tuple[str, str]:
    values: dict[str, str] = {}
    for column, label in (("mode", "dataset mode"), ("run_id", "run_id")):
        series = frame[column]
        if bool(series.isna().any()):
            raise VisualizationError(f"plot source must not contain null {label} values")
        normalized = series.astype(str).str.strip()
        if bool(normalized.eq("").any()):
            raise VisualizationError(f"plot source must not contain blank {label} values")
        unique = normalized.unique().tolist()
        if len(unique) != 1:
            raise VisualizationError(f"plot source must contain exactly one {label}")
        values[column] = unique[0]
    return values["mode"], values["run_id"]


def _resolve_saturation_coordinate(
    mode: str,
    metadata: dict[str, Any] | None,
    requested: PlotCoordinate | None,
) -> PlotCoordinate | None:
    if mode == "property_table":
        if requested is not None:
            raise VisualizationError(
                "saturation_coordinate is not valid for property_table datasets"
            )
        return None
    inferred: PlotCoordinate | None = None
    if metadata is not None:
        sampling = metadata.get("sampling")
        original = sampling.get("original") if isinstance(sampling, dict) else None
        if isinstance(original, dict):
            coordinates = [name for name in ("pressure", "temperature") if name in original]
            if len(coordinates) == 1:
                inferred = cast(PlotCoordinate, coordinates[0])
    if requested is not None and inferred is not None and requested != inferred:
        raise VisualizationError(
            f"requested coordinate {requested!r} conflicts with metadata coordinate {inferred!r}"
        )
    if requested is not None:
        return requested
    if inferred is not None:
        return inferred
    return None


def _display_unit(
    metadata: dict[str, Any] | None,
    coordinate: PlotCoordinate,
) -> str:
    if metadata is not None:
        original_units = metadata.get("original_units")
        if isinstance(original_units, dict):
            unit = original_units.get(coordinate)
            if isinstance(unit, str):
                return unit
    return AXIS_SI_UNITS[coordinate]


def _optional_metadata_text(
    metadata: dict[str, Any] | None,
    key: str,
) -> str | None:
    if metadata is None:
        return None
    value = metadata.get(key)
    return value if isinstance(value, str) else None
