from __future__ import annotations

import hashlib
import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

import pandas as pd

from carnopy.domain.failures import ConfigError
from carnopy.preparation.models import (
    PartitionName,
    ScenarioConfig,
    TransformationConfig,
    TransformMethod,
)


@dataclass(frozen=True)
class ScenarioOutput:
    name: str
    kind: str
    partitions: dict[str, pd.DataFrame]
    metadata: dict[str, Any]


def build_scenario_outputs(
    scenarios: tuple[ScenarioConfig, ...],
    frame: pd.DataFrame,
    *,
    source_kind: str,
) -> list[ScenarioOutput]:
    outputs: list[ScenarioOutput] = []
    for scenario in scenarios:
        partitions = _partition_frame(scenario, frame, source_kind=source_kind)
        transformed, transformations = _apply_transformations(scenario, partitions)
        outputs.append(
            ScenarioOutput(
                name=scenario.name,
                kind=scenario.kind,
                partitions=transformed,
                metadata={
                    "name": scenario.name,
                    "kind": scenario.kind,
                    "configuration": scenario.model_dump(mode="json"),
                    "partition_counts": {
                        partition: len(partition_frame)
                        for partition, partition_frame in transformed.items()
                    },
                    "transformations": transformations,
                },
            )
        )
    return outputs


def _partition_frame(
    scenario: ScenarioConfig,
    frame: pd.DataFrame,
    *,
    source_kind: str,
) -> dict[str, pd.DataFrame]:
    if scenario.kind == "unsplit":
        return {"all": frame.copy()}
    if scenario.kind == "shuffle":
        return _shuffle_partitions(scenario, frame)
    if scenario.kind == "range_holdout":
        return _range_holdout_partitions(scenario, frame)
    if scenario.kind == "coordinate_block":
        return _coordinate_block_partitions(scenario, frame)
    return _categorical_holdout_partitions(scenario, frame, source_kind=source_kind)


def _shuffle_partitions(scenario: ScenarioConfig, frame: pd.DataFrame) -> dict[str, pd.DataFrame]:
    if not math.isclose(sum(scenario.partitions.values()), 1.0, rel_tol=1e-9, abs_tol=1e-12):
        raise ConfigError(f"shuffle scenario {scenario.name!r} partition ratios must sum to 1")
    if "source_row_hash" not in frame.columns:
        raise ConfigError(f"shuffle scenario {scenario.name!r} requires source_row_hash")
    counts = _allocated_counts(len(frame), scenario.partitions)
    scored = sorted(
        (
            _hash_score(f"{scenario.name}|{scenario.seed}|{row['source_row_hash']}"),
            index,
        )
        for index, row in frame.iterrows()
    )
    partitions: dict[str, pd.DataFrame] = {}
    offset = 0
    for partition, count in counts.items():
        selected = [index for _, index in scored[offset : offset + count]]
        partitions[partition] = frame.loc[selected].copy()
        offset += count
    _require_non_empty_partitions(scenario.name, partitions)
    return partitions


