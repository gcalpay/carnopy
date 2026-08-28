from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Literal, cast

import pandas as pd

from carnopy.app.scene_contracts import (
    SceneBlockContext,
    SceneContractError,
    SceneProfile,
    SceneRequest,
    SceneTopologyAxis,
)
from carnopy.app.scene_geometry import (
    ScenePointProjection,
    SceneRowExclusion,
    _project_loaded_scene_points,
    _require_retained_points,
    _validated_projection_source,
)
from carnopy.app.scene_profiles import Checkpoint, LoadedSceneProfileSource

SceneBlockTopologyStatus = Literal[
    "unavailable",
    "zero_dimensional",
    "exact",
    "incomplete",
    "missing_context",
    "duplicate_locations",
    "unsupported_dimension",
]


@dataclass(frozen=True)
class SceneTopologyLocation:
    """Retained point indices occupying one exact source-sampling location."""

    level_indices: tuple[int, ...]
    point_indices: tuple[int, ...]

    def __post_init__(self) -> None:
        if any(index < 0 for index in self.level_indices):
            raise ValueError("scene topology level indices must be non-negative")
        if not self.point_indices or tuple(sorted(self.point_indices)) != self.point_indices:
            raise ValueError("scene topology point indices must be nonempty and ordered")
        if len(set(self.point_indices)) != len(self.point_indices):
            raise ValueError("scene topology location repeats a point index")


@dataclass(frozen=True)
class SceneTopologyGapLocation:
    """One excluded source row and its exact topology location when available."""

    exclusion: SceneRowExclusion
    level_indices: tuple[int, ...] | None

    def __post_init__(self) -> None:
        if self.level_indices is not None and any(index < 0 for index in self.level_indices):
            raise ValueError("scene topology gap level indices must be non-negative")


@dataclass(frozen=True)
class SceneMissingTopologyLevels:
    """Ordered sampler levels absent strictly between retained levels in one block."""

    axis_index: int
    field_id: str
    level_indices: tuple[int, ...]

    def __post_init__(self) -> None:
        if self.axis_index < 0 or not self.field_id or not self.level_indices:
            raise ValueError("missing topology-level evidence is incomplete")
        if tuple(sorted(set(self.level_indices))) != self.level_indices:
            raise ValueError("missing topology-level indices must be unique and ordered")


@dataclass(frozen=True)
class SceneBlockTopology:
    """Exact topology evidence for one context block, without any primitives."""

    status: SceneBlockTopologyStatus
    dimension: int | None
    axes: tuple[SceneTopologyAxis, ...]
    locations: tuple[SceneTopologyLocation, ...]
    gap_locations: tuple[SceneTopologyGapLocation, ...]
    missing_intermediate_levels: tuple[SceneMissingTopologyLevels, ...]
    unlocated_point_indices: tuple[int, ...]
    missing_context_fields: tuple[str, ...]
    reason_code: str = ""
    reason: str = ""

    def __post_init__(self) -> None:
        if self.dimension is not None and not 0 <= self.dimension <= len(self.axes):
            raise ValueError("scene block topology dimension is inconsistent with its axes")
        if tuple(sorted(self.unlocated_point_indices)) != self.unlocated_point_indices:
            raise ValueError("unlocated scene point indices must be ordered")
        if len(set(self.unlocated_point_indices)) != len(self.unlocated_point_indices):
            raise ValueError("unlocated scene point indices must be unique")
        if len(set(self.missing_context_fields)) != len(self.missing_context_fields):
            raise ValueError("missing scene context fields must be unique")
        location_keys = [location.level_indices for location in self.locations]
        if location_keys != sorted(location_keys) or len(set(location_keys)) != len(location_keys):
            raise ValueError("scene topology locations must be unique and ordered")
        for location in self.locations:
            _validate_level_indices(location.level_indices, self.axes)
        for gap in self.gap_locations:
            if gap.level_indices is not None:
                _validate_level_indices(gap.level_indices, self.axes)
        if self.status == "unavailable":
            if self.dimension is not None or self.axes or self.locations:
                raise ValueError("unavailable scene topology must not contain inferred topology")
            if not self.reason_code or not self.reason:
                raise ValueError("unavailable scene topology requires an explicit reason")
        elif self.status == "zero_dimensional":
            if self.dimension != 0 or self.reason_code or self.reason:
                raise ValueError("zero-dimensional scene topology is inconsistent")
        elif self.status == "exact":
            if self.dimension not in {1, 2} or self.reason_code or self.reason:
                raise ValueError("exact scene topology must be one- or two-dimensional")
        elif not self.reason_code or not self.reason:
            raise ValueError("blocked scene topology requires an explicit reason")

    @property
    def duplicate_locations(self) -> tuple[SceneTopologyLocation, ...]:
        return tuple(location for location in self.locations if len(location.point_indices) > 1)


