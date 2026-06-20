from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from carnopy.provenance import REPORT_SCHEMA_VERSION
from carnopy.results import RunStatus


def determine_run_status(frame: pd.DataFrame) -> RunStatus:
    valid_count = int(frame["valid"].sum())
    if valid_count == len(frame):
        return "completed"
    if valid_count == 0:
        return "completed_zero_valid_rows"
    return "completed_with_invalid_rows"


def build_report(
    *,
    frame: pd.DataFrame,
    run_id: str,
    run_status: RunStatus,
    output_directory: Path,
    input_columns: list[str],
) -> dict[str, Any]:
    numeric = frame.select_dtypes(include="number")
    min_max = {
        column: {
            "min": _json_number(numeric[column].min(skipna=True)),
            "max": _json_number(numeric[column].max(skipna=True)),
        }
        for column in numeric.columns
    }
    return {
        "report_schema_version": REPORT_SCHEMA_VERSION,
        "run_id": run_id,
        "run_status": run_status,
        "row_count": len(frame),
        "valid_row_count": int(frame["valid"].sum()),
        "invalid_row_count": int((~frame["valid"]).sum()),
        "failure_counts_by_layer": _counts(frame["failure_layer"]),
        "failure_counts_by_code": _counts(frame["failure_code"]),
        "failure_counts_by_property": _counts(frame["failure_property"]),
        "phase_counts": _counts(frame["phase"]),
        "fluid_counts": _counts(frame["fluid"]),
        "min_max_by_numeric_column": min_max,
        "duplicate_input_state_count": int(
            frame.duplicated(subset=input_columns, keep=False).sum()
        ),
        "output_directory": str(output_directory),
    }


def _counts(series: pd.Series) -> dict[str, int]:
    return {
        str(key): int(value) for key, value in series.dropna().value_counts().sort_index().items()
    }


def _json_number(value: Any) -> float | int | None:
    if pd.isna(value):
        return None
    if isinstance(value, bool):
        return int(value)
    return float(value)