def _range_holdout_partitions(
    scenario: ScenarioConfig,
    frame: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    assert scenario.field is not None
    values = _numeric_column(frame, scenario.field, scenario.name)
    ranges = {
        partition: _range_bounds(scenario.name, partition, spec)
        for partition, spec in scenario.holdouts.items()
    }
    assignments = _assign_by_match(
        scenario,
        frame,
        lambda index: [
            partition
            for partition, bounds in ranges.items()
            if _in_bounds(float(values.iloc[index]), bounds)
        ],
    )
    return _frames_from_assignments(scenario, frame, assignments)


def _coordinate_block_partitions(
    scenario: ScenarioConfig,
    frame: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    blocks: dict[PartitionName, dict[str, tuple[float, float]]] = {}
    for partition, spec in scenario.holdouts.items():
        if not isinstance(spec, dict) or not spec:
            raise ConfigError(
                f"coordinate_block scenario {scenario.name!r} partition {partition!r} "
                "requires field range mappings"
            )
        block: dict[str, tuple[float, float]] = {}
        for field, bounds in spec.items():
            field_name = str(field).strip()
            _numeric_column(frame, field_name, scenario.name)
            block[field_name] = _range_bounds(scenario.name, partition, bounds)
        blocks[partition] = block

    assignments = _assign_by_match(
        scenario,
        frame,
        lambda index: [
            partition
            for partition, block in blocks.items()
            if all(
                _in_bounds(float(frame.iloc[index][field]), bounds)
                for field, bounds in block.items()
            )
        ],
    )
    return _frames_from_assignments(scenario, frame, assignments)


def _categorical_holdout_partitions(
    scenario: ScenarioConfig,
    frame: pd.DataFrame,
    *,
    source_kind: str,
) -> dict[str, pd.DataFrame]:
    field = {
        "leave_fluid_out": "fluid",
        "phase_holdout": "phase",
        "model_holdout": "backend_model",
    }[scenario.kind]
    if scenario.kind == "model_holdout" and source_kind != "model_sweep":
        raise ConfigError("model_holdout scenarios require a model-sweep source")
    if field not in frame.columns:
        raise ConfigError(f"{scenario.kind} scenario {scenario.name!r} requires column {field!r}")
    holdouts = {
        partition: _category_values(scenario.name, partition, spec)
        for partition, spec in scenario.holdouts.items()
    }
    seen: dict[str, str] = {}
    for partition, values in holdouts.items():
        for value in values:
            if value in seen:
                raise ConfigError(
                    f"scenario {scenario.name!r} category {value!r} appears in both "
                    f"{seen[value]!r} and {partition!r}"
                )
            seen[value] = partition
    assignments = _assign_by_match(
        scenario,
        frame,
        lambda index: [
            partition
            for partition, values in holdouts.items()
            if str(frame.iloc[index][field]) in values
        ],
    )
    return _frames_from_assignments(scenario, frame, assignments)


def _assign_by_match(
    scenario: ScenarioConfig,
    frame: pd.DataFrame,
    matcher: Callable[[int], list[str]],
) -> dict[int, str]:
    assignments: dict[int, str] = {}
    assert scenario.remainder is not None
    for position in range(len(frame)):
        matches = matcher(position)
        if len(matches) > 1:
            raise ConfigError(
                f"scenario {scenario.name!r} has overlapping holdouts for source row {position}"
            )
        assignments[position] = matches[0] if matches else scenario.remainder
    return assignments


def _frames_from_assignments(
    scenario: ScenarioConfig,
    frame: pd.DataFrame,
    assignments: dict[int, str],
) -> dict[str, pd.DataFrame]:
    assert scenario.remainder is not None
    partitions = sorted({str(partition) for partition in scenario.holdouts} | {scenario.remainder})
    result = {
        partition: frame.iloc[
            [position for position in range(len(frame)) if assignments[position] == partition]
        ].copy()
        for partition in partitions
    }
    _require_non_empty_partitions(scenario.name, result)
    if sum(len(partition_frame) for partition_frame in result.values()) != len(frame):
        raise ConfigError(f"scenario {scenario.name!r} did not assign every row exactly once")
    return result


def _apply_transformations(
    scenario: ScenarioConfig,
    partitions: dict[str, pd.DataFrame],
) -> tuple[dict[str, pd.DataFrame], list[dict[str, Any]]]:
    result = {name: partition.copy() for name, partition in partitions.items()}
    summaries: list[dict[str, Any]] = []
    output_columns: set[str] = set().union(*(set(frame.columns) for frame in result.values()))
    fit_partition = "all" if scenario.kind == "unsplit" else "train"
    if scenario.transformations and fit_partition not in result:
        raise ConfigError(
            f"scenario {scenario.name!r} transformations require a {fit_partition!r} partition"
        )
    for transform in scenario.transformations:
        output_column = f"{transform.field}__{'__'.join(transform.methods)}"
        if output_column in output_columns:
            raise ConfigError(
                f"scenario {scenario.name!r} transformation output {output_column!r} "
                "collides with an existing column"
            )
        partition_values = _initial_transform_values(scenario, transform, result)
        steps: list[dict[str, Any]] = []
        for method in transform.methods:
            partition_values, step = _apply_transform_step(
                scenario,
                method,
                partition_values,
                fit_partition=fit_partition,
            )
            steps.append(step)
        for partition_name, values in partition_values.items():
            result[partition_name][output_column] = values.to_numpy()
        output_columns.add(output_column)
        summaries.append(
            {
                "field": transform.field,
                "methods": list(transform.methods),
                "output_column": output_column,
                "fit_partition": fit_partition,
                "steps": steps,
            }
        )
    return result, summaries


def _initial_transform_values(
    scenario: ScenarioConfig,
    transform: TransformationConfig,
    partitions: dict[str, pd.DataFrame],
) -> dict[str, pd.Series]:
    values: dict[str, pd.Series] = {}
    for partition_name, frame in partitions.items():
        if transform.field not in frame.columns:
            raise ConfigError(
                f"scenario {scenario.name!r} transformation field "
                f"{transform.field!r} is unavailable"
            )
        try:
            series = frame[transform.field].astype(float)
        except (TypeError, ValueError) as exc:
            raise ConfigError(
                f"scenario {scenario.name!r} transformation field "
                f"{transform.field!r} is not numeric"
            ) from exc
        if not bool(series.map(math.isfinite).all()):
            raise ConfigError(
                f"scenario {scenario.name!r} transformation field "
                f"{transform.field!r} contains non-finite values"
            )
        values[partition_name] = series
    return values


def _apply_transform_step(
    scenario: ScenarioConfig,
    method: TransformMethod,
    values: dict[str, pd.Series],
    *,
    fit_partition: str,
) -> tuple[dict[str, pd.Series], dict[str, Any]]:
    fit = values[fit_partition]
    if method == "log10":
        for partition, series in values.items():
            if not bool((series > 0.0).all()):
                raise ConfigError(
                    f"scenario {scenario.name!r} log10 transformation has nonpositive "
                    f"values in partition {partition!r}"
                )
        return (
            {partition: series.map(math.log10) for partition, series in values.items()},
            {"method": "log10"},
        )
    if method == "standard":
        mean = float(fit.mean())
        std = float(fit.std(ddof=0))
        if not math.isfinite(std) or std <= 0.0:
            raise ConfigError(
                f"scenario {scenario.name!r} standard transformation has zero train std"
            )
        return (
            {partition: (series - mean) / std for partition, series in values.items()},
            {"method": "standard", "mean": mean, "std": std, "std_ddof": 0},
        )
    minimum = float(fit.min())
    maximum = float(fit.max())
    value_range = maximum - minimum
    if not math.isfinite(value_range) or value_range <= 0.0:
        raise ConfigError(f"scenario {scenario.name!r} minmax transformation has zero train range")
    return (
        {partition: (series - minimum) / value_range for partition, series in values.items()},
        {"method": "minmax", "min": minimum, "max": maximum},
    )


def _allocated_counts(
    row_count: int,
    partitions: dict[PartitionName, float],
) -> dict[str, int]:
    ideals = {partition: row_count * ratio for partition, ratio in partitions.items()}
    counts = {partition: math.floor(value) for partition, value in ideals.items()}
    remaining = row_count - sum(counts.values())
    ranked = sorted(
        partitions,
        key=lambda partition: (ideals[partition] - counts[partition], partition),
        reverse=True,
    )
    for partition in ranked[:remaining]:
        counts[partition] += 1
    if any(count <= 0 for count in counts.values()):
        raise ConfigError("shuffle scenario produced an empty positive partition")
    return {str(partition): count for partition, count in counts.items()}


def _range_bounds(
    scenario_name: str,
    partition: str,
    value: object,
) -> tuple[float, float]:
    if not isinstance(value, Mapping) or "min" not in value or "max" not in value:
        raise ConfigError(
            f"scenario {scenario_name!r} partition {partition!r} requires min and max"
        )
    try:
        minimum = float(value["min"])
        maximum = float(value["max"])
    except (TypeError, ValueError) as exc:
        raise ConfigError(
            f"scenario {scenario_name!r} partition {partition!r} has nonnumeric bounds"
        ) from exc
    if not math.isfinite(minimum) or not math.isfinite(maximum) or minimum > maximum:
        raise ConfigError(f"scenario {scenario_name!r} partition {partition!r} has invalid bounds")
    return minimum, maximum


def _category_values(
    scenario_name: str,
    partition: str,
    value: object,
) -> list[str]:
    if not isinstance(value, list | tuple) or not value:
        raise ConfigError(
            f"scenario {scenario_name!r} partition {partition!r} requires category values"
        )
    result = [str(item).strip() for item in value]
    if any(not item for item in result):
        raise ConfigError(
            f"scenario {scenario_name!r} partition {partition!r} contains blank categories"
        )
    if len(set(result)) != len(result):
        raise ConfigError(
            f"scenario {scenario_name!r} partition {partition!r} contains duplicate categories"
        )
    return result


def _numeric_column(frame: pd.DataFrame, field: str, scenario_name: str) -> pd.Series:
    if field not in frame.columns:
        raise ConfigError(f"scenario {scenario_name!r} requires unavailable field {field!r}")
    try:
        series = frame[field].astype(float)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"scenario {scenario_name!r} field {field!r} is not numeric") from exc
    if not bool(series.map(math.isfinite).all()):
        raise ConfigError(f"scenario {scenario_name!r} field {field!r} contains non-finite values")
    return series


def _in_bounds(value: float, bounds: tuple[float, float]) -> bool:
    minimum, maximum = bounds
    return minimum <= value <= maximum


def _require_non_empty_partitions(name: str, partitions: dict[str, pd.DataFrame]) -> None:
    empty = [partition for partition, frame in partitions.items() if frame.empty]
    if empty:
        raise ConfigError(
            f"scenario {name!r} produced empty partitions: " + ", ".join(sorted(empty))
        )


def _hash_score(value: str) -> float:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return int(digest, 16) / float(16**64)
