from __future__ import annotations

import math
from typing import Any

import pandas as pd

from carnopy.preparation.fields import ResolvedPreparation
from carnopy.preparation.rows import PREPARED_ROW_ID_COLUMN, PreparedRows

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


def build_quality_artifacts(
    *,
    frame: pd.DataFrame,
    rows: PreparedRows,
    resolved: ResolvedPreparation,
    scenario_summary: dict[str, Any] | None,
    partition_target_summaries: list[dict[str, Any]],
) -> tuple[dict[str, Any], pd.DataFrame]:
    flags: list[dict[str, Any]] = []
    selected_columns = _selected_numeric_columns(frame, resolved)
    finite_summaries = {
        column: _numeric_summary(frame[column]) for column in selected_columns if column in frame
    }
    flags.extend(_nonfinite_flags(frame, selected_columns))
    duplicate_summary, duplicate_flags = _duplicate_state_summary(frame, resolved)
    flags.extend(duplicate_flags)
    grid_summary = _structured_grid_summary(frame)
    report = {
        "quality_report_schema_version": 1,
        "status": "no_eligible_rows" if not rows.prepared_rows else "completed",
        "row_counts": {
            "eligible": len(rows.prepared_rows),
            "excluded": len(rows.exclusion_rows),
        },
        "distributions": _distributions(frame),
        "finite_summaries": finite_summaries,
        "target_summaries_by_partition": partition_target_summaries
        or _unsplit_target_summaries(frame, resolved),
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
        if column in frame and pd.api.types.is_numeric_dtype(frame[column])
    ]


def _numeric_summary(series: pd.Series) -> dict[str, Any]:
    numeric = pd.to_numeric(series, errors="coerce")
    finite = numeric[numeric.map(math.isfinite)]
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
    }


def _finite_stat(series: pd.Series, name: str) -> float | None:
    if series.empty:
        return None
    return float(getattr(series, name)())


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
    groups = frame.groupby(group_columns, dropna=False, sort=True)
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
    return (
        {
            "status": "completed",
            "group_columns": group_columns,
            "duplicate_group_count": len(duplicate_groups),
            "duplicate_row_count": int(sum(len(group) for _, group in duplicate_groups)),
            "conflicting_target_group_count": conflict_count,
        },
        flags,
    )


def _structured_grid_summary(frame: pd.DataFrame) -> dict[str, Any]:
    coordinate_columns = [
        column
        for column in ("temperature", "pressure", "vapor_mass_fraction")
        if column in frame and pd.api.types.is_numeric_dtype(frame[column])
    ]
    if len(coordinate_columns) < 2:
        return {
            "status": "skipped_unsupported_shape",
            "reason": "fewer than two numeric independent coordinates are available",
            "coordinate_columns": coordinate_columns,
        }
    grouping = [column for column in ("fluid", "backend_model", "phase") if column in frame]
    group_items: list[tuple[object, pd.DataFrame]]
    if not grouping:
        group_items = [((), frame)]
    else:
        group_items = [
            (key, group) for key, group in frame.groupby(grouping, dropna=False, sort=True)
        ]
    summaries: list[dict[str, Any]] = []
    for key, group in group_items:
        levels = {column: int(group[column].nunique(dropna=False)) for column in coordinate_columns}
        expected = math.prod(levels.values())
        observed = int(group.drop_duplicates(coordinate_columns).shape[0])
        summaries.append(
            {
                "group": _group_dict(grouping, key),
                "coordinate_columns": coordinate_columns,
                "levels": levels,
                "expected_cells": int(expected),
                "observed_cells": observed,
                "missing_cells": int(max(expected - observed, 0)),
            }
        )
    return {"status": "completed", "groups": summaries}


def _group_dict(columns: list[str], key: object) -> dict[str, str]:
    if not columns:
        return {}
    values = key if isinstance(key, tuple) else (key,)
    return {column: str(value) for column, value in zip(columns, values, strict=True)}


def _distributions(frame: pd.DataFrame) -> dict[str, dict[str, int]]:
    result: dict[str, dict[str, int]] = {}
    for column in ("fluid", "phase", "backend_model"):
        if column not in frame:
            continue
        counts = frame[column].astype("string").fillna("<missing>").value_counts().sort_index()
        result[column] = {str(value): int(count) for value, count in counts.items()}
    return result


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
