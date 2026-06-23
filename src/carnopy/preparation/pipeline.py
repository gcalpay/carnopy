from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pandas as pd

from carnopy.domain.failures import OutputError
from carnopy.outputs.writers import hash_artifacts, write_bytes, write_json
from carnopy.preparation.fields import ResolvedPreparation, resolve_preparation_fields
from carnopy.preparation.layout import (
    PreparationLayout,
    cleanup_staging,
    create_preparation_layout,
    finalize_preparation_layout,
)
from carnopy.preparation.models import LoadedPreparationConfig, load_preparation_config
from carnopy.preparation.reporting import (
    build_dataset_card,
    build_diagnostics,
    build_manifest,
    normalized_preparation_bytes,
    preparation_context_id,
)
from carnopy.preparation.rows import PreparedRows, build_prepared_rows, exclusions_frame
from carnopy.preparation.source import LoadedPreparationSource, load_preparation_source
from carnopy.provenance import sha256_bytes
from carnopy.results import PreparationResult, PreparationStatus


@dataclass(frozen=True)
class BundleWriteResult:
    preparation_request_id: str
    preparation_context_id: str
    status: PreparationStatus
    eligible_row_count: int
    excluded_row_count: int
    unsplit_path: Path | None


def prepare_dataset(
    source: str | Path,
    config: str | Path,
    *,
    output_root: str | Path = "prepared",
) -> PreparationResult:
    loaded = load_preparation_config(config)
    source_data = load_preparation_source(
        source,
        allow_partial_sweep=loaded.model.source_policy.allow_partial_sweep,
    )
    resolved = resolve_preparation_fields(loaded.model, source_data.tables)
    normalized_bytes = normalized_preparation_bytes(loaded.model)
    request_id = f"prep-{sha256_bytes(normalized_bytes)}"
    preparation_run_id = str(uuid4())
    created_at = datetime.now(timezone.utc)
    layout = create_preparation_layout(
        Path(output_root),
        preparation_run_id=preparation_run_id,
        created_at=created_at,
    )
    try:
        result = _write_preparation_bundle(
            loaded=loaded,
            source_data=source_data,
            resolved=resolved,
            layout=layout,
            request_id=request_id,
            normalized_bytes=normalized_bytes,
            preparation_run_id=preparation_run_id,
            created_at=created_at,
        )
        finalize_preparation_layout(layout)
        return PreparationResult(
            preparation_request_id=result.preparation_request_id,
            preparation_context_id=result.preparation_context_id,
            preparation_run_id=preparation_run_id,
            status=result.status,
            output_directory=layout.final_directory,
            eligible_row_count=result.eligible_row_count,
            excluded_row_count=result.excluded_row_count,
            unsplit_path=(
                None
                if result.unsplit_path is None
                else layout.final_directory / "data" / "unsplit.parquet"
            ),
            exclusions_path=layout.final_directory / "data" / "exclusions.parquet",
            manifest_path=layout.final_directory / "manifest.json",
            diagnostics_path=layout.final_directory / "diagnostics.json",
            dataset_card_path=layout.final_directory / "dataset_card.md",
        )
    except Exception:
        # The staging directory is intentionally left in place only if cleanup itself fails;
        # source runs and sweep bundles are never modified.
        cleanup_staging(layout.staging_directory)
        raise


def _write_preparation_bundle(
    *,
    loaded: LoadedPreparationConfig,
    source_data: LoadedPreparationSource,
    resolved: ResolvedPreparation,
    layout: PreparationLayout,
    request_id: str,
    normalized_bytes: bytes,
    preparation_run_id: str,
    created_at: datetime,
) -> BundleWriteResult:
    data_directory = layout.staging_directory / "data"
    data_directory.mkdir()
    rows = build_prepared_rows(loaded.model, source_data, resolved)
    unsplit_path = _write_data_artifacts(rows, data_directory)

    write_bytes(layout.staging_directory / "preparation.original.yaml", loaded.raw_bytes)
    write_bytes(layout.staging_directory / "preparation.normalized.json", normalized_bytes)

    context_id = preparation_context_id(
        request_id=request_id,
        source_data=source_data,
        formats=loaded.model.outputs.formats,
    )
    artifact_names = [
        "preparation.original.yaml",
        "preparation.normalized.json",
        "data/exclusions.parquet",
    ]
    if unsplit_path is not None:
        artifact_names.append("data/unsplit.parquet")
    artifact_hashes = hash_artifacts(layout.staging_directory, artifact_names)
    manifest = build_manifest(
        loaded=loaded,
        source_data=source_data,
        resolved=resolved,
        categories=rows.categories,
        status=rows.status,
        request_id=request_id,
        context_id=context_id,
        preparation_run_id=preparation_run_id,
        created_at=created_at,
        eligible_row_count=len(rows.prepared_rows),
        excluded_row_count=len(rows.exclusion_rows),
        artifact_hashes=artifact_hashes,
    )
    write_json(layout.staging_directory / "manifest.json", manifest)
    diagnostics = build_diagnostics(source_data, rows.status, rows.exclusion_rows)
    write_json(layout.staging_directory / "diagnostics.json", diagnostics)
    _write_text(
        layout.staging_directory / "dataset_card.md",
        build_dataset_card(manifest, diagnostics),
    )
    final_hash_names = [*artifact_names, "diagnostics.json", "dataset_card.md"]
    manifest["artifact_hashes"] = hash_artifacts(layout.staging_directory, final_hash_names)
    write_json(layout.staging_directory / "manifest.json", manifest)
    return BundleWriteResult(
        preparation_request_id=request_id,
        preparation_context_id=context_id,
        status=rows.status,
        eligible_row_count=len(rows.prepared_rows),
        excluded_row_count=len(rows.exclusion_rows),
        unsplit_path=unsplit_path,
    )


def _write_data_artifacts(rows: PreparedRows, data_directory: Path) -> Path | None:
    unsplit_path: Path | None = None
    if rows.prepared_rows:
        unsplit_path = data_directory / "unsplit.parquet"
        _write_parquet(pd.DataFrame(rows.prepared_rows), unsplit_path)
    _write_parquet(exclusions_frame(rows.exclusion_rows), data_directory / "exclusions.parquet")
    return unsplit_path


def _write_parquet(frame: pd.DataFrame, path: Path) -> None:
    try:
        frame.to_parquet(path, index=False)
    except Exception as exc:
        raise OutputError(f"could not write preparation Parquet {path.name}: {exc}") from exc


def _write_text(path: Path, value: str) -> None:
    try:
        path.write_text(value, encoding="utf-8")
    except OSError as exc:
        raise OutputError(f"could not write {path.name}: {exc}") from exc
