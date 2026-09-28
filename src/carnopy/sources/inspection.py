from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from carnopy.sources.bundle import SourceBundle, read_source_bundle
from carnopy.sources.evidence import PREVIEW_RECORD_LIMIT


@dataclass(frozen=True)
class SourceInspection:
    source: Path
    bundle: SourceBundle

    def to_dict(self) -> dict[str, Any]:
        manifest, catalog, report = self.bundle.manifest, self.bundle.catalog, self.bundle.report
        return {
            "inspection_schema_version": 1,
            "source_kind": "imported_source",
            "source": str(self.source),
            "bundle_schema_version": manifest["schema_version"],
            "manifest_sha256": self.bundle.manifest_descriptor.sha256,
            **{
                key: manifest[key]
                for key in (
                    "source_document_id",
                    "publication_id",
                    "request_id",
                    "context_id",
                    "run_id",
                    "status",
                    "counts",
                    "format",
                    "tables",
                    "artifact_hashes",
                )
            },
            "independently_validated": False,
            "reason_counts": report["reason_counts"],
            "warning_counts": report["warning_counts"],
            "data_origin_counts": report["data_origin_counts"],
            "records_preview": catalog["records"][:PREVIEW_RECORD_LIMIT],
            "omitted_records": max(0, len(catalog["records"]) - PREVIEW_RECORD_LIMIT),
            "diagnostics_preview": report["diagnostics_preview"],
            "omitted_diagnostics": report["omitted_diagnostics"],
        }

    def format_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True, ensure_ascii=False)

    def format_text(self) -> str:
        payload = self.to_dict()
        return "\n".join(
            [
                f"Source: {self.source}",
                "Source kind: imported_source (ThermoML density evidence)",
                f"Status: {payload['status']}",
                f"Publication: {payload['publication_id']}",
                f"Source document: {payload['source_document_id']}",
                f"Manifest SHA-256: {payload['manifest_sha256']}",
                "Records: "
                + ", ".join(f"{key}={value}" for key, value in payload["counts"].items()),
                "Tables:",
                *[
                    f"  {name}: {table['row_count']} rows ({table['path']})"
                    for name, table in payload["tables"].items()
                ],
                "Warnings: " + json.dumps(payload["warning_counts"], sort_keys=True),
                "Normalization preserves evidence; it is not independent scientific validation.",
            ]
        )


def inspect_imported_source(source: str | Path) -> SourceInspection:
    bundle = read_source_bundle(source)
    return SourceInspection(bundle.root, bundle)
