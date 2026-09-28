from __future__ import annotations

import json
import platform
from collections import Counter
from dataclasses import asdict, dataclass
from importlib.metadata import version
from pathlib import Path
from typing import Any, Literal

from carnopy._execution import ExecutionControl
from carnopy._version import __version__
from carnopy.sources import evidence
from carnopy.sources.config import ImportConfig, LoadedImportConfig, load_import_config
from carnopy.sources.eligibility import EligibilityCache, RecordStatus, assess_record
from carnopy.sources.errors import SourceImportError
from carnopy.sources.evidence import EvidenceInventory, ImportDiagnostic
from carnopy.sources.files import (
    SourceDescriptor,
    SourceSnapshot,
    read_source_snapshot,
    verify_source_snapshot,
)
from carnopy.sources.inventory import build_inventory, source_identity


@dataclass(frozen=True, slots=True)
class ImportCounts:
    total: int
    eligible: int
    unsupported: int
    invalid: int
    unselected: int


@dataclass(frozen=True, slots=True)
class ImportRecordPreview:
    dataset_index: int
    point_index: int
    property_number: int
    observation_id: str
    point_id: str
    status: RecordStatus
    quantity: str | None
    reported_quantity: str | None
    reported_value: str | None
    reported_digits: str | None
    phase: str | None
    text_truncated: bool
    reasons: tuple[str, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ImportDatasetPreview:
    dataset_index: int
    dataset_id: str
    reported_number: int | None
    kind: str
    component_count: int
    property_numbers: tuple[int, ...]
    omitted_properties: int
    counts: ImportCounts


@dataclass(frozen=True)
class ImportPreview:
    """Bounded, immutable preview. No file is written and no model is evaluated."""

    source: SourceDescriptor
    configuration: SourceDescriptor
    format: str
    adapter_version: str
    source_document_id: str
    publication_id: str
    request_id: str
    context_id: str
    status: Literal["ready", "ready_with_limitations", "no_eligible_observations"]
    counts: ImportCounts
    dataset_count: int
    datasets: tuple[ImportDatasetPreview, ...]
    omitted_datasets: int
    records: tuple[ImportRecordPreview, ...]
    omitted_records: int
    diagnostics: tuple[ImportDiagnostic, ...]
    omitted_diagnostics: int
    reason_counts: tuple[tuple[str, int], ...]
    warning_counts: tuple[tuple[str, int], ...]

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["source"]["path"] = str(self.source.path)
        payload["configuration"]["path"] = str(self.configuration.path)
        result: dict[str, Any] = json.loads(json.dumps(payload, allow_nan=False))
        return result


@dataclass(frozen=True)
class SourceImportPlan:
    """Private evidence retained for SOURCE-1.1B's future bundle writer."""

    source: SourceSnapshot
    config: LoadedImportConfig
    inventory: EvidenceInventory
    preview: ImportPreview


def _selection(config: ImportConfig, inventory: EvidenceInventory) -> dict[int, set[int]]:
    available = {
        dataset.index: {key for key, _ in dataset.properties} for dataset in inventory.datasets
    }
    if not config.selections:
        return available
    selected: dict[int, set[int]] = {}
    for item in config.selections:
        if item.dataset_index not in available:
            raise SourceImportError(
                "invalid_selection", f"unknown dataset index {item.dataset_index}"
            )
        numbers = set(item.property_numbers) or available[item.dataset_index]
        if numbers - available[item.dataset_index]:
            raise SourceImportError(
                "invalid_selection", "selection contains an unknown property number"
            )
        selected[item.dataset_index] = numbers
    return selected


def _counts(counts: Counter[str]) -> ImportCounts:
    return ImportCounts(
        sum(counts.values()),
        counts["eligible"],
        counts["unsupported"],
        counts["invalid"],
        counts["unselected"],
    )


def plan_source_import(
    source: str | Path,
    config: str | Path,
    *,
    control: ExecutionControl | None = None,
    accepted_preview: ImportPreview | None = None,
) -> SourceImportPlan:
    """Private cancellable operation; accepted previews pin files and exact YAML."""
    cancel = control.raise_if_cancelled if control else None
    if control:
        control.phase("source_import_preview")
    loaded = load_import_config(config, cancel=cancel)
    snapshot = read_source_snapshot(source, maximum_bytes=evidence.MAX_SOURCE_BYTES, cancel=cancel)
    if loaded.model.format == "thermoml_xml":
        from carnopy.sources.xml_reader import read_xml

        root = read_xml(snapshot.raw_bytes, cancel=cancel)
    else:
        from carnopy.sources.json_reader import read_json

        root = read_json(snapshot.raw_bytes, cancel=cancel)
    inventory = build_inventory(root, snapshot.descriptor.sha256, cancel=cancel)
    selections = _selection(loaded.model, inventory)
    records: list[ImportRecordPreview] = []
    datasets: list[ImportDatasetPreview] = []
    all_counts: Counter[str] = Counter()
    reasons: Counter[str] = Counter()
    warnings: Counter[str] = Counter()
    for dataset in inventory.datasets:
        cache = EligibilityCache(dict(dataset.properties), dict(dataset.variables))
        counts: Counter[str] = Counter()
        for record in dataset.records:
            if control:
                control.raise_if_cancelled()
            eligibility = assess_record(dataset, record, cache=cache)
            selected = record.property_number in selections.get(dataset.index, set())
            status: RecordStatus = eligibility.status if selected else "unselected"
            counts[status] += 1
            reasons.update(eligibility.reasons)
            warnings.update(eligibility.warnings)
            if selected and len(records) < evidence.PREVIEW_RECORD_LIMIT:
                texts = (
                    eligibility.reported_quantity,
                    record.value.value("nPropValue"),
                    record.value.value("nPropDigits"),
                    eligibility.phase,
                )
                clipped = tuple(value[:1024] if value is not None else None for value in texts)
                records.append(
                    ImportRecordPreview(
                        record.dataset_index,
                        record.point_index,
                        record.property_number,
                        record.observation_id,
                        record.point_id,
                        status,
                        eligibility.quantity,
                        clipped[0],
                        clipped[1],
                        clipped[2],
                        clipped[3],
                        texts != clipped,
                        eligibility.reasons,
                        eligibility.warnings,
                    )
                )
        all_counts.update(counts)
        if dataset.index in selections and len(datasets) < evidence.PREVIEW_RECORD_LIMIT:
            properties = tuple(key for key, _ in dataset.properties)
            datasets.append(
                ImportDatasetPreview(
                    dataset.index,
                    dataset.dataset_id,
                    dataset.reported_number,
                    dataset.kind,
                    len(
                        dataset.definition.all(
                            "Participant" if dataset.kind == "ReactionData" else "Component"
                        )
                    ),
                    properties[: evidence.PREVIEW_RECORD_LIMIT],
                    max(0, len(properties) - evidence.PREVIEW_RECORD_LIMIT),
                    _counts(counts),
                )
            )
    request_id = source_identity(
        "import-request",
        {
            "configuration": loaded.model.model_dump(mode="json"),
            "source_document_id": inventory.source_document_id,
        },
    )
    context_id = source_identity(
        "import-context",
        {
            "request_id": request_id,
            "configuration_sha256": loaded.snapshot.descriptor.sha256,
            "adapter_version": evidence.ADAPTER_VERSION,
            "bundle_schema_version": 1,
            "parquet_writer_version": version("pyarrow"),
            "carnopy_version": __version__,
            "python_version": platform.python_version(),
            "xml_parser_version": version("defusedxml")
            if loaded.model.format == "thermoml_xml"
            else None,
        },
    )
    counts_result = _counts(all_counts)
    status_result: Literal["ready", "ready_with_limitations", "no_eligible_observations"] = (
        "ready_with_limitations" if counts_result.eligible else "no_eligible_observations"
    )
    preview = ImportPreview(
        snapshot.descriptor,
        loaded.snapshot.descriptor,
        loaded.model.format,
        evidence.ADAPTER_VERSION,
        inventory.source_document_id,
        inventory.publication_id,
        request_id,
        context_id,
        status_result,
        counts_result,
        len(inventory.datasets),
        tuple(datasets),
        len(inventory.datasets) - len(datasets),
        tuple(records),
        counts_result.total - len(records),
        inventory.diagnostics[: evidence.PREVIEW_RECORD_LIMIT],
        max(0, len(inventory.diagnostics) - evidence.PREVIEW_RECORD_LIMIT),
        tuple(sorted(reasons.items())),
        tuple(sorted(warnings.items())),
    )
    verify_source_snapshot(snapshot, maximum_bytes=evidence.MAX_SOURCE_BYTES, cancel=cancel)
    verify_source_snapshot(loaded.snapshot, maximum_bytes=1024 * 1024, cancel=cancel)
    if accepted_preview is not None and (
        preview.source != accepted_preview.source
        or preview.configuration != accepted_preview.configuration
        or preview.context_id != accepted_preview.context_id
    ):
        raise SourceImportError("stale_preview", "source or configuration changed since preview")
    return SourceImportPlan(snapshot, loaded, inventory, preview)
