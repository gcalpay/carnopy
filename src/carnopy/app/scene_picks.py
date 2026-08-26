from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from typing import cast

import numpy as np
import pandas as pd
from pydantic import ValidationError

from carnopy.app.scene_contracts import SceneContractError
from carnopy.app.scene_pick_contracts import (
    ResolveScenePickPayload,
    ScenePickCell,
    ScenePickColumn,
    ScenePickResult,
    ScenePickSourceKind,
)
from carnopy.app.scene_profiles import _read_table, _stable_uint64
from carnopy.app.source_inspection import revalidate_scene_binding

Checkpoint = Callable[[], None]


def resolve_scene_pick(
    payload: ResolveScenePickPayload | Mapping[str, object],
    *,
    checkpoint: Checkpoint | None = None,
) -> ScenePickResult:
    """Resolve one direct-run or sweep-child point to its exact source row."""

    try:
        request = (
            payload
            if isinstance(payload, ResolveScenePickPayload)
            else ResolveScenePickPayload.model_validate(payload)
        )
    except ValidationError as exc:
        raise SceneContractError(
            "scene_pick_stale",
            "scene pick identity is structurally invalid",
        ) from exc
    if request.binding.source_kind not in {"dataset", "model_sweep"}:
        raise SceneContractError(
            "unsupported_scene_source",
            "prepared scene picks are not available at this checkpoint",
        )

    accepted = revalidate_scene_binding(request.binding)
    _checkpoint(checkpoint)
    selected = accepted.selected_table()
    frame = _read_table(selected, checkpoint)
    if "case_id" not in frame.columns:
        raise SceneContractError(
            "scene_pick_stale",
            "scene source row identity column case_id is unavailable",
        )
    stable_ids = tuple(
        _stable_uint64(value, "scene pick case_id") for value in frame["case_id"].tolist()
    )
    stable_id_catalog = set(stable_ids)
    if len(stable_id_catalog) != len(stable_ids):
        raise SceneContractError(
            "scene_pick_stale",
            "scene source repeats a case_id and cannot resolve an exact pick",
            details={"stable_id": request.stable_id},
        )
    if request.row_position >= len(frame):
        raise SceneContractError(
            "scene_pick_stale",
            "scene source no longer contains the picked row position",
            details={
                "row_position": request.row_position,
                "source_row_count": len(frame),
            },
        )
    if request.stable_id not in stable_id_catalog:
        raise SceneContractError(
            "scene_pick_stale",
            "scene source no longer contains the picked case_id",
            details={"stable_id": request.stable_id},
        )
    observed_id = stable_ids[request.row_position]
    if observed_id != request.stable_id:
        raise SceneContractError(
            "scene_pick_stale",
            "scene source row order no longer matches the picked case_id",
            details={
                "row_position": request.row_position,
                "stable_id": request.stable_id,
                "observed_stable_id": observed_id,
            },
        )

    columns = tuple(
        ScenePickColumn(name=str(name), dtype=str(frame[name].dtype)) for name in frame.columns
    )
    cells = tuple(
        _pick_cell(frame[name].iloc[request.row_position], str(name)) for name in frame.columns
    )
    _checkpoint(checkpoint)
    if revalidate_scene_binding(accepted) != accepted:  # pragma: no cover - exact comparison
        raise SceneContractError(
            "scene_source_changed",
            "scene source changed while its picked row was being resolved",
        )
    return ScenePickResult(
        source_path=accepted.source_path,
        source_kind=cast(ScenePickSourceKind, accepted.source_kind),
        inspection_revision=accepted.inspection_revision,
        table_id=accepted.selected_table_id,
        table_sha256=selected.artifact.sha256,
        row_position=request.row_position,
        stable_id=request.stable_id,
        columns=columns,
        cells=cells,
    )


def _pick_cell(value: object, column: str) -> ScenePickCell:
    if value is None or value is pd.NA or value is pd.NaT:
        return ScenePickCell(kind="null")
    if isinstance(value, (bool, np.bool_)):
        return ScenePickCell(kind="boolean", value=bool(value))
    if isinstance(value, (int, np.integer)):
        return ScenePickCell(kind="integer", value=int(value))
    if isinstance(value, (float, np.floating)):
        numeric = float(value)
        if math.isnan(numeric):
            return ScenePickCell(kind="null")
        if math.isinf(numeric):
            token = "positive_infinity" if numeric > 0.0 else "negative_infinity"
            return ScenePickCell(kind="nonfinite", value=token)
        return ScenePickCell(kind="float", value=numeric)
    if isinstance(value, str):
        return ScenePickCell(kind="text", value=value)
    raise SceneContractError(
        "unsupported_scene_source",
        f"scene source column {column!r} contains a value that cannot be represented exactly",
        details={"python_type": type(value).__name__},
    )


def _checkpoint(checkpoint: Checkpoint | None) -> None:
    if checkpoint is not None:
        checkpoint()
