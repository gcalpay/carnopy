from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import pandas as pd

from carnopy.domain.failures import CarnopyError

PlotKind = Literal["curves", "contour"]
PlotScale = Literal["linear", "log"]
PlotCoordinate = Literal["pressure", "temperature"]
SourceIntegrity = Literal["verified", "unverified"]


class VisualizationError(CarnopyError):
    """A visualization request cannot be completed safely."""


class VisualizationDependencyError(VisualizationError):
    """Optional visualization dependencies are unavailable."""


@dataclass(frozen=True)
class PlotSource:
    requested_path: Path
    dataset_path: Path
    source_format: Literal["csv", "parquet"]
    frame: pd.DataFrame
    metadata: dict[str, Any] | None
    metadata_path: Path | None
    source_sha256: str
    source_integrity: SourceIntegrity
    mode: str
    run_id: str
    spec_id: str | None
    generation_context_id: str | None
    coordinate: PlotCoordinate
    coordinate_column: str
    coordinate_si_unit: str
    coordinate_display_unit: str


@dataclass(frozen=True)
class PlotResult:
    figure: Any
    image_path: Path
    sidecar_path: Path
    selected_fluids: tuple[str, ...]
    property_name: str
    kind: PlotKind
    scale: PlotScale
    valid_rows_plotted: int
    invalid_rows_excluded: int
    source_integrity: SourceIntegrity
