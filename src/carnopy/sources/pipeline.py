from __future__ import annotations

import platform
from collections import Counter
from dataclasses import asdict
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any
from uuid import uuid4

from carnopy._execution import ExecutionControl
from carnopy._version import __version__
from carnopy.config.normalize import canonical_json_bytes
from carnopy.domain.failures import OutputError
from carnopy.outputs.layout import (
    cleanup_run_layout,
    create_artifact_layout,
    finalize_run_layout,
)
from carnopy.sources.bundle import (
    MAX_ARTIFACT_BYTES,
    directory_identity,
    read_source_bundle,
)
from carnopy.sources.evidence import (
    ADAPTER_VERSION,
    MAX_SOURCE_BYTES,
    PREVIEW_RECORD_LIMIT,
    ImportDiagnostic,
)
from carnopy.sources.files import read_source_descriptor, verify_source_snapshot
from carnopy.sources.inventory import source_identity
from carnopy.sources.metadata import component_id, data_origin, element_payload
from carnopy.sources.normalization import normalize_records
from carnopy.sources.preview import ImportPreview, SourceImportPlan, plan_source_import
from carnopy.sources.results import ImportAccounting, ImportArtifact, ImportResult, ImportStatus
from carnopy.sources.tables import SourceTableWriter, schema_description, table_schemas


def _catalog_header(plan: SourceImportPlan) -> dict[str, Any]:
    inventory = plan.inventory
    qualified_compounds = {id(node) for _, node in inventory.compounds}
    return {
        "schema_version": 1,
        "source_document_id": inventory.source_document_id,
        "publication_id": inventory.publication_id,
        "root_metadata": [
            element_payload(child)
            for child in inventory.root.children
            if child.name not in {"PureOrMixtureData", "ReactionData", "Compound"}
        ],
        "compounds": [
            {
                "component_id": component_id(inventory.source_document_id, number),
                "reported_number": str(number),
                "evidence": element_payload(node),
            }
            for number, node in inventory.compounds
        ],
        "unqualified_compounds": [
            element_payload(node)
            for node in inventory.root.all("Compound")
            if id(node) not in qualified_compounds
        ],
        "datasets": [
            {
                "dataset_id": dataset.dataset_id,
                "dataset_index": dataset.index,
                "reported_number": None
                if dataset.reported_number is None
                else str(dataset.reported_number),
                "kind": dataset.kind,
                "definition": element_payload(dataset.definition),
                "properties": [
                    {
                        "property_number": str(number),
                        "property_id": source_identity(
                            "property",
                            {"dataset_id": dataset.dataset_id, "property_number": number},
                        ),
                        "data_origin": data_origin(node)[0],
                        "origin_rule": data_origin(node)[1],
                    }
                    for number, node in dataset.properties
                ],
            }
            for dataset in inventory.datasets
        ],
    }


