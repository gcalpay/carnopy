from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from typing import Any, cast

import pandas as pd

from carnopy.app.scene_contracts import (
    SceneContractError,
    SceneGapCode,
    SceneGapSummary,
    SceneProfile,
    SceneRequest,
    canonical_gap_summaries,
    validate_scene_request,
)
from carnopy.app.scene_profiles import (
    Checkpoint,
    LoadedSceneProfileSource,
    StableIdField,
    _load_scene_profile_source,
    _profile_loaded_scene_source,
)

_PROJECTION_GAP_CODES = frozenset(
    {
        "filtered",
        "source_invalid",
        "missing_selected_value",
        "nonfinite_selected_value",
    }
)
_UINT64_MAX = 2**64 - 1


@dataclass(frozen=True)
class RetainedScenePoint:
    """One exact source row retained as a renderer-neutral point."""

    row_position: int
    stable_id: int
    coordinates: tuple[float, float, float]
    scalar: float | None

    def __post_init__(self) -> None:
        if self.row_position < 0:
            raise ValueError("scene point row position must be non-negative")
        if self.stable_id < 0 or self.stable_id > _UINT64_MAX:
            raise ValueError("scene point stable ID must fit unsigned 64-bit storage")
        if len(self.coordinates) != 3 or any(
            not math.isfinite(value) for value in self.coordinates
        ):
            raise ValueError("scene point coordinates must contain three finite values")
        if self.scalar is not None and not math.isfinite(self.scalar):
            raise ValueError("scene point scalar must be finite")


@dataclass(frozen=True)
class SceneRowExclusion:
    """One source row omitted from point projection for exactly one reason."""

    row_position: int
    stable_id: int
    code: SceneGapCode
    field_id: str | None

    def __post_init__(self) -> None:
        if self.row_position < 0:
            raise ValueError("scene exclusion row position must be non-negative")
        if self.stable_id < 0 or self.stable_id > _UINT64_MAX:
            raise ValueError("scene exclusion stable ID must fit unsigned 64-bit storage")
        if self.code not in _PROJECTION_GAP_CODES:
            raise ValueError("scene row exclusion code is not a point-projection reason")
        if self.code == "source_invalid" and self.field_id is not None:
            raise ValueError("source-invalid row exclusions must not identify a field")
        if self.code != "source_invalid" and not self.field_id:
            raise ValueError("field-specific row exclusions require a field ID")


@dataclass(frozen=True)
class ScenePointProjection:
    """Exact retained points and one deterministic exclusion reason per source row."""

    profile: SceneProfile
    request: SceneRequest
    stable_id_field: StableIdField
    points: tuple[RetainedScenePoint, ...]
    excluded_rows: tuple[SceneRowExclusion, ...]
    exclusions: tuple[SceneGapSummary, ...]

    def __post_init__(self) -> None:
        if self.profile.binding != self.request.binding:
            raise ValueError("scene projection profile and request bindings disagree")
        if self.stable_id_field not in {"case_id", "prepared_row_id"}:
            raise ValueError("scene projection stable ID field is invalid")
        positions = [point.row_position for point in self.points]
        stable_ids = [point.stable_id for point in self.points]
        if positions != sorted(positions):
            raise ValueError("scene projection points are not in source-row order")
        excluded_positions = [row.row_position for row in self.excluded_rows]
        excluded_stable_ids = [row.stable_id for row in self.excluded_rows]
        if excluded_positions != sorted(excluded_positions):
            raise ValueError("scene exclusions are not in source-row order")
        if len(set(positions)) != len(positions):
            raise ValueError("scene projection repeats a source row position")
        if len(set(stable_ids)) != len(stable_ids):
            raise ValueError("scene projection repeats a stable source ID")
        if len(set(excluded_positions)) != len(excluded_positions):
            raise ValueError("scene projection repeats an excluded source row position")
        if len(set(excluded_stable_ids)) != len(excluded_stable_ids):
            raise ValueError("scene projection repeats an excluded stable source ID")
        if any(position >= self.profile.source_row_count for position in positions):
            raise ValueError("scene projection contains an out-of-range source row position")
        if any(position >= self.profile.source_row_count for position in excluded_positions):
            raise ValueError("scene exclusion contains an out-of-range source row position")
        if sorted([*positions, *excluded_positions]) != list(range(self.profile.source_row_count)):
            raise ValueError("scene projection row evidence does not partition source rows")
        if len(set([*stable_ids, *excluded_stable_ids])) != self.profile.source_row_count:
            raise ValueError("scene projection stable IDs do not partition source rows")
        if any(
            gap.block_index is not None or gap.code not in _PROJECTION_GAP_CODES
            for gap in self.exclusions
        ):
            raise ValueError("point projection contains a non-projection gap summary")
        if tuple(self.exclusions) != canonical_gap_summaries(self.exclusions):
            raise ValueError("scene point exclusions are not canonically ordered")
        if self.exclusions != _summarize_excluded_rows(self.excluded_rows):
            raise ValueError("scene point exclusion summaries disagree with excluded rows")
        if self.retained_row_count + self.excluded_row_count != self.profile.source_row_count:
            raise ValueError("scene point projection does not account for every source row")

    @property
    def retained_row_count(self) -> int:
        return len(self.points)

    @property
    def excluded_row_count(self) -> int:
        return len(self.excluded_rows)


def project_scene_points(
    profile: SceneProfile,
    request: SceneRequest,
    *,
    checkpoint: Checkpoint | None = None,
) -> ScenePointProjection:
    """Revalidate one profiled request and retain only exact finite source points."""

    loaded, authoritative = _validated_projection_source(
        profile,
        request,
        checkpoint=checkpoint,
    )
    projection = _project_loaded_scene_points(
        loaded,
        authoritative,
        request,
        checkpoint=checkpoint,
    )
    return _require_retained_points(projection)


