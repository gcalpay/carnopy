from __future__ import annotations

from collections.abc import Iterator, KeysView, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from carnopy.sources.errors import SourceImportError

THERMOML_NAMESPACE = "http://www.iupac.org/namespaces/ThermoML"
ADAPTER_VERSION = "thermoml-subset-2"
MAX_SOURCE_BYTES = 64 * 1024 * 1024
MAX_DEPTH = 64
MAX_SCALAR_BYTES = 1024 * 1024
MAX_PROPERTY_VALUES = 1_000_000
MAX_NODES = 1_000_000
PREVIEW_RECORD_LIMIT = 500


@dataclass(frozen=True, slots=True)
class EvidenceElement:
    """Ordered ThermoML evidence; numeric text is never parsed through float."""

    name: str
    text: str | None = None
    children: tuple[EvidenceElement, ...] = ()
    attributes: tuple[tuple[str, str], ...] = ()
    _index: Mapping[str, tuple[EvidenceElement, ...]] | None = field(
        default=None,
        init=False,
        repr=False,
        compare=False,
    )
    has_attributes: bool = field(default=False, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "has_attributes",
            bool(self.attributes or any(child.has_attributes for child in self.children)),
        )
        if self.children:
            grouped: dict[str, list[EvidenceElement]] = {}
            for child in self.children:
                grouped.setdefault(child.name, []).append(child)
            object.__setattr__(
                self,
                "_index",
                MappingProxyType({key: tuple(nodes) for key, nodes in grouped.items()}),
            )

    @property
    def child_names(self) -> KeysView[str]:
        return self._index.keys() if self._index else {}.keys()

    def all(self, name: str) -> tuple[EvidenceElement, ...]:
        return self._index.get(name, ()) if self._index else ()

    def one(self, name: str) -> EvidenceElement | None:
        matches = self.all(name)
        if len(matches) > 1:
            raise SourceImportError("ambiguous_structure", f"repeated singleton {name}")
        return matches[0] if matches else None

    def value(self, name: str) -> str | None:
        child = self.one(name)
        if child is None:
            return None
        if child.children:
            raise SourceImportError("ambiguous_structure", f"{name} must be a scalar")
        return child.text.strip() if child.text is not None else None

    def walk(self) -> Iterator[EvidenceElement]:
        yield self
        for child in self.children:
            yield from child.walk()


@dataclass(frozen=True, slots=True)
class ImportDiagnostic:
    code: str
    locator: str
    message: str


@dataclass(frozen=True, slots=True)
class RecordEvidence:
    dataset_index: int
    point_index: int
    property_number: int
    dataset_id: str
    point_id: str
    observation_id: str
    value: EvidenceElement
    variables: tuple[EvidenceElement, ...]
    point_qualifiers: tuple[EvidenceElement, ...] = ()

    @property
    def locator(self) -> str:
        return (
            f"dataset[{self.dataset_index}]/NumValues[{self.point_index}]"
            f"/PropertyValue[{self.property_number}]"
        )


@dataclass(frozen=True, slots=True)
class DatasetEvidence:
    index: int
    reported_number: int | None
    dataset_id: str
    kind: str
    definition: EvidenceElement
    component_numbers: tuple[int, ...]
    properties: tuple[tuple[int, EvidenceElement], ...]
    variables: tuple[tuple[int, EvidenceElement], ...]
    records: tuple[RecordEvidence, ...]


@dataclass(frozen=True, slots=True)
class EvidenceInventory:
    source_document_id: str
    publication_id: str
    root: EvidenceElement
    compounds: tuple[tuple[int, EvidenceElement], ...]
    datasets: tuple[DatasetEvidence, ...]
    diagnostics: tuple[ImportDiagnostic, ...]
