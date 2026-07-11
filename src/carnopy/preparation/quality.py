from __future__ import annotations

import math
from typing import Any

import pandas as pd

from carnopy.preparation.fields import ResolvedPreparation
from carnopy.preparation.grid_diagnostics import build_structured_grid_summary
from carnopy.preparation.rows import (
    PREPARED_ROW_ID_COLUMN,
    SOURCE_STATE_HASH_COLUMN,
    PreparedRows,
)

QUALITY_FLAG_COLUMNS = [
    "prepared_row_id",
    "flag_code",
    "severity",
    "scope",
    "scenario",
    "partition",
    "field",
    "metric",
    "value",
    "message",
]

STATE_COLUMNS = [
    "fluid",
    "backend_model",
    "phase",
    "temperature",
    "pressure",
    "vapor_mass_fraction",
    "saturation_endpoint",
]

QUALITY_QUANTILES = (0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99)


def build_quality_artifacts(
    *,
    frame: pd.DataFrame,
    rows: PreparedRows,
    resolved: ResolvedPreparation,
    scenario_summary: dict[str, Any] | None,
    partition_target_summaries: list[dict[str, Any]],
    matrix_diagnostics: list[dict[str, Any]] | None = None,
    baseline_diagnostics: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], pd.DataFrame]:
    flags: list[dict[str, Any]] = []
    selected_columns = _selected_numeric_columns(frame, resolved)
    finite_summaries = {
        column: _numeric_summary(frame[column]) for column in selected_columns if column in frame
    }
    flags.extend(_nonfinite_flags(frame, selected_columns))
    duplicate_summary, duplicate_flags = _duplicate_state_summary(frame, resolved)
    flags.extend(duplicate_flags)
    grid_summary = build_structured_grid_summary(frame)
    report = {
        "quality_report_schema_version": 2,
        "status": "no_eligible_rows" if not rows.prepared_rows else "completed",
        "row_counts": {
            "eligible": len(rows.prepared_rows),
            "excluded": len(rows.exclusion_rows),
        },
        "distributions": _distributions(frame),
        "finite_summaries": finite_summaries,
        "numeric_summaries_by_group": _grouped_numeric_summaries(
            frame,
            selected_columns,
        ),
        "target_summaries_by_partition": partition_target_summaries
        or _unsplit_target_summaries(frame, resolved),
        "matrix_diagnostics": {
            "status": _matrix_diagnostics_status(matrix_diagnostics),
            "fits": [] if matrix_diagnostics is None else matrix_diagnostics,
        },
        "baseline_diagnostics": {
            "status": _optional_diagnostics_status(baseline_diagnostics),
            "fits": [] if baseline_diagnostics is None else baseline_diagnostics,
        },
        "duplicate_state_candidates": duplicate_summary,
        "structured_grid": grid_summary,
        "scenarios": scenario_summary
        or {
            "scenario_count": 0,
            "partition_count": 0,
            "status": "not_configured",
            "scenarios": [],
        },
        "quality_flags": {
            "artifact": "data/quality_flags.parquet",
            "row_count": len(flags),
        },
        "advisory_policy": (
            "quality flags are advisory and do not change row eligibility or table contents"
        ),
        "estimator_definitions": {
            "std": "population standard deviation (ddof=0) over finite values",
            "quartiles_and_quantiles": (
                "linear interpolation using the (n - 1) * q sample index (Hyndman-Fan type 7)"
            ),
            "median_absolute_deviation": (
                "unscaled median of absolute deviations from the finite-value median"
            ),
            "skewness": (
                "unbiased Fisher-Pearson sample skewness; null below three finite values "
                "or for zero sample variance"
            ),
            "excess_kurtosis": (
                "unbiased Fisher excess kurtosis; null below four finite values or for "
                "zero sample variance"
            ),
        },
    }
    return report, _flags_frame(flags)


def _selected_numeric_columns(
    frame: pd.DataFrame,
    resolved: ResolvedPreparation,
) -> list[str]:
    candidates = [
        *(field.semantic_name for field in resolved.numeric_features),
        *resolved.derived_features,
        *(field.semantic_name for field in resolved.targets),
        *(field.semantic_name for field in resolved.auxiliary),
    ]
    return [
        column
        for column in dict.fromkeys(candidates)
        if column in frame
        and pd.api.types.is_numeric_dtype(frame[column])
        and not pd.api.types.is_bool_dtype(frame[column])
    ]


