from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import yaml

from carnopy.backends.coolprop import CoolPropBackend
from carnopy.backends.coolprop_models import unsupported_properties
from carnopy.config.io import LoadedConfig, LoadedSweepConfig
from carnopy.config.models import BackendConfig, CarnopyConfig, NormalizedConfig
from carnopy.config.normalize import canonical_json_bytes, normalize_config
from carnopy.domain.failures import ConfigError


@dataclass(frozen=True)
class NormalizedSweep:
    normalized_bytes: bytes
    normalized: dict[str, Any]
    child_configs: dict[str, LoadedConfig]
    child_normalized: dict[str, NormalizedConfig]


def normalize_sweep_config(loaded: LoadedSweepConfig) -> NormalizedSweep:
    sweep = loaded.model
    known_unsupported = {
        model: unsupported_properties(model, sweep.properties) for model in sweep.backend.models
    }
    unsupported = {
        model: properties for model, properties in known_unsupported.items() if properties
    }
    if unsupported:
        details = "; ".join(
            f"{model}: {', '.join(properties)}" for model, properties in unsupported.items()
        )
        raise ConfigError(f"selected models do not support requested properties: {details}")

    child_configs: dict[str, LoadedConfig] = {}
    child_normalized: dict[str, NormalizedConfig] = {}
    for model in sweep.backend.models:
        child_payload: dict[str, Any] = {
            "schema_version": 2,
            "document_type": "dataset",
            "backend": {"name": sweep.backend.name, "model": model},
            "mode": sweep.mode,
            "fluids": sweep.fluids,
            "grid": {axis: sampler.model_dump(mode="json") for axis, sampler in sweep.grid.items()},
            "properties": sweep.properties,
            "outputs": sweep.outputs.model_dump(mode="json"),
        }
        raw_bytes = yaml.safe_dump(
            child_payload,
            sort_keys=True,
            allow_unicode=True,
        ).encode("utf-8")
        child = LoadedConfig(
            path=loaded.path,
            raw_bytes=raw_bytes,
            model=CarnopyConfig(
                schema_version=2,
                document_type="dataset",
                backend=BackendConfig(name=sweep.backend.name, model=model),
                mode=sweep.mode,
                fluids=list(sweep.fluids),
                grid=sweep.grid,
                properties=list(sweep.properties),
                outputs=sweep.outputs,
            ),
        )
        backend = CoolPropBackend(model=model)
        child_configs[model] = child
        child_normalized[model] = normalize_config(child.model, backend)

    reference = child_normalized[sweep.backend.reference_model]
    normalized: dict[str, Any] = {
        "schema_version": 2,
        "document_type": "model_sweep",
        "backend": {
            "name": sweep.backend.name,
            "models": list(sweep.backend.models),
            "reference_model": sweep.backend.reference_model,
        },
        "mode": sweep.mode,
        "fluids": reference.fluids,
        "grid": {
            axis: {"unit": reference.grid_units[axis], "values": values}
            for axis, values in sorted(reference.grid.items())
        },
        "properties": reference.properties,
        "outputs": {"dataset_formats": list(sweep.outputs.dataset_formats)},
        "comparison_plots": (
            None
            if sweep.comparison_plots is None
            else sweep.comparison_plots.model_dump(mode="json")
        ),
    }
    return NormalizedSweep(
        normalized_bytes=canonical_json_bytes(normalized),
        normalized=normalized,
        child_configs=child_configs,
        child_normalized=child_normalized,
    )