@dataclass(frozen=True)
class SceneTopologyBlock:
    """One deterministic context partition of retained and excluded source rows."""

    index: int
    context: SceneBlockContext
    point_indices: tuple[int, ...]
    exclusions: tuple[SceneRowExclusion, ...]
    topology: SceneBlockTopology

    def __post_init__(self) -> None:
        if self.index < 0 or not self.point_indices:
            raise ValueError("scene topology block requires retained points")
        if tuple(sorted(self.point_indices)) != self.point_indices:
            raise ValueError("scene block point indices must be ordered")
        if len(set(self.point_indices)) != len(self.point_indices):
            raise ValueError("scene block repeats a point index")
        if tuple(sorted(row.row_position for row in self.exclusions)) != tuple(
            row.row_position for row in self.exclusions
        ):
            raise ValueError("scene block exclusions must be in source-row order")


@dataclass(frozen=True)
class SceneOrphanExclusions:
    """Excluded rows in a context that retained no scene point."""

    context: SceneBlockContext
    exclusions: tuple[SceneRowExclusion, ...]

    def __post_init__(self) -> None:
        if not self.exclusions:
            raise ValueError("orphan scene exclusion groups must be nonempty")


@dataclass(frozen=True)
class SceneTopologyPartition:
    """A complete context partition and topology analysis of a point projection."""

    projection: ScenePointProjection
    blocks: tuple[SceneTopologyBlock, ...]
    orphan_exclusions: tuple[SceneOrphanExclusions, ...]

    def __post_init__(self) -> None:
        if tuple(block.index for block in self.blocks) != tuple(range(len(self.blocks))):
            raise ValueError("scene topology block indices must be contiguous")
        contexts = tuple(_context_key(block.context) for block in self.blocks)
        orphan_contexts = tuple(_context_key(group.context) for group in self.orphan_exclusions)
        if contexts != tuple(sorted(contexts)) or orphan_contexts != tuple(sorted(orphan_contexts)):
            raise ValueError("scene topology contexts must be canonically ordered")
        if set(contexts).intersection(orphan_contexts):
            raise ValueError("scene topology context is both retained and orphaned")
        point_indices = [index for block in self.blocks for index in block.point_indices]
        if sorted(point_indices) != list(range(len(self.projection.points))):
            raise ValueError("scene topology blocks do not partition retained points")
        exclusion_positions = [
            row.row_position for block in self.blocks for row in block.exclusions
        ] + [row.row_position for group in self.orphan_exclusions for row in group.exclusions]
        expected_positions = [row.row_position for row in self.projection.excluded_rows]
        if sorted(exclusion_positions) != expected_positions:
            raise ValueError("scene topology contexts do not partition excluded rows")


def analyze_scene_topology(
    profile: SceneProfile,
    request: SceneRequest,
    *,
    checkpoint: Checkpoint | None = None,
) -> SceneTopologyPartition:
    """Partition exact points by source context and analyze topology without primitives."""

    loaded, authoritative = _validated_projection_source(
        profile,
        request,
        checkpoint=checkpoint,
    )
    projection = _require_retained_points(
        _project_loaded_scene_points(
            loaded,
            authoritative,
            request,
            checkpoint=checkpoint,
        )
    )
    return _partition_loaded_scene_topology(
        loaded,
        projection,
        checkpoint=checkpoint,
    )


