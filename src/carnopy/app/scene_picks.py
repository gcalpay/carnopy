from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from typing import Literal

import numpy as np
import pandas as pd
from pydantic import ValidationError

from carnopy.app.scene_contracts import SceneContractError, SceneSourceBinding
from carnopy.app.scene_pick_contracts import (
    ResolveScenePickPayload,
    ScenePickCell,
    ScenePickColumn,
    ScenePickEvidenceRow,
    ScenePickPreparedContext,
    ScenePickResult,
)
from carnopy.app.scene_prepared_profiles import load_prepared_evidence
from carnopy.app.scene_profiles import _read_table, _stable_uint64
from carnopy.app.source_inspection import revalidate_scene_binding

Checkpoint = Callable[[], None]


def resolve_scene_pick(
    payload: ResolveScenePickPayload | Mapping[str, object],
    *,
    checkpoint: Checkpoint | None = None,
) -> ScenePickResult:
    """Resolve one scene point to its exact source row and prepared evidence."""

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
    accepted = revalidate_scene_binding(request.binding)
    _checkpoint(checkpoint)
    if accepted.source_kind == "preparation":
        result = _resolve_prepared_pick(request, accepted, checkpoint)
    else:
        result = _resolve_dataset_pick(request, accepted, checkpoint)
    _checkpoint(checkpoint)
    if revalidate_scene_binding(accepted) != accepted:  # pragma: no cover - exact comparison
        raise SceneContractError(
            "scene_source_changed",
            "scene source changed while its picked row was being resolved",
        )
    return result


def _resolve_dataset_pick(
    request: ResolveScenePickPayload,
    accepted: SceneSourceBinding,
    checkpoint: Checkpoint | None,
) -> ScenePickResult:
    selected = accepted.selected_table()
    frame = _read_table(selected, checkpoint).frame
    stable_ids = _frame_stable_ids(frame, "case_id", "scene pick")
    row_position = _match_pick_identity(request, stable_ids, "case_id")
    columns, cells = _pick_record(frame, row_position)
    return ScenePickResult(
        source_path=accepted.source_path,
        source_kind=accepted.source_kind,
        inspection_revision=accepted.inspection_revision,
        table_id=accepted.selected_table_id,
        table_sha256=selected.artifact.sha256,
        row_position=request.row_position,
        stable_id_field="case_id",
        stable_id=request.stable_id,
        columns=columns,
        cells=cells,
    )


def _resolve_prepared_pick(
    request: ResolveScenePickPayload,
    accepted: SceneSourceBinding,
    checkpoint: Checkpoint | None,
) -> ScenePickResult:
    evidence = load_prepared_evidence(
        accepted,
        checkpoint=checkpoint,
        complete_support_rows=True,
    )
    row_position = _match_pick_identity(
        request,
        evidence.stable_ids,
        "prepared_row_id",
    )
    columns, cells = _pick_record(evidence.selected, row_position)
    tables = {table.table_id: table for table in accepted.tables}
    provenance = _prepared_support_row(
        evidence.provenance,
        tables["provenance"].artifact.sha256,
        "provenance",
        request.stable_id,
    )
    diagnostics = _prepared_support_row(
        evidence.diagnostics,
        tables["diagnostics"].artifact.sha256,
        "diagnostics",
        request.stable_id,
    )
    scenario = None if evidence.scenario_context is None else evidence.scenario_context[0]
    partition = None if evidence.scenario_context is None else evidence.scenario_context[1]
    selected = accepted.selected_table()
    return ScenePickResult(
        source_path=accepted.source_path,
        source_kind="preparation",
        inspection_revision=accepted.inspection_revision,
        table_id=accepted.selected_table_id,
        table_sha256=selected.artifact.sha256,
        row_position=request.row_position,
        stable_id_field="prepared_row_id",
        stable_id=request.stable_id,
        columns=columns,
        cells=cells,
        prepared_context=ScenePickPreparedContext(
            provenance=provenance,
            diagnostics=diagnostics,
            scenario=scenario,
            partition=partition,
        ),
    )


def _prepared_support_row(
    frame: pd.DataFrame,
    table_sha256: str,
    table_id: Literal["provenance", "diagnostics"],
    stable_id: int,
) -> ScenePickEvidenceRow:
    stable_ids = _frame_stable_ids(frame, "prepared_row_id", f"prepared {table_id}")
    try:
        row_position = stable_ids.index(stable_id)
    except ValueError as exc:  # pragma: no cover - prepared join validation closes this
        raise SceneContractError(
            "scene_pick_stale",
            f"prepared {table_id} no longer contains the picked prepared_row_id",
        ) from exc
    columns, cells = _pick_record(frame, row_position)
    return ScenePickEvidenceRow(
        table_id=table_id,
        table_sha256=table_sha256,
        stable_id=stable_id,
        columns=columns,
        cells=cells,
    )


def _frame_stable_ids(
    frame: pd.DataFrame,
    field: str,
    label: str,
) -> tuple[int, ...]:
    if field not in frame.columns:
        raise SceneContractError(
            "scene_pick_stale",
            f"{label} row identity column {field} is unavailable",
        )
    stable_ids = tuple(_stable_uint64(value, f"{label} {field}") for value in frame[field].tolist())
    if len(set(stable_ids)) != len(stable_ids):
        raise SceneContractError(
            "scene_pick_stale",
            f"{label} repeats a {field} and cannot resolve an exact pick",
        )
    return stable_ids


def _match_pick_identity(
    request: ResolveScenePickPayload,
    stable_ids: tuple[int, ...],
    field: str,
) -> int:
    stable_id_catalog = set(stable_ids)
    if request.row_position >= len(stable_ids):
        raise SceneContractError(
            "scene_pick_stale",
            "scene source no longer contains the picked row position",
            details={
                "row_position": request.row_position,
                "source_row_count": len(stable_ids),
            },
        )
    if request.stable_id not in stable_id_catalog:
        raise SceneContractError(
            "scene_pick_stale",
            f"scene source no longer contains the picked {field}",
            details={"stable_id": request.stable_id},
        )
    observed_id = stable_ids[request.row_position]
    if observed_id != request.stable_id:
        raise SceneContractError(
            "scene_pick_stale",
            f"scene source row order no longer matches the picked {field}",
            details={
                "row_position": request.row_position,
                "stable_id": request.stable_id,
                "observed_stable_id": observed_id,
            },
        )
    return request.row_position


def _pick_record(
    frame: pd.DataFrame,
    row_position: int,
) -> tuple[tuple[ScenePickColumn, ...], tuple[ScenePickCell, ...]]:
    columns = tuple(
        ScenePickColumn(name=str(name), dtype=str(frame[name].dtype)) for name in frame.columns
    )
    cells = tuple(_pick_cell(frame[name].iloc[row_position], str(name)) for name in frame.columns)
    return columns, cells


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
