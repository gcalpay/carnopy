from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from carnopy.config.visualization import VisualizationConfig
from carnopy.visualization.models import VisualizationError


def load_visualization_config(path: str | Path) -> VisualizationConfig:
    config_path = Path(path)
    try:
        payload: Any = yaml.safe_load(config_path.read_bytes())
    except (OSError, yaml.YAMLError) as exc:
        raise VisualizationError(
            f"could not read visualization config {config_path}: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise VisualizationError("visualization configuration root must be a YAML mapping")
    visualization = payload.get("visualization")
    if visualization is None:
        raise VisualizationError("configuration does not contain a visualization section")
    try:
        return VisualizationConfig.model_validate(visualization)
    except ValidationError as exc:
        raise VisualizationError(f"invalid visualization configuration: {exc}") from exc
