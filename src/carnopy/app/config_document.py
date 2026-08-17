from __future__ import annotations

import copy
import hashlib
import os
import stat
import tempfile
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, cast

import yaml

GRID_AXIS_ORDER = ("temperature", "pressure", "vapor_mass_fraction")
SAMPLER_FIELD_ORDER: dict[str, tuple[str, ...]] = {
    "explicit": ("kind", "values", "unit"),
    "linspace": ("kind", "start", "stop", "num", "unit"),
    "stepspace": ("kind", "start", "stop", "step", "unit"),
    "geomspace": ("kind", "start", "stop", "num", "unit"),
    "logspace": ("kind", "start_exp", "stop_exp", "num", "base", "unit"),
}
PLOT_FIELD_ORDER = (
    "name",
    "kind",
    "property",
    "x",
    "y",
    "group_by",
    "filters",
    "series",
    "display_units",
    "fluids",
    "value_scale",
    "color_scale",
    "x_scale",
    "y_scale",
    "format",
)
DEFAULT_PLOT_VALUES: dict[str, object] = {
    "value_scale": "linear",
    "color_scale": "linear",
    "x_scale": "linear",
    "y_scale": "linear",
}
DocumentType = Literal["dataset", "model_sweep", "preparation"]

SWEEP_PLOT_FIELD_ORDER = (
    "name",
    "kind",
    "fluid",
    "property",
    "x",
    "group_by",
    "filters",
    "models",
    "delta_metric",
    "value_scale",
    "format",
)
SCENARIO_FIELD_ORDER = (
    "name",
    "kind",
    "seed",
    "partitions",
    "field",
    "holdouts",
    "remainder",
    "strata",
    "transformations",
)


class ConfigDocumentError(ValueError):
    """A desktop configuration document cannot be read or saved safely."""


class ExternalModificationError(ConfigDocumentError):
    """A saved configuration changed after the GUI loaded it."""


@dataclass(frozen=True)
class SavedConfigSnapshot:
    """Exact saved configuration identity accepted for worker execution."""

    path: Path
    yaml_bytes: bytes
    sha256: str
    document_type: DocumentType


@dataclass
class ConfigurationDocument:
    _payload: dict[str, Any]
    source_path: Path | None = None
    source_sha256: str | None = None
    workspace_owned: bool = False
    imported: bool = False
    _baseline_yaml: bytes = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._payload = copy.deepcopy(self._payload)
        self._baseline_yaml = serialize_configuration(self._payload)

    @property
    def document_type(self) -> DocumentType:
        return document_type_from_payload(self._payload)

    @property
    def payload(self) -> dict[str, Any]:
        return copy.deepcopy(self._payload)

    @property
    def yaml_bytes(self) -> bytes:
        return serialize_configuration(self._payload)

    @property
    def yaml_text(self) -> str:
        return self.yaml_bytes.decode("utf-8")

    @property
    def dirty(self) -> bool:
        return self.yaml_bytes != self._baseline_yaml

    @property
    def needs_save(self) -> bool:
        return self.source_path is None or self.dirty

    def set_payload(self, payload: dict[str, Any]) -> None:
        self._payload = copy.deepcopy(payload)

    def mark_saved(self, path: Path, content: bytes) -> None:
        self.source_path = path.resolve()
        self.source_sha256 = sha256_bytes(content)
        self.workspace_owned = True
        self.imported = False
        self._baseline_yaml = content

    def execution_snapshot(self, *, configs_root: Path) -> SavedConfigSnapshot:
        path = self.source_path
        digest = self.source_sha256
        if path is None or digest is None:
            raise ConfigDocumentError("save the configuration before execution")
        if not self.workspace_owned or not is_path_within(path, configs_root):
            raise ConfigDocumentError(
                "external configurations must be saved under the workspace configs folder"
            )
        if self.dirty:
            raise ConfigDocumentError("save the current configuration changes before execution")
        try:
            content = path.read_bytes()
        except OSError as exc:
            raise ConfigDocumentError(f"saved configuration is not readable: {path}") from exc
        if sha256_bytes(content) != digest:
            raise ExternalModificationError(f"saved configuration changed outside Carnopy: {path}")
        if content != self._baseline_yaml:
            raise ExternalModificationError(
                f"saved configuration bytes no longer match the open document: {path}"
            )
        return SavedConfigSnapshot(
            path=path,
            yaml_bytes=content,
            sha256=digest,
            document_type=self.document_type,
        )


