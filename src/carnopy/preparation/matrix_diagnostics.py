from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from carnopy.preparation.models import MatrixDiagnosticsConfig


def build_matrix_diagnostics(
    frame: pd.DataFrame,
    *,
    feature_columns: list[str],
    target_columns: list[str],
    config: MatrixDiagnosticsConfig,
    scenario: str | None,
    fit_partition: str,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "scenario": scenario,
        "fit_partition": fit_partition,
        "row_count": len(frame),
        "feature_columns": feature_columns,
        "target_columns": target_columns,
        "correlation_threshold": config.correlation_threshold,
        "near_constant_relative_spread_threshold": config.near_constant_relative_spread,
        "standardization": "population mean and std fitted on the stated partition",
    }
    if frame.empty:
        return {**result, "status": "skipped_empty_fit_partition"}
    unavailable = [column for column in [*feature_columns, *target_columns] if column not in frame]
    if unavailable:
        return {
            **result,
            "status": "skipped_missing_columns",
            "missing_columns": unavailable,
        }
    try:
        features = frame.loc[:, feature_columns].astype("float64").to_numpy(copy=True)
        targets = frame.loc[:, target_columns].astype("float64").to_numpy(copy=True)
    except (TypeError, ValueError):
        return {**result, "status": "skipped_nonnumeric_columns"}
    if not bool(np.isfinite(features).all()) or not bool(np.isfinite(targets).all()):
        return {**result, "status": "skipped_nonfinite_values"}

    minima = features.min(axis=0)
    maxima = features.max(axis=0)
    spreads = maxima - minima
    scales = np.maximum(np.maximum(np.abs(minima), np.abs(maxima)), np.finfo(float).tiny)
    relative_spreads = spreads / scales
    constant_mask = spreads == 0.0
    near_constant_mask = (~constant_mask) & (
        relative_spreads <= config.near_constant_relative_spread
    )
    constant_columns = [
        column
        for column, is_constant in zip(feature_columns, constant_mask, strict=True)
        if is_constant
    ]
    near_constant_columns = [
        {
            "field": column,
            "relative_spread": float(relative_spread),
        }
        for column, relative_spread, is_near_constant in zip(
            feature_columns,
            relative_spreads,
            near_constant_mask,
            strict=True,
        )
        if is_near_constant
    ]
    variable_columns = [
        column
        for column, is_constant in zip(feature_columns, constant_mask, strict=True)
        if not is_constant
    ]
    result.update(
        {
            "constant_feature_columns": constant_columns,
            "near_constant_feature_columns": near_constant_columns,
            "variable_feature_columns": variable_columns,
        }
    )
    if not variable_columns:
        return {**result, "status": "skipped_no_variable_features"}

    variable = features[:, ~constant_mask]
    means = variable.mean(axis=0)
    stds = variable.std(axis=0, ddof=0)
    standardized = (variable - means) / stds
    singular_values = np.linalg.svd(standardized, full_matrices=False, compute_uv=False)
    largest = float(singular_values[0]) if singular_values.size else 0.0
    tolerance = max(standardized.shape) * np.finfo(float).eps * largest
    rank = int(np.sum(singular_values > tolerance))
    feature_rank_deficient = rank < len(variable_columns)
    condition_number = (
        None
        if feature_rank_deficient or singular_values.size == 0 or singular_values[-1] == 0.0
        else float(singular_values[0] / singular_values[-1])
    )
    squared = np.square(singular_values)
    explained = squared / squared.sum() if squared.sum() > 0.0 else np.zeros_like(squared)
    positive = explained[explained > 0.0]
    effective_rank = float(math.exp(float(-(positive * np.log(positive)).sum())))

    result.update(
        {
            "status": "completed",
            "singular_values": [float(value) for value in singular_values],
            "explained_variance_ratio": [float(value) for value in explained],
            "numerical_rank": rank,
            "rank_tolerance": float(tolerance),
            "rank_tolerance_definition": (
                "max(rows, columns) * float64 epsilon * largest singular value"
            ),
            "feature_rank_fraction": rank / len(variable_columns),
            "effective_rank": effective_rank,
            "effective_rank_fraction": effective_rank / len(variable_columns),
            "condition_number": condition_number,
            "condition_number_is_infinite": feature_rank_deficient,
            "highly_correlated_feature_pairs": _feature_correlations(
                standardized,
                variable_columns,
                threshold=config.correlation_threshold,
            ),
            "constant_target_columns": [
                column
                for column, std in zip(target_columns, targets.std(axis=0, ddof=0), strict=True)
                if std == 0.0
            ],
            "feature_target_correlations": _target_correlations(
                standardized,
                variable_columns,
                targets,
                target_columns,
            ),
        }
    )
    return result


def _feature_correlations(
    standardized: np.ndarray,
    columns: list[str],
    *,
    threshold: float,
) -> list[dict[str, Any]]:
    if len(columns) < 2:
        return []
    correlation = np.corrcoef(standardized, rowvar=False)
    pairs = [
        {
            "left": columns[left],
            "right": columns[right],
            "correlation": float(correlation[left, right]),
        }
        for left in range(len(columns))
        for right in range(left + 1, len(columns))
        if abs(float(correlation[left, right])) >= threshold
    ]
    return sorted(pairs, key=lambda item: (-abs(item["correlation"]), item["left"], item["right"]))


def _target_correlations(
    standardized_features: np.ndarray,
    feature_columns: list[str],
    targets: np.ndarray,
    target_columns: list[str],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for target_index, target_column in enumerate(target_columns):
        target = targets[:, target_index]
        target_std = float(target.std(ddof=0))
        if target_std == 0.0:
            continue
        standardized_target = (target - target.mean()) / target_std
        for feature_index, feature_column in enumerate(feature_columns):
            correlation = float(
                np.mean(standardized_features[:, feature_index] * standardized_target)
            )
            result.append(
                {
                    "feature": feature_column,
                    "target": target_column,
                    "correlation": correlation,
                }
            )
    return sorted(
        result,
        key=lambda item: (-abs(item["correlation"]), item["feature"], item["target"]),
    )
