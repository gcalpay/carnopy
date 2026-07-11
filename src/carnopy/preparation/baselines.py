from __future__ import annotations

import importlib.metadata
import math
from typing import Any, cast

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from carnopy.domain.failures import ConfigError
from carnopy.preparation.models import BaselineDiagnosticsConfig, BaselineModel


def build_baseline_diagnostics(
    partitions: dict[str, pd.DataFrame],
    *,
    feature_columns: list[str],
    target_columns: list[str],
    config: BaselineDiagnosticsConfig,
    scenario: str,
) -> dict[str, Any]:
    if "train" not in partitions:
        return {
            "scenario": scenario,
            "status": "skipped_missing_train_partition",
            "feature_columns": feature_columns,
            "target_columns": target_columns,
        }
    evaluation_partitions = [
        partition for partition in ("validation", "test") if partition in partitions
    ]
    if not evaluation_partitions:
        return {
            "scenario": scenario,
            "status": "skipped_missing_evaluation_partition",
            "feature_columns": feature_columns,
            "target_columns": target_columns,
        }
    sklearn_version = _require_sklearn()
    train = partitions["train"]
    train_features = _matrix(train, feature_columns, role="feature")
    train_targets = _matrix(train, target_columns, role="target")
    evaluations = {
        partition: (
            _matrix(partitions[partition], feature_columns, role="feature"),
            _matrix(partitions[partition], target_columns, role="target"),
        )
        for partition in evaluation_partitions
    }
    models: list[dict[str, Any]] = []
    for model_name in config.models:
        for target_index, target_column in enumerate(target_columns):
            models.append(
                _fit_target_baseline(
                    model_name,
                    target_column=target_column,
                    train_features=train_features,
                    train_target=train_targets[:, target_index],
                    evaluations={
                        partition: (features, targets[:, target_index])
                        for partition, (features, targets) in evaluations.items()
                    },
                    config=config,
                )
            )
    return {
        "scenario": scenario,
        "status": (
            "completed"
            if all(model.get("status") == "completed" for model in models)
            else "completed_with_failures"
        ),
        "library": "scikit-learn",
        "library_version": sklearn_version,
        "feature_columns": feature_columns,
        "target_columns": target_columns,
        "train_row_count": len(train),
        "evaluation_row_counts": {
            partition: len(partitions[partition]) for partition in evaluation_partitions
        },
        "models": models,
        "policy": (
            "diagnostic metrics only; estimators are fitted on train and are not persisted, "
            "registered, tuned, or used to change prepared rows"
        ),
    }


def _fit_target_baseline(
    model_name: BaselineModel,
    *,
    target_column: str,
    train_features: np.ndarray,
    train_target: np.ndarray,
    evaluations: dict[str, tuple[np.ndarray, np.ndarray]],
    config: BaselineDiagnosticsConfig,
) -> dict[str, Any]:
    try:
        estimator = _estimator(model_name, config)
        estimator.fit(train_features, train_target)
        metrics = {
            partition: _regression_metrics(target, estimator.predict(features))
            for partition, (features, target) in evaluations.items()
        }
    except Exception as exc:  # diagnostic failures must not discard prepared data
        return {
            "model": model_name,
            "target": target_column,
            "status": "failed",
            "error_type": type(exc).__name__,
            "message": str(exc),
        }
    return {
        "model": model_name,
        "target": target_column,
        "status": "completed",
        "metrics": metrics,
    }


def _estimator(model_name: BaselineModel, config: BaselineDiagnosticsConfig) -> Any:
    from sklearn.dummy import DummyRegressor
    from sklearn.ensemble import HistGradientBoostingRegressor
    from sklearn.linear_model import Ridge
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    if model_name == "dummy_mean":
        return DummyRegressor(strategy="mean")
    if model_name == "ridge":
        return make_pipeline(StandardScaler(), Ridge(alpha=config.ridge_alpha))
    return HistGradientBoostingRegressor(
        max_iter=config.histogram_max_iterations,
        random_state=config.random_seed,
    )


def _regression_metrics(actual: np.ndarray, predicted: np.ndarray) -> dict[str, Any]:
    residual = predicted - actual
    mean_absolute_error = float(np.mean(np.abs(residual)))
    root_mean_squared_error = float(math.sqrt(float(np.mean(np.square(residual)))))
    denominator = float(np.sum(np.square(actual - actual.mean())))
    r_squared = (
        None if denominator == 0.0 else 1.0 - float(np.sum(np.square(residual))) / denominator
    )
    return {
        "mean_absolute_error": mean_absolute_error,
        "root_mean_squared_error": root_mean_squared_error,
        "r_squared": r_squared,
        "actual_minimum": float(actual.min()),
        "actual_maximum": float(actual.max()),
        "prediction_minimum": float(predicted.min()),
        "prediction_maximum": float(predicted.max()),
    }


def _matrix(
    frame: pd.DataFrame,
    columns: list[str],
    *,
    role: str,
) -> NDArray[np.float64]:
    missing = [column for column in columns if column not in frame]
    if missing:
        raise ConfigError(
            f"baseline diagnostic {role} columns are unavailable: {', '.join(missing)}"
        )
    try:
        matrix = frame.loc[:, columns].astype("float64").to_numpy(copy=True)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"baseline diagnostic {role} columns must be numeric") from exc
    if not bool(np.isfinite(matrix).all()):
        raise ConfigError(f"baseline diagnostic {role} columns contain non-finite values")
    return cast(NDArray[np.float64], matrix)


def _require_sklearn() -> str:
    try:
        return importlib.metadata.version("scikit-learn")
    except importlib.metadata.PackageNotFoundError as exc:
        raise ConfigError(
            "baseline diagnostics require the optional analysis extra; install carnopy[analysis]"
        ) from exc