def _partition_loaded_scene_topology(
    loaded: LoadedSceneProfileSource,
    projection: ScenePointProjection,
    *,
    checkpoint: Checkpoint | None,
) -> SceneTopologyPartition:
    retained_by_context: dict[SceneBlockContext, list[int]] = defaultdict(list)
    excluded_by_context: dict[SceneBlockContext, list[SceneRowExclusion]] = defaultdict(list)
    for point_index, point in enumerate(projection.points):
        retained_by_context[loaded.row_contexts[point.row_position]].append(point_index)
    for exclusion in projection.excluded_rows:
        excluded_by_context[loaded.row_contexts[exclusion.row_position]].append(exclusion)

    retained_contexts = sorted(retained_by_context, key=_context_key)
    blocks: list[SceneTopologyBlock] = []
    for block_index, context in enumerate(retained_contexts):
        if checkpoint is not None:
            checkpoint()
        point_indices = tuple(retained_by_context[context])
        exclusions = tuple(excluded_by_context.pop(context, ()))
        blocks.append(
            SceneTopologyBlock(
                index=block_index,
                context=context,
                point_indices=point_indices,
                exclusions=exclusions,
                topology=_analyze_block_topology(
                    loaded,
                    projection,
                    context,
                    point_indices,
                    exclusions,
                ),
            )
        )
    orphans = tuple(
        SceneOrphanExclusions(context=context, exclusions=tuple(excluded_by_context[context]))
        for context in sorted(excluded_by_context, key=_context_key)
    )
    return SceneTopologyPartition(
        projection=projection,
        blocks=tuple(blocks),
        orphan_exclusions=orphans,
    )


def _analyze_block_topology(
    loaded: LoadedSceneProfileSource,
    projection: ScenePointProjection,
    context: SceneBlockContext,
    point_indices: tuple[int, ...],
    exclusions: tuple[SceneRowExclusion, ...],
) -> SceneBlockTopology:
    evidence = loaded.topology
    if evidence.status == "unavailable":
        return SceneBlockTopology(
            status="unavailable",
            dimension=None,
            axes=(),
            locations=(),
            gap_locations=(),
            missing_intermediate_levels=(),
            unlocated_point_indices=(),
            missing_context_fields=(),
            reason_code=evidence.reason_code,
            reason=evidence.reason,
        )

    fields = {field.field_id: field.values for field in loaded.fields}
    level_maps = tuple(
        {level: index for index, level in enumerate(axis.levels)} for axis in evidence.axes
    )
    occupied: dict[tuple[int, ...], list[int]] = defaultdict(list)
    unlocated: list[int] = []
    for point_index in point_indices:
        row_position = projection.points[point_index].row_position
        indices = _row_level_indices(row_position, evidence.axes, fields, level_maps)
        if indices is None:
            unlocated.append(point_index)
        else:
            occupied[indices].append(point_index)
    locations = tuple(
        SceneTopologyLocation(level_indices=indices, point_indices=tuple(occupied[indices]))
        for indices in sorted(occupied)
    )
    gap_locations = tuple(
        SceneTopologyGapLocation(
            exclusion=exclusion,
            level_indices=_row_level_indices(
                exclusion.row_position,
                evidence.axes,
                fields,
                level_maps,
            ),
        )
        for exclusion in exclusions
    )
    missing_levels = _missing_intermediate_levels(evidence.axes, locations)
    dimension = sum(
        len({location.level_indices[axis_index] for location in locations}) > 1
        for axis_index in range(len(evidence.axes))
    )
    missing_context = tuple(
        field for field in evidence.context_fields if getattr(context, field) is None
    )
    duplicates = tuple(location for location in locations if len(location.point_indices) > 1)

    status: SceneBlockTopologyStatus
    reason_code = ""
    reason = ""
    if missing_context:
        status = "missing_context"
        reason_code = "missing_context"
        reason = "required topology-separation context is absent"
    elif unlocated:
        status = "incomplete"
        reason_code = "unlocated_topology_point"
        reason = "one or more retained points have no exact recorded topology location"
    elif duplicates:
        status = "duplicate_locations"
        reason_code = "duplicate_topology_location"
        reason = "multiple retained source rows occupy an identical topology location"
    elif dimension == 0:
        status = "zero_dimensional"
    elif dimension <= 2:
        status = "exact"
    else:
        status = "unsupported_dimension"
        reason_code = "unsupported_topology_dimension"
        reason = f"the retained block has {dimension} varying topology dimensions"
    return SceneBlockTopology(
        status=status,
        dimension=dimension,
        axes=evidence.axes,
        locations=locations,
        gap_locations=gap_locations,
        missing_intermediate_levels=missing_levels,
        unlocated_point_indices=tuple(unlocated),
        missing_context_fields=missing_context,
        reason_code=reason_code,
        reason=reason,
    )