def run_source_import(
    source: str | Path,
    config: str | Path,
    *,
    output_root: str | Path = "outputs",
    control: ExecutionControl | None = None,
    accepted_preview: ImportPreview | None = None,
) -> ImportResult:
    """Private cancellable import; the public API exposes only finalized results."""
    plan = plan_source_import(source, config, control=control, accepted_preview=accepted_preview)
    root = Path(output_root).absolute()
    directory_identity(root, allow_missing=True)
    run_id, created_at = str(uuid4()), datetime.now(UTC)
    if control:
        control.phase("source_import_normalization")
    layout = create_artifact_layout(
        output_root=root, slug="source_import", run_id=run_id, created_at=created_at
    )
    root_identity = directory_identity(root)
    stage = layout.staging_directory
    stage_identity = directory_identity(stage)
    writers: dict[str, SourceTableWriter] = {}
    owned_directories: dict[Path, tuple[int, int] | None] = {}

    def check() -> None:
        if control:
            control.raise_if_cancelled()
        if directory_identity(root) != root_identity or directory_identity(stage) != stage_identity:
            raise OutputError("source-import output directory was replaced")
        if any(
            directory_identity(path) != identity for path, identity in owned_directories.items()
        ):
            raise OutputError("source-import artifact directory was replaced")

    def write(relative: str, content: bytes) -> None:
        check()
        if len(content) > MAX_ARTIFACT_BYTES:
            raise OutputError("source-import artifact size limit exceeded")
        with (stage / relative).open("xb") as stream:
            stream.write(content)

    counts: Counter[str] = Counter()
    reasons: Counter[str] = Counter()
    warnings: Counter[str] = Counter()
    origins: Counter[str] = Counter()
    diagnostics: list[ImportDiagnostic] = []
    diagnostic_count = 0
    try:
        check()
        (stage / "source").mkdir()
        (stage / "data").mkdir()
        owned_directories.update(
            {path: directory_identity(path) for path in (stage / "data", stage / "source")}
        )
        source_path = (
            "source/original.xml"
            if plan.config.model.format == "thermoml_xml"
            else "source/original.json"
        )
        write(source_path, plan.source.raw_bytes)
        write("request.original.yaml", plan.config.snapshot.raw_bytes)
        write(
            "request.normalized.json",
            canonical_json_bytes(plan.config.model.model_dump(mode="json")),
        )
        for name, schema in table_schemas().items():
            writers[name] = SourceTableWriter(stage / "data" / f"{name}.parquet", schema, check)

        def append_diagnostic(row: dict[str, Any]) -> None:
            nonlocal diagnostic_count
            writers["diagnostics"].append(row)
            diagnostic_count += 1
            if len(diagnostics) < PREVIEW_RECORD_LIMIT:
                diagnostics.append(ImportDiagnostic(row["code"], row["locator"], row["message"]))

        for item in plan.inventory.diagnostics:
            append_diagnostic(
                {
                    "diagnostic_id": source_identity(
                        "document-diagnostic",
                        {
                            "source_document_id": plan.inventory.source_document_id,
                            "code": item.code,
                            "locator": item.locator,
                        },
                    ),
                    "dataset_id": None,
                    "point_id": None,
                    "source_record_id": None,
                    "observation_id": None,
                    "target_id": plan.inventory.source_document_id,
                    "locator": item.locator,
                    "code": item.code,
                    "message": item.message,
                    "severity": "info" if item.code == "not_independently_validated" else "warning",
                }
            )
        # Stream the full inventory instead of keeping a second million-record
        # projection beside the already bounded parser evidence.
        with (stage / "catalog.json").open("xb") as catalog:
            header = canonical_json_bytes(_catalog_header(plan)).rstrip()
            catalog.write(header[:-1] + b',"records":[')
            first = True
            for record in normalize_records(plan, control=control):
                check()
                if not first:
                    catalog.write(b",")
                catalog.write(canonical_json_bytes(record.inventory))
                if catalog.tell() > MAX_ARTIFACT_BYTES:
                    raise OutputError("source-import catalog size limit exceeded")
                first = False
                counts[record.inventory["status"]] += 1
                reasons.update(record.inventory["reasons"])
                warnings.update(record.inventory["warnings"])
                origins[record.inventory["data_origin"]] += 1
                if record.observation is not None:
                    assert record.provenance is not None
                    writers["observations"].append(record.observation)
                    writers["provenance"].append(record.provenance)
                for row in record.uncertainties:
                    writers["uncertainties"].append(row)
                for row in record.diagnostics:
                    append_diagnostic(row)
            accounting = ImportAccounting(
                sum(counts.values()),
                counts["normalized"],
                counts["unsupported"],
                counts["invalid"],
                counts["unselected"],
            )
            catalog.write(b'],"counts":' + canonical_json_bytes(asdict(accounting)) + b"}")
        for writer in writers.values():
            writer.close()
        if control:
            control.phase("source_import_verification")
        status: ImportStatus = "completed"
        if not accounting.normalized:
            status = "no_eligible_observations"
        elif (
            accounting.unsupported
            or accounting.invalid
            or warnings
            or any(
                item.code != "not_independently_validated" for item in plan.inventory.diagnostics
            )
        ):
            status = "completed_with_limitations"
        identity = {
            "source_document_id": plan.inventory.source_document_id,
            "publication_id": plan.inventory.publication_id,
            "request_id": plan.preview.request_id,
            "context_id": plan.preview.context_id,
            "run_id": run_id,
            "status": status,
        }
        report = {
            **identity,
            "schema_version": 1,
            "counts": asdict(accounting),
            "reason_counts": dict(sorted(reasons.items())),
            "warning_counts": dict(sorted(warnings.items())),
            "data_origin_counts": dict(sorted(origins.items())),
            "diagnostic_count": diagnostic_count,
            "diagnostics_preview": [asdict(item) for item in diagnostics],
            "omitted_diagnostics": max(0, diagnostic_count - len(diagnostics)),
            "independently_validated": False,
            "limitations": [
                "Supported ThermoML subset; not complete XSD validation.",
                "Import does not establish independent scientific validity "
                "or backend compatibility.",
            ],
        }
        write("report.json", canonical_json_bytes(report))
        artifacts: list[ImportArtifact] = []
        paths = {
            "source": source_path,
            "request_original": "request.original.yaml",
            "request_normalized": "request.normalized.json",
            "catalog": "catalog.json",
            "report": "report.json",
            **{name: f"data/{name}.parquet" for name in writers},
        }
        for name, relative in paths.items():
            descriptor = read_source_descriptor(
                stage / relative, maximum_bytes=MAX_ARTIFACT_BYTES, cancel=check
            )
            artifacts.append(
                ImportArtifact(
                    name,
                    relative,
                    descriptor.sha256,
                    descriptor.size,
                    writers[name].count if name in writers else None,
                )
            )
        manifest = {
            **identity,
            "schema_version": 1,
            "bundle_kind": "imported_source",
            "format": plan.config.model.format,
            "adapter_version": ADAPTER_VERSION,
            "created_at_utc": created_at.isoformat(),
            "software": {"name": "Carnopy", "version": __version__},
            "runtime_versions": {
                "python": platform.python_version(),
                "pyarrow": version("pyarrow"),
                "defusedxml": version("defusedxml")
                if plan.config.model.format == "thermoml_xml"
                else None,
            },
            "capability_profile": "thermoml-density-source-1.1b",
            "source": {
                "path": source_path,
                "sha256": plan.inventory.source_document_id,
                "size": plan.source.descriptor.size,
            },
            "counts": asdict(accounting),
            "artifact_hashes": {item.path: item.sha256 for item in artifacts},
            "artifacts": [asdict(item) for item in artifacts],
            "tables": {
                name: {
                    "path": f"data/{name}.parquet",
                    "row_count": writer.count,
                    "columns": schema_description(writer.schema),
                }
                for name, writer in writers.items()
            },
            "independently_validated": False,
        }
        write("manifest.json", canonical_json_bytes(manifest))
        verified = read_source_bundle(stage, cancel=check)
        check()
        verify_source_snapshot(plan.source, maximum_bytes=MAX_SOURCE_BYTES, cancel=check)
        verify_source_snapshot(plan.config.snapshot, maximum_bytes=1024 * 1024, cancel=check)
        if control:
            control.protected_phase("source_import_finalization")
        # The final worker/parent handoff may itself take time. Recheck the two
        # consumed inputs after entering the protected section, before publishing.
        verify_source_snapshot(plan.source, maximum_bytes=MAX_SOURCE_BYTES)
        verify_source_snapshot(plan.config.snapshot, maximum_bytes=1024 * 1024)
        for descriptor in (*verified.artifacts, verified.manifest_descriptor):
            if (
                read_source_descriptor(descriptor.path, maximum_bytes=MAX_ARTIFACT_BYTES)
                != descriptor
            ):
                raise OutputError("source bundle changed before finalization")
        check()
        finalize_run_layout(layout)
        return ImportResult(
            status,
            plan.inventory.source_document_id,
            plan.inventory.publication_id,
            plan.preview.request_id,
            plan.preview.context_id,
            run_id,
            layout.final_directory,
            layout.final_directory / "manifest.json",
            verified.manifest_descriptor.sha256,
            accounting,
            tuple(artifacts),
            tuple(diagnostics),
            max(0, diagnostic_count - len(diagnostics)),
            tuple(sorted(reasons.items())),
            tuple(sorted(warnings.items())),
        )
    except BaseException as exc:
        for writer in writers.values():
            if not writer.stream.closed:
                try:
                    writer.abort()
                except OSError as close_error:
                    exc.add_note(f"could not close staged table: {close_error}")
        try:
            cleanup_run_layout(layout)
        except OutputError as cleanup_error:
            exc.add_note(str(cleanup_error))
        if isinstance(exc, OSError):
            raise OutputError(f"could not write source bundle: {exc}") from exc
        raise
