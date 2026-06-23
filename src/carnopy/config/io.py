from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from carnopy.config.models import CarnopyConfig
from carnopy.domain.failures import ConfigError


@dataclass(frozen=True)
class LoadedConfig:
    path: Path
    raw_bytes: bytes
    model: CarnopyConfig


def load_config_file(path: str | Path) -> LoadedConfig:
    config_path = Path(path)
    try:
        raw_bytes = config_path.read_bytes()
    except OSError as exc:
        raise ConfigError(f"could not read configuration {config_path}: {exc}") from exc
    try:
        payload: Any = yaml.safe_load(raw_bytes)
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML in {config_path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ConfigError("configuration root must be a YAML mapping")
    if payload.get("schema_version") == 1:
        raise ConfigError(
            "configuration schema version 1 is no longer supported. Migrate to "
            "schema_version: 2, add document_type: dataset, and replace "
            "`backend: coolprop` with `backend: {name: coolprop, model: heos}`"
        )
    try:
        model = CarnopyConfig.model_validate(payload)
    except ValidationError as exc:
        raise ConfigError(str(exc)) from exc
    return LoadedConfig(path=config_path, raw_bytes=raw_bytes, model=model)
