from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd

from carnopy.visualization.fields import get_field
from carnopy.visualization.models import Advisory, VisualizationError
from carnopy.visualization.requests import ExactFilter, PlotScale

NUMERIC_FILTER_RTOL = 1e-9
NUMERIC_FILTER_ATOL = 1e-12
DYNAMIC_RANGE_ADVISORY_THRESHOLD = 100.0


@dataclass(frozen=True)
class FilterMatch:
    field: str
    requested_value: float | str
    matched_values: tuple[float | str, ...]


@dataclass(frozen=True)
class SelectionResult:
    frame: pd.DataFrame
    selected_fluids: tuple[str, ...]
    filter_matches: tuple[FilterMatch, ...]


@dataclass(frozen=True)
class GroupingResolution:
    group_by: str | None
    varying_coordinate: str | None


def select_rows(
    frame: pd.DataFrame,
    *,
    fluids: Sequence[str] | None = None,
    filters: Sequence[ExactFilter] = (),
) -> SelectionResult:
    selected_fluids = select_fluids(frame, fluids)
    selected = frame.loc[frame["fluid"].isin(selected_fluids)].copy()
    matches: list[FilterMatch] = []
    for exact_filter in filters:
        selected, match = _apply_filter(selected, exact_filter)
        matches.append(match)
    if selected.empty:
        raise VisualizationError("visualization selection produced no rows")
    return SelectionResult(selected, tuple(selected_fluids), tuple(matches))


def select_fluids(frame: pd.DataFrame, requested: Sequence[str] | None) -> list[str]:
    available = sorted(frame["fluid"].dropna().astype(str).unique().tolist())
    if not available:
        raise VisualizationError("source dataset contains no fluids")
    if not requested:
        if len(available) == 1:
            return available
        raise VisualizationError(
            "source contains multiple fluids; select one or more with --fluid. "
            f"Available fluids: {', '.join(available)}"
        )
    selected: list[str] = []
    lookup = {fluid.casefold(): fluid for fluid in available}
    for name in requested:
        match = lookup.get(name.casefold())
        if match is None:
            raise VisualizationError(
                f"fluid {name!r} is not present. Available fluids: {', '.join(available)}"
            )
        if match not in selected:
            selected.append(match)
    return sorted(selected, key=str.casefold)


def resolve_group_by(
    frame: pd.DataFrame,
    *,
    axis_fields: Iterable[str],
    sampling_fields: Iterable[str],
    requested: str | None,
) -> GroupingResolution:
    axes = set(axis_fields)
    sampling = tuple(sampling_fields)
    varying = [
        field
        for field in sampling
        if get_field(field).column in frame.columns
        and frame[get_field(field).column].nunique(dropna=True) > 1
    ]
    if requested is not None:
        definition = get_field(requested)
        if definition.column in frame.columns and bool(frame[definition.column].isna().any()):
            raise VisualizationError(f"group-by field {requested!r} contains null values")
        requested_varies = (
            definition.column in frame.columns and frame[definition.column].nunique(dropna=True) > 1
        )
        if not definition.group_allowed or not requested_varies:
            available = ", ".join(varying) or "none"
            raise VisualizationError(
                f"group-by field {requested!r} is not a varying grouping candidate; "
                f"available candidates: {available}"
            )
        unresolved_sets: list[tuple[str, ...]] = []
        for _, group in frame.groupby(definition.column, sort=False, dropna=False):
            unresolved_sets.append(
                tuple(
                    field
                    for field in sampling
                    if field != requested
                    and get_field(field).column in group.columns
                    and group[get_field(field).column].nunique(dropna=True) > 1
                )
            )
        if any(len(fields) > 1 for fields in unresolved_sets):
            unresolved = sorted({field for fields in unresolved_sets for field in fields})
            raise VisualizationError(
                "generic x-y curve plot remains ambiguous after grouping; "
                f"unresolved coordinates: {', '.join(unresolved)}"
            )
        varying_paths = sorted({field for fields in unresolved_sets for field in fields})
        if len(varying_paths) > 1:
            raise VisualizationError(
                "generic x-y groups do not share one deterministic path coordinate; "
                f"observed coordinates: {', '.join(varying_paths)}"
            )
        return GroupingResolution(
            group_by=requested,
            varying_coordinate=varying_paths[0] if varying_paths else None,
        )
    if not varying:
        return GroupingResolution(group_by=None, varying_coordinate=None)
    if len(varying) == 1:
        return GroupingResolution(
            group_by=None,
            varying_coordinate=varying[0],
        )
    axis_varying = [field for field in varying if field in axes]
    non_axis_varying = [field for field in varying if field not in axes]
    if len(axis_varying) == 1 and len(non_axis_varying) == 1:
        return GroupingResolution(
            group_by=non_axis_varying[0],
            varying_coordinate=axis_varying[0],
        )
    if len(varying) > 1:
        raise VisualizationError(
            "Generic x-y curve plot is ambiguous because multiple independent "
            "coordinates remain. Specify --group-by using one of: "
            f"{', '.join(varying)}."
        )
    raise AssertionError("unreachable grouping state")


