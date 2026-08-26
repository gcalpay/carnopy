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
ScenePickSourceKind = Literal["dataset", "model_sweep"]
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
    stable_id_field: Literal["case_id"] = "case_id"
    stable_id: Uint64
    columns: tuple[ScenePickColumn, ...]
    cells: tuple[ScenePickCell, ...]

    @field_validator("source_path")
    @classmethod
    def absolute_source_path(cls, value: str) -> str:
        if not value or not Path(value).is_absolute():
            raise ValueError("scene pick source path must be absolute")
        return value

    @field_validator("inspection_revision", "table_sha256")
    @classmethod
    def canonical_sha256(cls, value: str) -> str:
        if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
            raise ValueError("scene pick identity must use canonical SHA-256 text")
        return value

    @field_validator("table_id")
    @classmethod
    def exact_table_id(cls, value: str) -> str:
        if not value or value.strip() != value or "\x00" in value:
            raise ValueError("scene pick table ID must be exact nonempty text")
        return value

    @model_validator(mode="after")
    def consistent_row(self) -> ScenePickResult:
        names = tuple(column.name for column in self.columns)
        if not names or len(names) != len(set(names)):
            raise ValueError("scene pick columns must be nonempty and unique")
        if len(self.cells) != len(self.columns):
            raise ValueError("scene pick cells must align with the source columns")
        if "case_id" not in names:
            raise ValueError("scene pick row must contain case_id")
        case_cell = self.cells[names.index("case_id")]
        if case_cell.kind != "integer" or case_cell.value != self.stable_id:
            raise ValueError("scene pick row disagrees with its stable case_id")
        return self

    def row(self) -> dict[str, ScenePickCell]:
        """Return the exact ordered source row as a detached name/cell mapping."""

        return {
            column.name: cell.model_copy(deep=True)
            for column, cell in zip(self.columns, self.cells, strict=True)
        }