def document_type_from_payload(payload: dict[str, Any]) -> DocumentType:
    value = payload.get("document_type")
    if value not in {"dataset", "model_sweep", "preparation"}:
        raise ConfigDocumentError(
            "configuration document_type must be dataset, model_sweep, or preparation"
        )
    return cast(DocumentType, value)


def serialize_configuration(payload: dict[str, Any]) -> bytes:
    document_type = document_type_from_payload(payload)
    if document_type == "dataset":
        return serialize_dataset_config(payload)
    if document_type == "model_sweep":
        return serialize_sweep_config(payload)
    return serialize_preparation_config(payload)


def serialize_dataset_config(payload: dict[str, Any]) -> bytes:
    ordered: dict[str, Any] = {}
    for key in ("schema_version", "document_type"):
        if key in payload:
            ordered[key] = copy.deepcopy(payload[key])

    backend = payload.get("backend")
    if isinstance(backend, dict):
        ordered["backend"] = _ordered_mapping(backend, ("name", "model"))
    if "mode" in payload:
        ordered["mode"] = payload["mode"]
    if "fluids" in payload:
        ordered["fluids"] = copy.deepcopy(payload["fluids"])

    grid = payload.get("grid")
    if isinstance(grid, dict):
        ordered_grid: dict[str, Any] = {}
        for axis in GRID_AXIS_ORDER:
            sampler = grid.get(axis)
            if not isinstance(sampler, dict):
                continue
            kind = sampler.get("kind")
            field_order = SAMPLER_FIELD_ORDER.get(str(kind), tuple(sampler))
            ordered_grid[axis] = _ordered_mapping(sampler, field_order)
        ordered["grid"] = ordered_grid

    if "properties" in payload:
        ordered["properties"] = copy.deepcopy(payload["properties"])

    outputs = payload.get("outputs")
    if isinstance(outputs, dict) and outputs.get("dataset_formats"):
        ordered["outputs"] = {
            "dataset_formats": [
                item for item in ("csv", "parquet") if item in outputs["dataset_formats"]
            ],
        }

    visualization = _ordered_visualization(payload.get("visualization"))
    if visualization is not None:
        ordered["visualization"] = visualization

    return _dump_yaml(ordered)


def serialize_sweep_config(payload: dict[str, Any]) -> bytes:
    """Serialize one valid model-sweep payload in deterministic public order."""

    from carnopy.config.sweep import ModelSweepConfig

    model = ModelSweepConfig.model_validate(payload)
    value = model.model_dump(mode="json", by_alias=True, exclude_none=True)
    ordered: dict[str, Any] = {
        "schema_version": value["schema_version"],
        "document_type": value["document_type"],
        "backend": _ordered_mapping(value["backend"], ("name", "models", "reference_model")),
        "mode": value["mode"],
        "fluids": copy.deepcopy(value["fluids"]),
        "grid": _ordered_grid(cast(dict[str, Any], value["grid"])),
        "properties": copy.deepcopy(value["properties"]),
        "outputs": _ordered_mapping(value["outputs"], ("dataset_formats",)),
    }
    comparisons = value.get("comparison_plots")
    if isinstance(comparisons, dict):
        plots = comparisons.get("plots")
        ordered_comparisons: dict[str, Any] = {}
        if comparisons.get("format") not in (None, "png"):
            ordered_comparisons["format"] = comparisons["format"]
        if isinstance(plots, list):
            ordered_comparisons["plots"] = [
                _ordered_mapping(plot, SWEEP_PLOT_FIELD_ORDER)
                for plot in plots
                if isinstance(plot, dict)
            ]
        if ordered_comparisons:
            ordered["comparison_plots"] = ordered_comparisons
    return _dump_yaml(ordered)