def _validated_projection_source(
    profile: SceneProfile,
    request: SceneRequest,
    *,
    checkpoint: Checkpoint | None,
) -> tuple[LoadedSceneProfileSource, SceneProfile]:
    if profile.binding != request.binding:
        raise SceneContractError(
            "invalid_scene_request",
            "scene request binding disagrees with its accepted profile",
        )
    if not profile.build_eligible:
        raise SceneContractError(
            "invalid_scene_profile",
            "scene profile is not eligible for point projection",
            details={"reason": profile.ineligible_reason},
        )
    loaded = _load_scene_profile_source(request.binding, checkpoint=checkpoint)
    authoritative = _profile_loaded_scene_source(loaded, checkpoint=checkpoint)
    if authoritative != profile:
        raise SceneContractError(
            "invalid_scene_profile",
            "scene profile no longer matches the authoritative source profile",
        )
    validate_scene_request(request, authoritative.fields)
    return loaded, authoritative


def _require_retained_points(projection: ScenePointProjection) -> ScenePointProjection:
    if projection.points:
        return projection
    raise SceneContractError(
        "scene_no_retained_points",
        "scene filters and selected fields retain no exact source points",
        details={
            "source_row_count": projection.profile.source_row_count,
            "exclusions": [gap.model_dump(mode="json") for gap in projection.exclusions],
        },
    )


def _project_loaded_scene_points(
    loaded: LoadedSceneProfileSource,
    profile: SceneProfile,
    request: SceneRequest,
    *,
    checkpoint: Checkpoint | None,
) -> ScenePointProjection:
    fields = {field.field_id: field for field in loaded.fields}
    selected_field_ids = tuple(
        dict.fromkeys(
            field_id
            for field_id in (
                request.x_field,
                request.y_field,
                request.z_field,
                request.scalar_field,
            )
            if field_id is not None
        )
    )
    points: list[RetainedScenePoint] = []
    excluded_rows: list[SceneRowExclusion] = []
    for row_position in range(loaded.source_row_count):
        if checkpoint is not None and row_position % 1_024 == 0:
            checkpoint()
        if not bool(loaded.source_valid.iloc[row_position]):
            excluded_rows.append(_row_exclusion(loaded, row_position, "source_invalid", None))
            continue
        failed_filter = next(
            (
                filter_value
                for filter_value in request.filters
                if not filter_value.matches(fields[filter_value.field_id].values.iloc[row_position])
            ),
            None,
        )
        if failed_filter is not None:
            excluded_rows.append(
                _row_exclusion(loaded, row_position, "filtered", failed_filter.field_id)
            )
            continue
        numeric_values: dict[str, float] = {}
        row_excluded = False
        for field_id in selected_field_ids:
            raw = fields[field_id].values.iloc[row_position]
            if _is_missing(raw):
                excluded_rows.append(
                    _row_exclusion(
                        loaded,
                        row_position,
                        "missing_selected_value",
                        field_id,
                    )
                )
                row_excluded = True
                break
            numeric = _finite_numeric(raw, field_id)
            if numeric is None:
                excluded_rows.append(
                    _row_exclusion(
                        loaded,
                        row_position,
                        "nonfinite_selected_value",
                        field_id,
                    )
                )
                row_excluded = True
                break
            numeric_values[field_id] = numeric
        if row_excluded:
            continue
        points.append(
            RetainedScenePoint(
                row_position=row_position,
                stable_id=loaded.stable_ids[row_position],
                coordinates=(
                    numeric_values[request.x_field],
                    numeric_values[request.y_field],
                    numeric_values[request.z_field],
                ),
                scalar=(
                    None if request.scalar_field is None else numeric_values[request.scalar_field]
                ),
            )
        )
    if checkpoint is not None:
        checkpoint()
    exact_exclusions = tuple(excluded_rows)
    return ScenePointProjection(
        profile=profile,
        request=request,
        stable_id_field=loaded.stable_id_field,
        points=tuple(points),
        excluded_rows=exact_exclusions,
        exclusions=_summarize_excluded_rows(exact_exclusions),
    )


def _row_exclusion(
    loaded: LoadedSceneProfileSource,
    row_position: int,
    code: SceneGapCode,
    field_id: str | None,
) -> SceneRowExclusion:
    return SceneRowExclusion(
        row_position=row_position,
        stable_id=loaded.stable_ids[row_position],
        code=code,
        field_id=field_id,
    )


def _summarize_excluded_rows(
    rows: tuple[SceneRowExclusion, ...],
) -> tuple[SceneGapSummary, ...]:
    counts = Counter((row.code, row.field_id) for row in rows)
    return canonical_gap_summaries(
        SceneGapSummary(code=code, count=count, field_id=field_id)
        for (code, field_id), count in counts.items()
    )


def _is_missing(value: object) -> bool:
    try:
        return bool(pd.isna(cast(Any, value)))
    except (TypeError, ValueError):
        return False


def _finite_numeric(value: object, field_id: str) -> float | None:
    if isinstance(value, bool):
        raise SceneContractError(
            "invalid_scene_profile",
            f"authoritative numeric scene field {field_id!r} contains a boolean",
        )
    try:
        numeric = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError, OverflowError) as exc:
        raise SceneContractError(
            "invalid_scene_profile",
            f"authoritative numeric scene field {field_id!r} contains a non-numeric value",
        ) from exc
    if not math.isfinite(numeric):
        return None
    return 0.0 if numeric == 0.0 else numeric
