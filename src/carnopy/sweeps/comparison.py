from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from carnopy.domain.failures import OutputError
from carnopy.domain.properties import PROPERTY_REGISTRY, REFERENCE_DEPENDENT_PROPERTIES
from carnopy.provenance import sha256_file
from carnopy.results import RunResult


@dataclass(frozen=True)
class ComparisonArtifacts:
    values_path: Path
    deltas_path: Path
    artifact_hashes: dict[str, str]


def write_comparison_artifacts(
    *,
    sweep_id: str,
    reference_model: str,
    child_run_paths: dict[str, Path],
    child_results: dict[str, RunResult],
    properties: list[str],
    comparison_directory: Path,
) -> ComparisonArtifacts:
    try:
        comparison_directory.mkdir(parents=True, exist_ok=False)
    except OSError as exc:
        raise OutputError(f"could not create comparison directory: {exc}") from exc
    values = _values_frame(
        sweep_id=sweep_id,
        reference_model=reference_model,
        child_run_paths=child_run_paths,
        child_results=child_results,
        properties=properties,
    )
    deltas = _deltas_frame(values, reference_model=reference_model)
    values_path = comparison_directory / "values.parquet"
    deltas_path = comparison_directory / "deltas.parquet"
    try:
        values.to_parquet(values_path, index=False)
        deltas.to_parquet(deltas_path, index=False)
        hashes = {
            "comparison/values.parquet": sha256_file(values_path),
            "comparison/deltas.parquet": sha256_file(deltas_path),
        }
    except Exception as exc:
        raise OutputError(f"could not write comparison artifacts: {exc}") from exc
    return ComparisonArtifacts(
        values_path=values_path,
        deltas_path=deltas_path,
        artifact_hashes=hashes,
    )


def _values_frame(
    *,
    sweep_id: str,
    reference_model: str,
    child_run_paths: dict[str, Path],
    child_results: dict[str, RunResult],
    properties: list[str],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for model, run_path in child_run_paths.items():
        frame = _read_child_dataset(run_path)
        if "state_key" not in frame.columns or "state_key_version" not in frame.columns:
            raise OutputError(f"child run for model {model} is missing sweep state keys")
        result = child_results[model]
        for _, row in frame.iterrows():
            for property_name in properties:
                definition = PROPERTY_REGISTRY[property_name]
                value = row.get(definition.column)
                rows.append(
                    {
                        "sweep_id": sweep_id,
                        "reference_model": reference_model,
                        "backend_model": model,
                        "child_run_id": result.run_id,
                        "state_key": row["state_key"],
                        "state_key_version": int(row["state_key_version"]),
                        "mode": row["mode"],
                        "fluid": row["fluid"],
                        "case_id": int(row["case_id"]),
                        "temperature_K": row.get("temperature_K"),
                        "pressure_Pa": row.get("pressure_Pa"),
                        "vapor_mass_fraction": row.get("vapor_mass_fraction"),
                        "saturation_endpoint": row.get("saturation_endpoint"),
                        "property": property_name,
                        "property_column": definition.column,
                        "unit": definition.unit,
                        "value": value,
                        "row_valid": bool(row["valid"]),
                        "failure_layer": row.get("failure_layer"),
                        "failure_code": row.get("failure_code"),
                        "failure_property": row.get("failure_property"),
                        "failure_message": row.get("failure_message"),
                    }
                )
    return pd.DataFrame(rows)


def _deltas_frame(values: pd.DataFrame, *, reference_model: str) -> pd.DataFrame:
    references = values.loc[values["backend_model"] == reference_model]
    ref_lookup = {(row.state_key, row.property): row for row in references.itertuples(index=False)}
    rows: list[dict[str, Any]] = []
    candidates = values.loc[values["backend_model"] != reference_model]
    for row in candidates.itertuples(index=False):
        reference = ref_lookup.get((row.state_key, row.property))
        reason: str | None = None
        absolute: float | None = None
        relative: float | None = None
        reference_value: float | None = None
        model_value = _finite_float(row.value)
        if row.property in REFERENCE_DEPENDENT_PROPERTIES:
            reason = "reference_dependent_property_excluded"
        elif reference is None:
            reason = "reference_property_missing"
        else:
            reference_value = _finite_float(reference.value)
            if not bool(row.row_valid):
                reason = "model_row_invalid"
            elif not bool(reference.row_valid):
                reason = "reference_row_invalid"
            elif model_value is None:
                reason = "model_property_missing"
            elif reference_value is None or reference_value == 0.0:
                reason = "reference_value_zero_or_nonfinite"
            else:
                absolute = model_value - reference_value
                relative = absolute / abs(reference_value)
        rows.append(
            {
                "sweep_id": row.sweep_id,
                "reference_model": reference_model,
                "backend_model": row.backend_model,
                "state_key": row.state_key,
                "state_key_version": row.state_key_version,
                "mode": row.mode,
                "fluid": row.fluid,
                "temperature_K": row.temperature_K,
                "pressure_Pa": row.pressure_Pa,
                "vapor_mass_fraction": row.vapor_mass_fraction,
                "saturation_endpoint": row.saturation_endpoint,
                "property": row.property,
                "unit": row.unit,
                "model_value": model_value,
                "reference_value": reference_value,
                "signed_absolute_difference": absolute,
                "signed_relative_difference": relative,
                "comparison_valid": reason is None,
                "unavailable_reason": reason,
            }
        )
    return pd.DataFrame(rows)


def _read_child_dataset(run_path: Path) -> pd.DataFrame:
    parquet = run_path / "dataset.parquet"
    csv = run_path / "dataset.csv"
    try:
        if parquet.is_file():
            return pd.read_parquet(parquet)
        if csv.is_file():
            return pd.read_csv(csv)
    except Exception as exc:
        raise OutputError(f"could not read child dataset {run_path}: {exc}") from exc
    raise OutputError(f"child run contains neither dataset.parquet nor dataset.csv: {run_path}")


def _finite_float(value: object) -> float | None:
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(numeric):
        return None
    return float(numeric)