def serialize_preparation_config(payload: dict[str, Any]) -> bytes:
    """Serialize one valid preparation payload in deterministic public order."""

    from carnopy.preparation.models import PreparationConfig

    model = PreparationConfig.model_validate(payload)
    value = model.model_dump(mode="json", by_alias=True, exclude_none=True)
    features = cast(dict[str, Any], value["features"])
    ordered: dict[str, Any] = {
        "schema_version": value["schema_version"],
        "document_type": value["document_type"],
        "source_policy": _ordered_mapping(
            cast(dict[str, Any], value["source_policy"]),
            ("allow_partial_sweep",),
        ),
        "features": _ordered_mapping(features, ("numeric", "derived")),
        "categorical_features": [
            _ordered_mapping(item, ("field", "encoding", "categories"))
            for item in cast(list[dict[str, Any]], value["categorical_features"])
        ],
        "targets": copy.deepcopy(value["targets"]),
        "auxiliary": copy.deepcopy(value["auxiliary"]),
    }
    scenarios = cast(list[dict[str, Any]], value["scenarios"])
    if scenarios:
        ordered["scenarios"] = [_ordered_scenario(item) for item in scenarios]
    quality = cast(dict[str, Any], value["quality"])
    ordered_quality: dict[str, Any] = {}
    matrix = quality.get("matrix_diagnostics")
    if isinstance(matrix, dict):
        ordered_quality["matrix_diagnostics"] = _ordered_mapping(
            matrix,
            ("correlation_threshold", "near_constant_relative_spread"),
        )
    baseline = quality.get("baseline_diagnostics")
    if isinstance(baseline, dict):
        ordered_quality["baseline_diagnostics"] = _ordered_mapping(
            baseline,
            ("models", "random_seed", "ridge_alpha", "histogram_max_iterations"),
        )
    if ordered_quality:
        ordered["quality"] = ordered_quality
    outputs = cast(dict[str, Any], value["outputs"])
    ordered_outputs = _ordered_mapping(outputs, ("formats", "parquet"))
    arrays = outputs.get("arrays")
    if isinstance(arrays, dict):
        ordered_outputs["arrays"] = _ordered_mapping(
            arrays,
            ("formats", "dtype", "include_auxiliary"),
        )
    ordered["outputs"] = ordered_outputs
    return _dump_yaml(ordered)


def document_from_worker_payload(
    worker_payload: dict[str, Any],
    *,
    configs_root: Path,
) -> ConfigurationDocument:
    config = worker_payload.get("config")
    source_name = worker_payload.get("source_name")
    source_sha256 = worker_payload.get("source_sha256")
    if not isinstance(config, dict):
        raise ConfigDocumentError("worker response does not contain a configuration")
    if not isinstance(source_name, str) or not isinstance(source_sha256, str):
        raise ConfigDocumentError("worker response does not contain source identity")
    source_path = Path(source_name).expanduser().resolve()
    response_type = worker_payload.get("document_type", config.get("document_type"))
    if response_type != config.get("document_type"):
        raise ConfigDocumentError("worker response document type is inconsistent")
    document_type_from_payload(config)
    return ConfigurationDocument(
        config,
        source_path=source_path,
        source_sha256=source_sha256,
        workspace_owned=is_path_within(source_path, configs_root),
        imported=True,
    )


def new_document(payload: dict[str, Any]) -> ConfigurationDocument:
    return ConfigurationDocument(payload)


def write_new_config(path: Path, content: bytes, *, configs_root: Path) -> Path:
    destination = validate_config_destination(path, configs_root=configs_root)
    created = False
    try:
        with destination.open("xb") as stream:
            created = True
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as exc:
        raise ConfigDocumentError(f"refusing to overwrite existing file: {destination}") from exc
    except OSError as exc:
        if created:
            with suppress(OSError):
                destination.unlink(missing_ok=True)
        raise ConfigDocumentError(f"could not save configuration {destination}: {exc}") from exc
    return destination


def replace_config_atomic(
    path: Path,
    content: bytes,
    *,
    expected_sha256: str,
    configs_root: Path,
) -> Path:
    destination = validate_config_destination(
        path,
        configs_root=configs_root,
        require_absent=False,
    )
    try:
        current = destination.read_bytes()
        current_mode = stat.S_IMODE(destination.stat().st_mode)
    except OSError as exc:
        raise ExternalModificationError(
            f"saved configuration is no longer readable: {destination}"
        ) from exc
    if sha256_bytes(current) != expected_sha256:
        raise ExternalModificationError(
            f"saved configuration changed outside Carnopy: {destination}"
        )

    temporary_path: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
        )
        temporary_path = Path(temporary_name)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        temporary_path.chmod(current_mode)
        if not source_matches(destination, expected_sha256):
            raise ExternalModificationError(
                f"saved configuration changed outside Carnopy: {destination}"
            )
        os.replace(temporary_path, destination)
    except ExternalModificationError:
        if temporary_path is not None:
            with suppress(OSError):
                temporary_path.unlink(missing_ok=True)
        raise
    except OSError as exc:
        if temporary_path is not None:
            with suppress(OSError):
                temporary_path.unlink(missing_ok=True)
        raise ConfigDocumentError(f"could not save configuration {destination}: {exc}") from exc
    return destination