def _numeric_summary(series: pd.Series) -> dict[str, Any]:
    numeric = pd.to_numeric(series, errors="coerce").astype("float64")
    finite = numeric[numeric.map(math.isfinite)]
    quantiles = (
        {}
        if finite.empty
        else {
            _quantile_key(quantile): float(value)
            for quantile, value in zip(
                QUALITY_QUANTILES,
                finite.quantile(QUALITY_QUANTILES, interpolation="linear").tolist(),
                strict=True,
            )
        }
    )
    median = _finite_stat(finite, "median")
    first_quartile = quantiles.get("0.25")
    third_quartile = quantiles.get("0.75")
    sample_std = None if len(finite) < 2 else float(finite.std(ddof=1))
    return {
        "row_count": len(series),
        "missing_count": int(series.isna().sum()),
        "finite_count": len(finite),
        "nonfinite_count": int(len(numeric) - len(finite) - int(series.isna().sum())),
        "minimum": _finite_stat(finite, "min"),
        "maximum": _finite_stat(finite, "max"),
        "mean": _finite_stat(finite, "mean"),
        "std": None if finite.empty else float(finite.std(ddof=0)),
        "std_ddof": 0,
        "median": median,
        "first_quartile": first_quartile,
        "third_quartile": third_quartile,
        "interquartile_range": (
            None
            if first_quartile is None or third_quartile is None
            else third_quartile - first_quartile
        ),
        "median_absolute_deviation": (
            None if median is None else float((finite - median).abs().median())
        ),
        "quantiles": quantiles,
        "skewness": _shape_stat(finite, sample_std=sample_std, minimum_count=3, name="skew"),
        "excess_kurtosis": _shape_stat(
            finite,
            sample_std=sample_std,
            minimum_count=4,
            name="kurt",
        ),
    }


def _finite_stat(series: pd.Series, name: str) -> float | None:
    if series.empty:
        return None
    return float(getattr(series, name)())


def _quantile_key(value: float) -> str:
    return f"{value:g}"


def _shape_stat(
    series: pd.Series,
    *,
    sample_std: float | None,
    minimum_count: int,
    name: str,
) -> float | None:
    if len(series) < minimum_count or sample_std is None or sample_std == 0.0:
        return None
    value = float(getattr(series, name)())
    return value if math.isfinite(value) else None


def _nonfinite_flags(frame: pd.DataFrame, columns: list[str]) -> list[dict[str, Any]]:
    flags: list[dict[str, Any]] = []
    for column in columns:
        values = pd.to_numeric(frame[column], errors="coerce")
        invalid = frame[column].isna() | ~values.map(math.isfinite)
        for row in frame.loc[invalid, [PREPARED_ROW_ID_COLUMN, column]].itertuples(index=False):
            flags.append(
                _flag(
                    prepared_row_id=getattr(row, PREPARED_ROW_ID_COLUMN),
                    flag_code="nonfinite_selected_value",
                    severity="warning",
                    scope="row",
                    field=column,
                    metric="finite",
                    value=None,
                    message=f"selected numeric field {column!r} is missing or non-finite",
                )
            )
    return flags


