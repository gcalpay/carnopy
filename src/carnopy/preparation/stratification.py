from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from carnopy.domain.failures import ConfigError
from carnopy.preparation.models import PartitionName, ScenarioConfig, StratificationConfig
from carnopy.preparation.rows import SOURCE_STATE_HASH_COLUMN


@dataclass(frozen=True)
class StratifiedPartitionResult:
    partitions: dict[str, pd.DataFrame]
    summary: dict[str, Any]


def shuffle_hash_partitions(
    scenario: ScenarioConfig,
    frame: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    _validate_partition_ratios(scenario)
    labels: list[tuple[object, ...]] = [("all",)] * len(frame)
    partitions, _ = _partition_state_groups(scenario, frame, labels)
    return partitions


def stratified_hash_partitions(
    scenario: ScenarioConfig,
    frame: pd.DataFrame,
) -> StratifiedPartitionResult:
    _validate_partition_ratios(scenario)
    assert scenario.strata is not None
    labels, descriptions = _stratum_labels(scenario.name, frame, scenario.strata)
    partitions, partition_counts = _partition_state_groups(scenario, frame, labels)
    strata = [
        {
            "key": descriptions[label],
            "row_count": sum(partition_counts[label].values()),
            "partition_counts": partition_counts[label],
        }
        for label in sorted(partition_counts, key=_label_text)
    ]
    return StratifiedPartitionResult(
        partitions=partitions,
        summary={
            "categorical_fields": list(scenario.strata.categorical),
            "numeric_bins": {
                field: list(boundaries)
                for field, boundaries in scenario.strata.numeric_bins.items()
            },
            "numeric_bin_semantics": (
                "[-infinity, b0), [b0, b1), ..., [bn, +infinity); boundaries enter the upper bin"
            ),
            "stratum_count": len(strata),
            "strata": strata,
        },
    )


def _partition_state_groups(
    scenario: ScenarioConfig,
    frame: pd.DataFrame,
    stratum_labels: list[tuple[object, ...]],
) -> tuple[dict[str, pd.DataFrame], dict[tuple[object, ...], dict[str, int]]]:
    if SOURCE_STATE_HASH_COLUMN not in frame:
        raise ConfigError(f"scenario {scenario.name!r} requires {SOURCE_STATE_HASH_COLUMN}")
    if frame[SOURCE_STATE_HASH_COLUMN].isna().any():
        raise ConfigError(
            f"scenario {scenario.name!r} contains missing {SOURCE_STATE_HASH_COLUMN} values"
        )
    positions_by_stratum: dict[tuple[object, ...], list[int]] = {}
    for position, label in enumerate(stratum_labels):
        positions_by_stratum.setdefault(label, []).append(position)

    selected: dict[str, list[int]] = {str(partition): [] for partition in scenario.partitions}
    partition_counts: dict[tuple[object, ...], dict[str, int]] = {}
    for label in sorted(positions_by_stratum, key=_label_text):
        positions = positions_by_stratum[label]
        stratum = frame.iloc[positions]
        grouped = stratum.groupby(SOURCE_STATE_HASH_COLUMN, dropna=False, sort=False).indices
        if len(grouped) < len(scenario.partitions):
            raise ConfigError(
                f"scenario {scenario.name!r} stratum {_label_text(label)} has "
                f"{len(grouped)} distinct states for {len(scenario.partitions)} partitions"
            )
        scored_groups = sorted(
            (
                _hash_score(f"{scenario.name}|{scenario.seed}|{_label_text(label)}|{state_hash}"),
                str(state_hash),
                [positions[int(relative)] for relative in relative_positions],
            )
            for state_hash, relative_positions in grouped.items()
        )
        assigned = _assign_state_groups(
            scored_groups,
            scenario.partitions,
            total_rows=len(positions),
        )
        partition_counts[label] = {}
        for partition, assigned_positions in assigned.items():
            selected[partition].extend(assigned_positions)
            partition_counts[label][partition] = len(assigned_positions)
    return (
        {
            partition: frame.iloc[sorted(positions)].copy()
            for partition, positions in selected.items()
        },
        partition_counts,
    )


def _stratum_labels(
    scenario_name: str,
    frame: pd.DataFrame,
    config: StratificationConfig,
) -> tuple[list[tuple[object, ...]], dict[tuple[object, ...], dict[str, Any]]]:
    categorical_values: dict[str, list[str]] = {}
    for field in config.categorical:
        if field not in frame:
            raise ConfigError(
                f"stratified_hash scenario {scenario_name!r} requires field {field!r}"
            )
        categorical_values[field] = [
            "<missing>" if pd.isna(value) else str(value) for value in frame[field].tolist()
        ]

    numeric_values: dict[str, np.ndarray] = {}
    for field, boundaries in config.numeric_bins.items():
        if field not in frame:
            raise ConfigError(
                f"stratified_hash scenario {scenario_name!r} requires field {field!r}"
            )
        try:
            values = frame[field].astype("float64").to_numpy(copy=True)
        except (TypeError, ValueError) as exc:
            raise ConfigError(
                f"stratified_hash scenario {scenario_name!r} field {field!r} is not numeric"
            ) from exc
        if not bool(np.isfinite(values).all()):
            raise ConfigError(
                f"stratified_hash scenario {scenario_name!r} field {field!r} "
                "contains non-finite values"
            )
        indices = np.searchsorted(np.asarray(boundaries), values, side="right")
        counts = np.bincount(indices, minlength=len(boundaries) + 1)
        empty = np.flatnonzero(counts == 0).tolist()
        if empty:
            raise ConfigError(
                f"stratified_hash scenario {scenario_name!r} field {field!r} has empty "
                "declared bins: " + ", ".join(str(index) for index in empty)
            )
        numeric_values[field] = indices

    labels: list[tuple[object, ...]] = []
    descriptions: dict[tuple[object, ...], dict[str, Any]] = {}
    for position in range(len(frame)):
        categorical = tuple(categorical_values[field][position] for field in config.categorical)
        numeric = tuple(int(numeric_values[field][position]) for field in config.numeric_bins)
        label = (*categorical, *numeric)
        labels.append(label)
        descriptions.setdefault(
            label,
            {
                "categorical": {
                    field: categorical_values[field][position] for field in config.categorical
                },
                "numeric_bin_indices": {
                    field: int(numeric_values[field][position]) for field in config.numeric_bins
                },
            },
        )
    return labels, descriptions


def _assign_state_groups(
    groups: list[tuple[float, str, list[int]]],
    ratios: dict[PartitionName, float],
    *,
    total_rows: int,
) -> dict[str, list[int]]:
    partitions = [str(partition) for partition in ratios]
    order = {partition: index for index, partition in enumerate(partitions)}
    targets = {str(partition): total_rows * ratio for partition, ratio in ratios.items()}
    selected: dict[str, list[int]] = {partition: [] for partition in partitions}
    assigned_rows = dict.fromkeys(partitions, 0)
    assigned_groups = dict.fromkeys(partitions, 0)
    for position, (_, _, row_positions) in enumerate(groups):
        groups_left = len(groups) - position
        empty = [partition for partition in partitions if assigned_groups[partition] == 0]
        candidates = empty if len(empty) == groups_left else partitions
        partition = max(
            candidates,
            key=lambda name: (targets[name] - assigned_rows[name], -order[name]),
        )
        selected[partition].extend(row_positions)
        assigned_rows[partition] += len(row_positions)
        assigned_groups[partition] += 1
    return selected


def _validate_partition_ratios(scenario: ScenarioConfig) -> None:
    if not math.isclose(sum(scenario.partitions.values()), 1.0, rel_tol=1e-9, abs_tol=1e-12):
        raise ConfigError(
            f"{scenario.kind} scenario {scenario.name!r} partition ratios must sum to 1"
        )


def _hash_score(value: str) -> float:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return int(digest, 16) / float(2**256)


def _label_text(label: tuple[object, ...]) -> str:
    return json.dumps(label, separators=(",", ":"), ensure_ascii=False)