def validate_config_destination(
    path: Path,
    *,
    configs_root: Path,
    require_absent: bool = True,
) -> Path:
    destination = path.expanduser().resolve()
    root = configs_root.expanduser().resolve()
    if destination.suffix.lower() not in {".yaml", ".yml"}:
        raise ConfigDocumentError("configuration filename must end in .yaml or .yml")
    if not is_path_within(destination, root):
        raise ConfigDocumentError(f"configuration must be saved under {root}")
    if not destination.parent.is_dir():
        raise ConfigDocumentError(
            f"configuration parent directory does not exist: {destination.parent}"
        )
    if require_absent and destination.exists():
        raise ConfigDocumentError(f"refusing to overwrite existing file: {destination}")
    if not require_absent and not destination.is_file():
        raise ConfigDocumentError(f"saved configuration is missing: {destination}")
    return destination


def is_path_within(path: Path, root: Path) -> bool:
    try:
        path.expanduser().resolve().relative_to(root.expanduser().resolve())
    except ValueError:
        return False
    return True


def source_matches(path: Path, expected_sha256: str) -> bool:
    try:
        return sha256_bytes(path.read_bytes()) == expected_sha256
    except OSError:
        return False


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _ordered_visualization(value: object) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    ordered: dict[str, Any] = {}
    if value.get("format") not in (None, "png"):
        ordered["format"] = value["format"]
    for key in ("fluids", "filters", "display_units"):
        item = value.get(key)
        if item:
            ordered[key] = _ordered_value(item)
    plots = value.get("plots")
    if isinstance(plots, (list, tuple)) and plots:
        ordered["plots"] = [_ordered_plot(plot) for plot in plots if isinstance(plot, dict)]
    return ordered or None


def _ordered_grid(value: dict[str, Any]) -> dict[str, Any]:
    ordered: dict[str, Any] = {}
    for axis in GRID_AXIS_ORDER:
        sampler = value.get(axis)
        if not isinstance(sampler, dict):
            continue
        field_order = SAMPLER_FIELD_ORDER.get(str(sampler.get("kind")), tuple(sampler))
        ordered[axis] = _ordered_mapping(sampler, field_order)
    return ordered


def _ordered_scenario(value: dict[str, Any]) -> dict[str, Any]:
    ordered = _ordered_mapping(value, SCENARIO_FIELD_ORDER)
    strata = ordered.get("strata")
    if isinstance(strata, dict):
        ordered["strata"] = _ordered_mapping(strata, ("categorical", "numeric_bins"))
    transformations = ordered.get("transformations")
    if isinstance(transformations, list):
        ordered["transformations"] = [
            _ordered_mapping(item, ("field", "methods"))
            for item in transformations
            if isinstance(item, dict)
        ]
    return ordered


def _dump_yaml(value: dict[str, Any]) -> bytes:
    text = cast(
        str,
        yaml.safe_dump(
            value,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
            width=100,
        ),
    )
    return text.encode("utf-8")


def _ordered_plot(plot: dict[str, Any]) -> dict[str, Any]:
    ordered: dict[str, Any] = {}
    for key in PLOT_FIELD_ORDER:
        value = plot.get(key)
        if value is None or value == () or value == [] or value == {}:
            continue
        if key in DEFAULT_PLOT_VALUES and value == DEFAULT_PLOT_VALUES[key]:
            continue
        ordered[key] = _ordered_value(value)
    return ordered


def _ordered_mapping(value: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    return {key: _ordered_value(value[key]) for key in keys if key in value}


def _ordered_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _ordered_value(value[key]) for key in sorted(value)}
    if isinstance(value, tuple):
        return [_ordered_value(item) for item in value]
    if isinstance(value, list):
        return [_ordered_value(item) for item in value]
    return copy.deepcopy(value)