def _duplicate_state_summary(
    frame: pd.DataFrame,
    resolved: ResolvedPreparation,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    group_columns = [column for column in STATE_COLUMNS if column in frame]
    if not group_columns or PREPARED_ROW_ID_COLUMN not in frame:
        return {"status": "skipped_missing_state_columns", "group_columns": group_columns}, []
    target_columns = [
        field.semantic_name for field in resolved.targets if field.semantic_name in frame
    ]
    identity_column = SOURCE_STATE_HASH_COLUMN if SOURCE_STATE_HASH_COLUMN in frame else None
    groups = frame.groupby(identity_column or group_columns, dropna=False, sort=True)
    duplicate_groups = [(key, group) for key, group in groups if len(group) > 1]
    flags: list[dict[str, Any]] = []
    conflict_count = 0
    for _, group in duplicate_groups:
        conflicting_targets = [
            column for column in target_columns if group[column].dropna().nunique(dropna=True) > 1
        ]
        if conflicting_targets:
            conflict_count += 1
        for row_id in group[PREPARED_ROW_ID_COLUMN].tolist():
            flags.append(
                _flag(
                    prepared_row_id=row_id,
                    flag_code=(
                        "duplicate_state_conflicting_targets"
                        if conflicting_targets
                        else "duplicate_state_candidate"
                    ),
                    severity="warning" if conflicting_targets else "advisory",
                    scope="row",
                    field=",".join(conflicting_targets) if conflicting_targets else None,
                    metric="duplicate_state",
                    value=float(len(group)),
                    message=(
                        "duplicate thermodynamic-state key has conflicting target values"
                        if conflicting_targets
                        else "duplicate thermodynamic-state key candidate"
                    ),
                )
            )
    summary = {
        "status": "completed",
        "group_columns": group_columns,
        "duplicate_group_count": len(duplicate_groups),
        "duplicate_row_count": int(sum(len(group) for _, group in duplicate_groups)),
        "conflicting_target_group_count": conflict_count,
    }
    if identity_column is not None:
        summary["identity_column"] = identity_column
    return summary, flags


def _distributions(frame: pd.DataFrame) -> dict[str, dict[str, int]]:
    result: dict[str, dict[str, int]] = {}
    for column in ("fluid", "phase", "backend_model"):
        if column not in frame:
            continue
        counts = frame[column].astype("string").fillna("<missing>").value_counts().sort_index()
        result[column] = {str(value): int(count) for value, count in counts.items()}
    return result


def _grouped_numeric_summaries(
    frame: pd.DataFrame,
    selected_columns: list[str],
) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for group_column in ("fluid", "phase", "backend_model"):
        if group_column not in frame:
            continue
        groups: list[dict[str, Any]] = []
        for value, group in frame.groupby(group_column, dropna=False, sort=True):
            groups.append(
                {
                    "value": "<missing>" if pd.isna(value) else str(value),
                    "row_count": len(group),
                    "fields": {
                        column: _numeric_summary(group[column])
                        for column in selected_columns
                        if column in group
                    },
                }
            )
        result[group_column] = groups
    return result


def _matrix_diagnostics_status(value: list[dict[str, Any]] | None) -> str:
    if value is None:
        return "not_requested"
    if value and all(item.get("status") == "completed" for item in value):
        return "completed"
    return "completed_with_skips"


def _optional_diagnostics_status(value: list[dict[str, Any]] | None) -> str:
    if value is None:
        return "not_requested"
    if value and all(item.get("status") == "completed" for item in value):
        return "completed"
    return "completed_with_skips"


def _unsplit_target_summaries(
    frame: pd.DataFrame,
    resolved: ResolvedPreparation,
) -> list[dict[str, Any]]:
    return [
        {
            "scenario": None,
            "partition": "all",
            "row_count": len(frame),
            "targets": _target_summaries(frame, resolved),
        }
    ]


def partition_target_summaries(
    *,
    scenario_name: str,
    partitions: dict[str, pd.DataFrame],
    resolved: ResolvedPreparation,
) -> list[dict[str, Any]]:
    return [
        {
            "scenario": scenario_name,
            "partition": partition,
            "row_count": len(partition_frame),
            "targets": _target_summaries(partition_frame, resolved),
        }
        for partition, partition_frame in sorted(partitions.items())
    ]


def _target_summaries(frame: pd.DataFrame, resolved: ResolvedPreparation) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for field in resolved.targets:
        column = field.semantic_name
        if column in frame and pd.api.types.is_numeric_dtype(frame[column]):
            result[column] = _numeric_summary(frame[column])
    return result


def _flags_frame(flags: list[dict[str, Any]]) -> pd.DataFrame:
    frame = pd.DataFrame(flags, columns=QUALITY_FLAG_COLUMNS)
    if frame.empty:
        return frame
    frame["prepared_row_id"] = frame["prepared_row_id"].astype("Int64")
    return frame


def _flag(
    *,
    prepared_row_id: Any,
    flag_code: str,
    severity: str,
    scope: str,
    field: str | None,
    metric: str | None,
    value: float | None,
    message: str,
) -> dict[str, Any]:
    row_id = (
        None
        if prepared_row_id is None
        or (isinstance(prepared_row_id, float) and math.isnan(prepared_row_id))
        else int(prepared_row_id)
    )
    return {
        "prepared_row_id": row_id,
        "flag_code": flag_code,
        "severity": severity,
        "scope": scope,
        "scenario": None,
        "partition": None,
        "field": field,
        "metric": metric,
        "value": value,
        "message": message,
    }
