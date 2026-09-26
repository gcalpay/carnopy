from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from carnopy.sources.errors import SourceImportError
from carnopy.sources.files import Checkpoint, SourceSnapshot, read_source_snapshot

SourceFormat = Literal["thermoml_xml", "thermoml_json"]
StrictInteger = Annotated[int, Field(strict=True)]


class ImportSelection(BaseModel):
    """A zero-based dataset locator and optional reported property numbers."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    dataset_index: Annotated[int, Field(strict=True, ge=0)]
    property_numbers: tuple[StrictInteger, ...] = ()

    @model_validator(mode="after")
    def unique_properties(self) -> ImportSelection:
        if len(set(self.property_numbers)) != len(self.property_numbers):
            raise ValueError("property_numbers must not contain duplicates")
        return self


class ImportConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    document_type: Literal["source_import"]
    format: SourceFormat
    selections: tuple[ImportSelection, ...] = ()

    @model_validator(mode="before")
    @classmethod
    def strict_version(cls, value: Any) -> Any:
        if isinstance(value, dict) and type(value.get("schema_version")) is not int:
            raise ValueError("schema_version must be integer 1")
        return value

    @model_validator(mode="after")
    def unique_datasets(self) -> ImportConfig:
        ids = [selection.dataset_index for selection in self.selections]
        if len(ids) != len(set(ids)):
            raise ValueError("select each dataset at most once")
        return self


@dataclass(frozen=True)
class LoadedImportConfig:
    snapshot: SourceSnapshot
    model: ImportConfig


class _UniqueLoader(yaml.SafeLoader):  # type: ignore[misc]  # PyYAML has no bundled stubs.
    def construct_mapping(self, node: Any, deep: bool = False) -> dict[Any, Any]:
        result: dict[Any, Any] = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, (str, int)) or key in result:
                raise SourceImportError("invalid_config", "duplicate or invalid YAML mapping key")
            result[key] = self.construct_object(value_node, deep=deep)
        return result


def load_import_config(
    path: str | Path,
    *,
    cancel: Checkpoint | None = None,
) -> LoadedImportConfig:
    snapshot = read_source_snapshot(path, maximum_bytes=1024 * 1024, cancel=cancel)
    try:
        depth = 0
        for event in yaml.parse(snapshot.raw_bytes):
            if isinstance(event, yaml.AliasEvent):
                raise SourceImportError("invalid_config", "YAML aliases are not supported")
            if isinstance(event, (yaml.MappingStartEvent, yaml.SequenceStartEvent)):
                depth += 1
                if depth > 64:
                    raise SourceImportError("invalid_config", "configuration nesting is too deep")
            elif isinstance(event, (yaml.MappingEndEvent, yaml.SequenceEndEvent)):
                depth -= 1
        payload = yaml.load(snapshot.raw_bytes, Loader=_UniqueLoader)
        model = ImportConfig.model_validate(payload)
    except (yaml.YAMLError, UnicodeError, ValidationError, RecursionError) as exc:
        raise SourceImportError("invalid_config", str(exc)) from exc
    return LoadedImportConfig(snapshot, model)
