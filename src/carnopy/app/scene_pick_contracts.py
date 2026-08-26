from __future__ import annotations

import math
from pathlib import Path
from typing import Annotated, Final, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)

from carnopy.app.scene_contracts import SceneSourceBinding

SCENE_PICK_SCHEMA_VERSION: Final[Literal[1]] = 1

Uint64 = Annotated[StrictInt, Field(ge=0, le=2**64 - 1)]
ScenePickSourceKind = Literal["dataset", "model_sweep", "preparation"]
ScenePickStableIdField = Literal["case_id", "prepared_row_id"]
ScenePickCellKind = Literal["null", "boolean", "integer", "float", "nonfinite", "text"]
ScenePickCellValue = StrictBool | StrictInt | StrictFloat | StrictStr | None


class ResolveScenePickPayload(BaseModel):
    """Exact source identity stored for one renderer-neutral scene point."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scene_pick_schema_version: Literal[1] = SCENE_PICK_SCHEMA_VERSION
    binding: SceneSourceBinding
    row_position: Uint64
    stable_id: Uint64


class ScenePickColumn(BaseModel):
    """One source column in its original table order."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: StrictStr
    dtype: StrictStr

    @field_validator("name", "dtype")
    @classmethod
    def nonempty_text(cls, value: str) -> str:
        if not value or value.strip() != value or "\x00" in value:
            raise ValueError("scene pick column metadata must be exact nonempty text")
        return value


class ScenePickCell(BaseModel):
    """Loss-aware JSON representation of one exact source-table cell."""

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    kind: ScenePickCellKind
    value: ScenePickCellValue = None

    @model_validator(mode="after")
    def consistent_value(self) -> ScenePickCell:
        value = self.value
        if self.kind == "null":
            valid = value is None
        elif self.kind == "boolean":
            valid = type(value) is bool
        elif self.kind == "integer":
            valid = type(value) is int
        elif self.kind == "float":
            valid = type(value) is float and math.isfinite(value)
        elif self.kind == "nonfinite":
            valid = value in {"positive_infinity", "negative_infinity"}
        else:
            valid = type(value) is str
        if not valid:
            raise ValueError(f"scene pick cell kind {self.kind!r} disagrees with its value")
        return self


class ScenePickEvidenceRow(BaseModel):
    """One exact prepared support-table row joined by ``prepared_row_id``."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    table_id: Literal["provenance", "diagnostics"]
    table_sha256: StrictStr
    stable_id: Uint64
    columns: tuple[ScenePickColumn, ...]
    cells: tuple[ScenePickCell, ...]

    @field_validator("table_sha256")
    @classmethod
    def canonical_sha256(cls, value: str) -> str:
        return _canonical_sha256(value)

    @model_validator(mode="after")
    def consistent_row(self) -> ScenePickEvidenceRow:
        names = _validate_record(self.columns, self.cells, f"prepared {self.table_id}")
        if "prepared_row_id" not in names:
            raise ValueError(f"prepared {self.table_id} row must contain prepared_row_id")
        identity = self.cells[names.index("prepared_row_id")]
        if identity.kind != "integer" or identity.value != self.stable_id:
            raise ValueError(f"prepared {self.table_id} row disagrees with its prepared_row_id")
        return self

    def row(self) -> dict[str, ScenePickCell]:
        """Return a detached ordered mapping for this support-table row."""

        return _detached_row(self.columns, self.cells)


class ScenePickPreparedContext(BaseModel):
    """Verified joined evidence and optional scenario identity for a prepared row."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provenance: ScenePickEvidenceRow
    diagnostics: ScenePickEvidenceRow
    scenario: StrictStr | None = None
    partition: StrictStr | None = None

    @field_validator("scenario", "partition")
    @classmethod
    def exact_optional_context(cls, value: str | None) -> str | None:
        if value is not None and (not value or value.strip() != value or "\x00" in value):
            raise ValueError("prepared scene pick context must be exact nonempty text")
        return value

    @model_validator(mode="after")
    def consistent_context(self) -> ScenePickPreparedContext:
        if self.provenance.table_id != "provenance":
            raise ValueError("prepared scene pick provenance uses the wrong table identity")
        if self.diagnostics.table_id != "diagnostics":
            raise ValueError("prepared scene pick diagnostics uses the wrong table identity")
        if self.provenance.stable_id != self.diagnostics.stable_id:
            raise ValueError("prepared scene pick evidence disagrees on prepared_row_id")
        if (self.scenario is None) != (self.partition is None):
            raise ValueError("prepared scene pick scenario and partition must appear together")
        return self