def row_valid_mask(frame: pd.DataFrame) -> pd.Series:
    valid = frame["valid"]
    if valid.dtype == object:
        return valid.astype(str).str.casefold().eq("true")
    return valid.astype(bool)


def numeric_field_values(
    frame: pd.DataFrame,
    field: str,
) -> tuple[pd.Series, pd.Series]:
    definition = get_field(field)
    if definition.kind != "numeric":
        raise VisualizationError(f"field {field!r} is not numeric")
    source_field = (
        get_field(definition.required_property)
        if definition.required_property is not None
        else definition
    )
    if source_field.column not in frame.columns:
        required = definition.required_property or field
        raise VisualizationError(
            f"field {field!r} requires emitted {required!r}, "
            "which is not present in the source dataset"
        )
    source = pd.to_numeric(frame[source_field.column], errors="coerce")
    supported = pd.Series(
        np.isfinite(source.to_numpy(dtype=float)),
        index=frame.index,
    )
    if definition.derivation == "reciprocal":
        supported &= source > 0.0
        values = pd.Series(np.nan, index=frame.index, dtype=float)
        values.loc[supported] = 1.0 / source.loc[supported]
        return values, supported
    return source.astype(float), supported


def dynamic_range_advisories(
    values: Iterable[float],
    *,
    scale: PlotScale,
    subject: str,
) -> tuple[Advisory, ...]:
    finite = [float(value) for value in values if math.isfinite(float(value))]
    if scale != "linear" or not finite or any(value <= 0.0 for value in finite):
        return ()
    minimum = min(finite)
    maximum = max(finite)
    ratio = maximum / minimum
    if ratio < DYNAMIC_RANGE_ADVISORY_THRESHOLD:
        return ()
    return (
        Advisory(
            code="large_linear_dynamic_range",
            message=(
                f"the linear {subject} range spans {ratio:.6g}:1; consider logarithmic scaling"
            ),
            dynamic_range_ratio=ratio,
        ),
    )


def _apply_filter(
    frame: pd.DataFrame,
    exact_filter: ExactFilter,
) -> tuple[pd.DataFrame, FilterMatch]:
    definition = get_field(exact_filter.field)
    if definition.column not in frame.columns:
        raise VisualizationError(
            f"filter field {exact_filter.field!r} is not present in the source dataset"
        )
    series = frame[definition.column]
    if definition.kind == "numeric":
        try:
            requested = float(exact_filter.value)
        except (TypeError, ValueError) as exc:
            raise VisualizationError(
                f"numeric filter {exact_filter.field!r} requires a finite number"
            ) from exc
        if not math.isfinite(requested):
            raise VisualizationError(
                f"numeric filter {exact_filter.field!r} requires a finite number"
            )
        numeric = pd.to_numeric(series, errors="coerce")
        mask = numeric.map(
            lambda value: bool(
                pd.notna(value)
                and math.isclose(
                    float(value),
                    requested,
                    rel_tol=NUMERIC_FILTER_RTOL,
                    abs_tol=NUMERIC_FILTER_ATOL,
                )
            )
        )
        matched = sorted({float(value) for value in numeric.loc[mask].dropna().tolist()})
        canonical = {_canonical_float(value) for value in matched}
        if len(canonical) > 1:
            raise VisualizationError(
                f"numeric filter {exact_filter.field}={requested!r} matches multiple "
                f"distinct emitted levels: {matched}"
            )
        matched_values: tuple[float | str, ...] = tuple(matched)
        requested_value: float | str = requested
    else:
        requested_text = str(exact_filter.value).strip().casefold()
        if not requested_text:
            raise VisualizationError(
                f"categorical filter {exact_filter.field!r} requires a non-empty value"
            )
        normalized = series.astype("string").str.strip().str.casefold()
        mask = normalized.eq(requested_text).fillna(False)
        matched_values = tuple(sorted(series.loc[mask].dropna().astype(str).unique().tolist()))
        requested_value = str(exact_filter.value)
    if not bool(mask.any()):
        raise VisualizationError(
            f"filter {exact_filter.field}={exact_filter.value!r} matches no rows"
        )
    return (
        frame.loc[mask].copy(),
        FilterMatch(
            field=exact_filter.field,
            requested_value=requested_value,
            matched_values=matched_values,
        ),
    )


def _canonical_float(value: float) -> str:
    return format(0.0 if value == 0.0 else value, ".15g")
