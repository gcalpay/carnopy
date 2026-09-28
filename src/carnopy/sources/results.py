from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from carnopy.sources.evidence import ImportDiagnostic

ImportStatus = Literal["completed", "completed_with_limitations", "no_eligible_observations"]


@dataclass(frozen=True, slots=True)
class ImportAccounting:
    total: int
    normalized: int
    unsupported: int
    invalid: int
    unselected: int


@dataclass(frozen=True, slots=True)
class ImportArtifact:
    name: str
    path: str
    sha256: str
    size: int
    row_count: int | None = None


@dataclass(frozen=True)
class ImportResult:
    """Immutable, lightweight references to a finalized evidence snapshot."""

    status: ImportStatus
    source_document_id: str
    publication_id: str
    request_id: str
    context_id: str
    run_id: str
    output_directory: Path
    manifest_path: Path
    manifest_sha256: str
    counts: ImportAccounting
    artifacts: tuple[ImportArtifact, ...]
    diagnostics: tuple[ImportDiagnostic, ...]
    omitted_diagnostics: int
    reason_counts: tuple[tuple[str, int], ...]
    warning_counts: tuple[tuple[str, int], ...]

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["output_directory"] = str(self.output_directory)
        payload["manifest_path"] = str(self.manifest_path)
        result: dict[str, Any] = json.loads(json.dumps(payload, allow_nan=False))
        return result