def _row_level_indices(
    row_position: int,
    axes: tuple[SceneTopologyAxis, ...],
    fields: dict[str, pd.Series],
    level_maps: tuple[dict[float, int], ...],
) -> tuple[int, ...] | None:
    result: list[int] = []
    for axis, level_map in zip(axes, level_maps, strict=True):
        values = fields.get(axis.field_id)
        if values is None:
            raise SceneContractError(
                "invalid_scene_profile",
                f"authoritative topology field {axis.field_id!r} is unavailable",
            )
        raw = values.iloc[row_position]
        try:
            if bool(pd.isna(cast(Any, raw))):
                return None
        except (TypeError, ValueError):
            pass
        if isinstance(raw, bool):
            raise SceneContractError(
                "invalid_scene_profile",
                f"authoritative topology field {axis.field_id!r} contains a boolean",
            )
        try:
            numeric = float(raw)
        except (TypeError, ValueError, OverflowError) as exc:
            raise SceneContractError(
                "invalid_scene_profile",
                f"authoritative topology field {axis.field_id!r} is non-numeric",
            ) from exc
        if not math.isfinite(numeric):
            return None
        numeric = 0.0 if numeric == 0.0 else numeric
        index = level_map.get(numeric)
        if index is None:
            raise SceneContractError(
                "invalid_scene_profile",
                f"authoritative topology field {axis.field_id!r} contains an unrecorded level",
            )
        result.append(index)
    return tuple(result)


def _missing_intermediate_levels(
    axes: tuple[SceneTopologyAxis, ...],
    locations: tuple[SceneTopologyLocation, ...],
) -> tuple[SceneMissingTopologyLevels, ...]:
    missing: list[SceneMissingTopologyLevels] = []
    for axis_index, axis in enumerate(axes):
        retained = {location.level_indices[axis_index] for location in locations}
        if len(retained) < 2:
            continue
        absent = tuple(
            index for index in range(min(retained) + 1, max(retained)) if index not in retained
        )
        if absent:
            missing.append(
                SceneMissingTopologyLevels(
                    axis_index=axis_index,
                    field_id=axis.field_id,
                    level_indices=absent,
                )
            )
    return tuple(missing)


def _context_key(context: SceneBlockContext) -> tuple[tuple[bool, str], ...]:
    return tuple((value is not None, value or "") for _, value in context.canonical_items())


def _validate_level_indices(
    level_indices: tuple[int, ...],
    axes: tuple[SceneTopologyAxis, ...],
) -> None:
    if len(level_indices) != len(axes):
        raise ValueError("scene topology location dimensionality disagrees with its axes")
    if any(index >= len(axis.levels) for index, axis in zip(level_indices, axes, strict=True)):
        raise ValueError("scene topology location contains an out-of-range level index")
