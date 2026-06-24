from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from carnopy.domain.failures import OutputError
from carnopy.preparation.fields import sanitize_category
from carnopy.preparation.models import PreparationArrayOutputsConfig
from carnopy.provenance import sha256_file


@dataclass(frozen=True)
class ArrayExportResult:
    artifact_names: list[str]
    manifest: dict[str, Any]


def write_array_exports(
    *,
    frame: pd.DataFrame,
    output_directory: Path,
    source_table_path: Path,
    artifact_prefix: str,
    file_prefix: str,
    config: PreparationArrayOutputsConfig | None,
    feature_columns: list[str],
    target_columns: list[str],
    auxiliary_columns: list[str],
    units: dict[str, str | None],
) -> ArrayExportResult:
    if config is None or frame.empty:
        return ArrayExportResult(artifact_names=[], manifest={"enabled": False, "exports": []})
    dtype = config.dtype
    if dtype is None:
        raise OutputError("array output dtype is required when arrays are requested")

    arrays_directory = output_directory / "arrays"
    arrays_directory.mkdir(exist_ok=True)
    feature_matrix = _numeric_matrix(frame, feature_columns, dtype, role="features")
    target_matrix = _numeric_matrix(frame, target_columns, dtype, role="targets")
    auxiliary = _auxiliary_arrays(
        frame,
        auxiliary_columns=auxiliary_columns,
        dtype=dtype,
        include=config.include_auxiliary,
    )

    artifact_names: list[str] = []
    exports: list[dict[str, Any]] = []

    def record(path: Path, *, fmt: str, arrays: dict[str, np.ndarray]) -> None:
        artifact_name = f"{artifact_prefix}/arrays/{path.name}"
        artifact_names.append(artifact_name)
        exports.append(
            {
                "path": artifact_name,
                "format": fmt,
                "dtype": dtype,
                "arrays": {
                    name: {
                        "shape": list(array.shape),
                        "dtype": str(array.dtype),
                    }
                    for name, array in arrays.items()
                },
                "sha256": sha256_file(path),
            }
        )

    if "npy" in config.formats:
        feature_path = arrays_directory / f"{file_prefix}features.{dtype}.npy"
        target_path = arrays_directory / f"{file_prefix}targets.{dtype}.npy"
        _save_npy(feature_path, feature_matrix)
        _save_npy(target_path, target_matrix)
        record(feature_path, fmt="npy", arrays={"features": feature_matrix})
        record(target_path, fmt="npy", arrays={"targets": target_matrix})
        for auxiliary_name, auxiliary_array in auxiliary.arrays.items():
            suffix = str(auxiliary_array.dtype)
            auxiliary_path = arrays_directory / f"{file_prefix}{auxiliary_name}.{suffix}.npy"
            _save_npy(auxiliary_path, auxiliary_array)
            record(auxiliary_path, fmt="npy", arrays={auxiliary_name: auxiliary_array})

    container_arrays = {
        "features": feature_matrix,
        "targets": target_matrix,
        **auxiliary.arrays,
    }
    if "npz" in config.formats:
        npz_path = arrays_directory / f"{file_prefix}dataset.{dtype}.npz"
        _save_npz(npz_path, container_arrays)
        record(npz_path, fmt="npz", arrays=container_arrays)
    if "safetensors" in config.formats:
        safetensors_path = arrays_directory / f"{file_prefix}dataset.{dtype}.safetensors"
        _save_safetensors(safetensors_path, container_arrays)
        record(safetensors_path, fmt="safetensors", arrays=container_arrays)

    manifest: dict[str, Any] = {
        "enabled": True,
        "dtype": dtype,
        "formats": list(config.formats),
        "include_auxiliary": config.include_auxiliary,
        "source_table": source_table_path.name,
        "source_table_sha256": sha256_file(source_table_path),
        "feature_columns": feature_columns,
        "target_columns": target_columns,
        "auxiliary_columns": auxiliary_columns if config.include_auxiliary else [],
        "units": {column: units.get(column) for column in [*feature_columns, *target_columns]},
        "categorical_auxiliary": auxiliary.categorical_manifest,
        "float_conversion": {
            "features": _conversion_errors(frame, feature_columns, dtype),
            "targets": _conversion_errors(frame, target_columns, dtype),
        },
        "exports": exports,
    }
    if auxiliary.numeric_columns:
        manifest["float_conversion"]["auxiliary_numeric"] = _conversion_errors(
            frame,
            auxiliary.numeric_columns,
            dtype,
        )
    return ArrayExportResult(artifact_names=artifact_names, manifest=manifest)


@dataclass(frozen=True)
class AuxiliaryArrays:
    arrays: dict[str, np.ndarray]
    numeric_columns: list[str]
    categorical_manifest: dict[str, dict[str, Any]]