class ScenePickResult(BaseModel):
    """One exact row accepted only after source and dual-identity checks."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scene_pick_schema_version: Literal[1] = SCENE_PICK_SCHEMA_VERSION
    source_path: StrictStr
    source_kind: ScenePickSourceKind
    inspection_revision: StrictStr
    table_id: StrictStr
    table_sha256: StrictStr
    row_position: Uint64
    stable_id_field: ScenePickStableIdField
    stable_id: Uint64
    columns: tuple[ScenePickColumn, ...]
    cells: tuple[ScenePickCell, ...]
    prepared_context: ScenePickPreparedContext | None = None

    @field_validator("source_path")
    @classmethod
    def absolute_source_path(cls, value: str) -> str:
        if not value or not Path(value).is_absolute():
            raise ValueError("scene pick source path must be absolute")
        return value

    @field_validator("inspection_revision", "table_sha256")
    @classmethod
    def canonical_sha256(cls, value: str) -> str:
        return _canonical_sha256(value)

    @field_validator("table_id")
    @classmethod
    def exact_table_id(cls, value: str) -> str:
        if not value or value.strip() != value or "\x00" in value:
            raise ValueError("scene pick table ID must be exact nonempty text")
        return value

    @model_validator(mode="after")
    def consistent_row(self) -> ScenePickResult:
        names = _validate_record(self.columns, self.cells, "scene pick")
        expected_field: ScenePickStableIdField = (
            "prepared_row_id" if self.source_kind == "preparation" else "case_id"
        )
        if self.stable_id_field != expected_field or expected_field not in names:
            raise ValueError("scene pick stable-ID field disagrees with its source kind")
        identity = self.cells[names.index(expected_field)]
        if identity.kind != "integer" or identity.value != self.stable_id:
            raise ValueError(f"scene pick row disagrees with its stable {expected_field}")
        context = self.prepared_context
        if self.source_kind != "preparation":
            if context is not None:
                raise ValueError("direct scene picks cannot contain prepared evidence")
            return self
        if context is None:
            raise ValueError("prepared scene picks require joined evidence")
        if (
            context.provenance.stable_id != self.stable_id
            or context.diagnostics.stable_id != self.stable_id
        ):
            raise ValueError("prepared scene pick evidence disagrees with its stable ID")
        expected_table = (
            "table"
            if context.scenario is None
            else f"scenario.{context.scenario}.{context.partition}"
        )
        if self.table_id != expected_table:
            raise ValueError("prepared scene pick context disagrees with its selected table")
        return self

    def row(self) -> dict[str, ScenePickCell]:
        """Return the exact ordered source row as a detached name/cell mapping."""

        return _detached_row(self.columns, self.cells)


def _canonical_sha256(value: str) -> str:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError("scene pick identity must use canonical SHA-256 text")
    return value


def _validate_record(
    columns: tuple[ScenePickColumn, ...],
    cells: tuple[ScenePickCell, ...],
    label: str,
) -> tuple[str, ...]:
    names = tuple(column.name for column in columns)
    if not names or len(names) != len(set(names)):
        raise ValueError(f"{label} columns must be nonempty and unique")
    if len(cells) != len(columns):
        raise ValueError(f"{label} cells must align with their source columns")
    return names


def _detached_row(
    columns: tuple[ScenePickColumn, ...],
    cells: tuple[ScenePickCell, ...],
) -> dict[str, ScenePickCell]:
    return {
        column.name: cell.model_copy(deep=True) for column, cell in zip(columns, cells, strict=True)
    }
