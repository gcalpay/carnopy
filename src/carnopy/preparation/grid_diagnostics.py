from __future__ import annotations

from itertools import pairwise
from typing import Any, cast

import numpy as np
import pandas as pd

PROPERTY_COORDINATES = ("source_temperature_K", "source_pressure_Pa")


def build_structured_grid_summary(frame: pd.DataFrame) -> dict[str, Any]:
    if "source_mode" not in frame:
        return _skipped("source mode provenance is unavailable")
    modes = sorted(frame["source_mode"].dropna().astype(str).unique())
    if len(modes) != 1:
        return _skipped("one unambiguous source mode is required", source_modes=modes)
    mode = modes[0]
    if mode != "property_table":
        return {
            "status": "skipped_unsupported_mode",
            "source_mode": mode,
            "reason": (
                "exact grid intent is currently audited only for property_table sources; "
                "saturation and vapor-fraction grids require source sampler metadata"
            ),
        }
    required = ["source_run_id", "source_fluid", "backend_model", *PROPERTY_COORDINATES]
    missing = [column for column in required if column not in frame]
    if missing:
        return _skipped("required state provenance is unavailable", missing_columns=missing)
    if frame.loc[:, list(PROPERTY_COORDINATES)].isna().any(axis=None):
        return _skipped("property-table coordinates contain missing values")
    coordinates = frame.loc[:, list(PROPERTY_COORDINATES)].astype("float64")
    if not bool(np.isfinite(coordinates.to_numpy()).all()):
        return _skipped("property-table coordinates contain non-finite values")

    groups = [
        _property_group_summary(
            group,
            source_run_id=run_id,
            source_fluid=fluid,
            backend_model=model,
        )
        for (run_id, fluid, model), group in frame.groupby(
            ["source_run_id", "source_fluid", "backend_model"],
            dropna=False,
            sort=True,
        )
    ]
    return {
        "status": "completed",
        "source_mode": mode,
        "coordinate_columns": list(PROPERTY_COORDINATES),
        "group_columns": ["source_run_id", "source_fluid", "backend_model"],
        "groups": groups,
        "interpretation": (
            "exact emitted cells only; no interpolation, extrapolation, or backend calls"
        ),
    }


def _property_group_summary(
    frame: pd.DataFrame,
    *,
    source_run_id: object,
    source_fluid: object,
    backend_model: object,
) -> dict[str, Any]:
    temperature_levels = np.sort(frame[PROPERTY_COORDINATES[0]].astype(float).unique())
    pressure_levels = np.sort(frame[PROPERTY_COORDINATES[1]].astype(float).unique())
    expected = int(len(temperature_levels) * len(pressure_levels))
    cell_counts = frame.groupby(list(PROPERTY_COORDINATES), dropna=False).size()
    observed = len(cell_counts)
    repeated = cell_counts[cell_counts > 1]
    return {
        "group": {
            "source_run_id": _group_value(source_run_id),
            "source_fluid": _group_value(source_fluid),
            "backend_model": _group_value(backend_model),
        },
        "row_count": len(frame),
        "levels": {
            PROPERTY_COORDINATES[0]: len(temperature_levels),
            PROPERTY_COORDINATES[1]: len(pressure_levels),
        },
        "expected_cells": expected,
        "expected_cell_basis": "Cartesian product of observed eligible coordinate levels",
        "observed_cells": observed,
        "missing_cells": max(expected - observed, 0),
        "coverage_fraction": None if expected == 0 else observed / expected,
        "repeated_cell_count": len(repeated),
        "repeated_row_count": int((repeated - 1).sum()),
        "coordinate_spacing": {
            PROPERTY_COORDINATES[0]: _spacing_summary(temperature_levels),
            PROPERTY_COORDINATES[1]: _spacing_summary(pressure_levels),
        },
        "disconnected_ranges": {
            "status": "not_inferred_without_sampler_contract",
            "reason": "nonuniform spacing can be intentional",
        },
        "phase_boundaries": _phase_boundary_summary(
            frame,
            temperature_levels=temperature_levels,
            pressure_levels=pressure_levels,
        ),
    }


def _spacing_summary(levels: np.ndarray) -> dict[str, Any]:
    if len(levels) < 2:
        return {
            "level_count": len(levels),
            "minimum": None if not len(levels) else float(levels[0]),
            "maximum": None if not len(levels) else float(levels[-1]),
            "spacing_count": 0,
            "minimum_spacing": None,
            "maximum_spacing": None,
            "median_spacing": None,
            "maximum_to_minimum_spacing_ratio": None,
            "uniform_spacing": None,
        }
    spacing = np.diff(levels)
    minimum = float(spacing.min())
    maximum = float(spacing.max())
    return {
        "level_count": len(levels),
        "minimum": float(levels[0]),
        "maximum": float(levels[-1]),
        "spacing_count": len(spacing),
        "minimum_spacing": minimum,
        "maximum_spacing": maximum,
        "median_spacing": float(np.median(spacing)),
        "maximum_to_minimum_spacing_ratio": maximum / minimum,
        "uniform_spacing": bool(np.allclose(spacing, spacing[0], rtol=1e-12, atol=0.0)),
    }


def _phase_boundary_summary(
    frame: pd.DataFrame,
    *,
    temperature_levels: np.ndarray,
    pressure_levels: np.ndarray,
) -> dict[str, Any]:
    if "source_phase" not in frame:
        return {"status": "skipped_missing_phase_provenance"}
    phase_sets: dict[tuple[float, float], set[str]] = {}
    for key, group in frame.groupby(list(PROPERTY_COORDINATES), dropna=False, sort=False):
        coordinate_key = cast(tuple[Any, Any], key)
        phases = {
            "<missing>" if pd.isna(value) else str(value)
            for value in group["source_phase"].tolist()
        }
        phase_sets[(float(coordinate_key[0]), float(coordinate_key[1]))] = phases
    transitions = {PROPERTY_COORDINATES[0]: 0, PROPERTY_COORDINATES[1]: 0}
    for pressure in pressure_levels:
        for left, right in pairwise(temperature_levels):
            transitions[PROPERTY_COORDINATES[0]] += _phase_transition(
                phase_sets.get((float(left), float(pressure))),
                phase_sets.get((float(right), float(pressure))),
            )
    for temperature in temperature_levels:
        for left, right in pairwise(pressure_levels):
            transitions[PROPERTY_COORDINATES[1]] += _phase_transition(
                phase_sets.get((float(temperature), float(left))),
                phase_sets.get((float(temperature), float(right))),
            )
    counts = frame["source_phase"].astype("string").fillna("<missing>").value_counts().sort_index()
    return {
        "status": "completed",
        "phase_counts": {str(value): int(count) for value, count in counts.items()},
        "multi_phase_cell_count": sum(len(phases) > 1 for phases in phase_sets.values()),
        "transition_edge_count": sum(transitions.values()),
        "transition_edges_by_coordinate": transitions,
    }


def _phase_transition(left: set[str] | None, right: set[str] | None) -> int:
    if left is None or right is None or len(left) != 1 or len(right) != 1:
        return 0
    return int(left != right)


def _group_value(value: object) -> str:
    return "<missing>" if pd.isna(cast(Any, value)) else str(value)


def _skipped(reason: str, **details: Any) -> dict[str, Any]:
    return {"status": "skipped_unsupported_shape", "reason": reason, **details}