def _auxiliary_arrays(
    frame: pd.DataFrame,
    *,
    auxiliary_columns: list[str],
    dtype: str,
    include: bool,
) -> AuxiliaryArrays:
    if not include:
        return AuxiliaryArrays(arrays={}, numeric_columns=[], categorical_manifest={})

    numeric_columns: list[str] = []
    categorical_columns: list[str] = []
    unsupported: list[str] = []
    for column in auxiliary_columns:
        if column not in frame.columns:
            raise OutputError(f"auxiliary array column {column!r} is not present")
        if pd.api.types.is_numeric_dtype(frame[column]) or pd.api.types.is_bool_dtype(
            frame[column]
        ):
            numeric_columns.append(column)
        elif column in {"fluid", "phase", "saturation_endpoint", "backend_model"}:
            categorical_columns.append(column)
        else:
            unsupported.append(column)
    if unsupported:
        raise OutputError(
            "auxiliary array exports support only numeric columns or categorical "
            "codes for fluid, phase, saturation_endpoint, and backend_model; unsupported: "
            + ", ".join(sorted(unsupported))
        )

    arrays: dict[str, np.ndarray] = {}
    if numeric_columns:
        arrays["auxiliary_numeric"] = _numeric_matrix(
            frame,
            numeric_columns,
            dtype,
            role="auxiliary",
        )

    categorical_manifest: dict[str, dict[str, Any]] = {}
    if categorical_columns:
        code_columns: list[np.ndarray] = []
        for column in categorical_columns:
            encoded, manifest = _categorical_codes(frame[column])
            categorical_manifest[column] = {
                **manifest,
                "original_column": column,
                "output_array": "auxiliary_categorical",
            }
            code_columns.append(encoded)
        arrays["auxiliary_categorical"] = np.column_stack(code_columns).astype(np.int32)
    return AuxiliaryArrays(
        arrays=arrays,
        numeric_columns=numeric_columns,
        categorical_manifest=categorical_manifest,
    )


def _numeric_matrix(
    frame: pd.DataFrame,
    columns: list[str],
    dtype: str,
    *,
    role: str,
) -> np.ndarray:
    if not columns:
        raise OutputError(f"{role} array export requires at least one column")
    values: list[np.ndarray] = []
    for column in columns:
        if column not in frame.columns:
            raise OutputError(f"{role} array column {column!r} is not present")
        try:
            series = pd.to_numeric(frame[column], errors="raise")
        except (TypeError, ValueError) as exc:
            raise OutputError(f"{role} array column {column!r} is not numeric") from exc
        array = series.to_numpy(dtype=np.float64, copy=True)
        if not bool(np.isfinite(array).all()):
            raise OutputError(f"{role} array column {column!r} contains non-finite values")
        values.append(array)
    matrix = np.column_stack(values).astype(dtype, copy=False)
    if matrix.dtype.kind == "O":
        raise OutputError(f"{role} array export produced an object array")
    return np.ascontiguousarray(matrix)


def _categorical_codes(series: pd.Series) -> tuple[np.ndarray, dict[str, Any]]:
    labels = [str(value) for value in series if not bool(pd.isna(value))]
    vocabulary = sorted(set(labels), key=str)
    if len({sanitize_category(value) for value in vocabulary}) != len(vocabulary):
        raise OutputError(f"categorical auxiliary column {series.name!r} has code-name collisions")
    mapping = {value: index for index, value in enumerate(vocabulary)}
    missing_code = -1
    encoded = np.array(
        [
            missing_code if bool(pd.isna(value)) else mapping.get(str(value), missing_code)
            for value in series
        ],
        dtype=np.int32,
    )
    return encoded, {
        "encoding": "int_code",
        "dtype": "int32",
        "missing_code": missing_code,
        "vocabulary": vocabulary,
    }


def _conversion_errors(
    frame: pd.DataFrame,
    columns: list[str],
    dtype: str,
) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = {}
    for column in columns:
        source = pd.to_numeric(frame[column], errors="raise").to_numpy(dtype=np.float64, copy=True)
        converted = source.astype(dtype).astype(np.float64)
        absolute = np.abs(converted - source)
        finite = np.isfinite(source) & np.isfinite(converted)
        denominator = np.abs(source[finite])
        nonzero = denominator > 0.0
        relative = (
            absolute[finite][nonzero] / denominator[nonzero] if nonzero.any() else np.array([])
        )
        result[column] = {
            "max_abs_error": float(absolute[finite].max()) if finite.any() else 0.0,
            "max_rel_error": float(relative.max()) if relative.size else 0.0,
            "mean_abs_error": float(absolute[finite].mean()) if finite.any() else 0.0,
        }
    return result


def _save_npy(path: Path, array: np.ndarray) -> None:
    try:
        with path.open("wb") as stream:
            np.save(stream, array, allow_pickle=False)
    except OSError as exc:
        raise OutputError(f"could not write NumPy array {path.name}: {exc}") from exc


def _save_npz(path: Path, arrays: dict[str, np.ndarray]) -> None:
    try:
        np.savez(path, **arrays)  # type: ignore[arg-type]
    except OSError as exc:
        raise OutputError(f"could not write NumPy archive {path.name}: {exc}") from exc


def _save_safetensors(path: Path, arrays: dict[str, np.ndarray]) -> None:
    try:
        from safetensors.numpy import save_file
    except ImportError as exc:
        raise OutputError(
            "SafeTensors export requires the ml extra. Install with: "
            'python -m pip install "carnopy[ml]"'
        ) from exc
    try:
        save_file({name: np.ascontiguousarray(array) for name, array in arrays.items()}, str(path))
    except Exception as exc:
        raise OutputError(f"could not write SafeTensors file {path.name}: {exc}") from exc
