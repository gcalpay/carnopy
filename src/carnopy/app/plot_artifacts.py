from __future__ import annotations

import errno
import hashlib
import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from carnopy.app.workspace import Workspace
from carnopy.visualization.requests import PlotRequest, request_id

VISUALIZATION_REPORT_SCHEMA_VERSION = 1
PLOT_SCHEMA_VERSION = 2
SUPPORTED_PLOT_FORMATS = frozenset({"png", "svg", "pdf"})


class PlotArtifactError(ValueError):
    """Recorded plot evidence is incomplete, inconsistent, or unsafe to use."""


@dataclass(frozen=True)
class VerifiedPlotArtifact:
    index: int
    name: str
    kind: str
    figures_root: Path
    image_path: Path
    sidecar_path: Path
    image_sha256: str
    image_format: str
    normalized_request: dict[str, object]
    visualization_request_id: str
    source_identity: dict[str, object]
    advisories: tuple[dict[str, object], ...]
    valid_sample_count: int
    excluded_sample_count: int


@dataclass(frozen=True)
class VerifiedPlotOutcome:
    index: int
    name: str
    kind: str
    status: str
    error_type: str
    error_message: str
    artifact: VerifiedPlotArtifact | None


@dataclass(frozen=True)
class VerifiedConfiguredPlotBundle:
    request_id: str
    run_id: str
    spec_id: str
    generation_context_id: str
    output_directory: Path
    figure_directory: Path
    report_path: Path
    visualization_request_id: str
    status: str
    outcomes: tuple[VerifiedPlotOutcome, ...]
    verification_revision: str


def verify_session_plot_result(
    workspace: Workspace,
    *,
    source_path: Path,
    inspection_revision: str,
    result: dict[str, Any],
) -> tuple[VerifiedPlotArtifact, str]:
    """Verify one worker-returned session plot before exposing it to a frontend."""

    if _required_path(result, "source", "plot result") != source_path.absolute():
        raise PlotArtifactError("plot result belongs to another inspected source")
    _require_equal_text(result, "inspection_revision", inspection_revision, "plot result")
    normalized = _required_mapping(result, "normalized_request", "plot result")
    try:
        request = PlotRequest.model_validate(normalized)
    except (TypeError, ValueError) as exc:
        raise PlotArtifactError(
            f"plot result contains an invalid normalized request: {exc}"
        ) from exc
    canonical_request = request.canonical_dict()
    if normalized != canonical_request:
        raise PlotArtifactError("plot result request is not canonical")
    image_path = _regular_path_within(
        workspace.figures,
        _required_path(result, "image_path", "plot result"),
        "session plot image",
    )
    sidecar_path = _regular_path_within(
        workspace.figures,
        _required_path(result, "sidecar_path", "plot result"),
        "session plot sidecar",
    )
    if sidecar_path != image_path.with_suffix(".plot.json"):
        raise PlotArtifactError("session plot image and sidecar names do not form a pair")
    sidecar_bytes = _read_stable_regular_bytes(
        workspace.figures,
        sidecar_path,
        "session plot sidecar",
    )
    _require_equal_text(
        result,
        "sidecar_sha256",
        hashlib.sha256(sidecar_bytes).hexdigest(),
        "plot result",
    )
    sidecar = _json_object(sidecar_bytes, "session plot sidecar")
    if sidecar.get("plot_schema_version") != PLOT_SCHEMA_VERSION:
        raise PlotArtifactError("session plot sidecar uses an unsupported schema")
    if sidecar.get("normalized_request") != canonical_request:
        raise PlotArtifactError("session plot sidecar request does not match the worker result")
    visualization_request_id = _required_text(
        result,
        "visualization_request_id",
        "plot result",
    )
    _require_equal_text(
        sidecar,
        "visualization_request_id",
        visualization_request_id,
        "session plot sidecar",
    )
    if request_id((request,)) != visualization_request_id:
        raise PlotArtifactError("session plot visualization identity is inconsistent")
    source_identity = _required_mapping(sidecar, "source_identity", "session plot sidecar")
    if (
        _required_path(
            source_identity,
            "requested_path",
            "session plot sidecar",
        )
        != source_path.absolute()
    ):
        raise PlotArtifactError("session plot sidecar belongs to another inspected source")
    image = _required_mapping(sidecar, "image", "session plot sidecar")
    if _required_path(image, "path", "session plot sidecar") != image_path:
        raise PlotArtifactError("session plot sidecar records another image path")
    if _required_path(image, "sidecar_path", "session plot sidecar") != sidecar_path:
        raise PlotArtifactError("session plot sidecar records another sidecar path")
    image_format = _required_text(image, "format", "session plot sidecar").casefold()
    _require_equal_text(result, "format", image_format, "plot result")
    _require_equal_text(result, "kind", request.kind, "plot result")
    image_sha256 = _sha256_text(
        _required_text(image, "sha256", "session plot sidecar"),
        "session plot image",
    )
    _require_equal_text(result, "image_sha256", image_sha256, "plot result")
    valid_sample_count = _required_nonnegative_int(
        sidecar.get("valid_sample_count"),
        "session plot sidecar valid_sample_count",
    )
    excluded_sample_count = _required_nonnegative_int(
        sidecar.get("excluded_sample_count"),
        "session plot sidecar excluded_sample_count",
    )
    if result.get("valid_rows_plotted") != valid_sample_count:
        raise PlotArtifactError("plot result valid-row count does not match its sidecar")
    if result.get("invalid_rows_excluded") != excluded_sample_count:
        raise PlotArtifactError("plot result excluded-row count does not match its sidecar")
    validated_plot_bytes(workspace.figures, image_path, image_format, image_sha256)
    verification = hashlib.sha256(sidecar_bytes)
    verification.update(image_sha256.encode("ascii"))
    artifact = VerifiedPlotArtifact(
        index=0,
        name=str(request.name),
        kind=request.kind,
        figures_root=workspace.figures,
        image_path=image_path,
        sidecar_path=sidecar_path,
        image_sha256=image_sha256,
        image_format=image_format,
        normalized_request=canonical_request,
        visualization_request_id=visualization_request_id,
        source_identity=dict(source_identity),
        advisories=_mapping_tuple(sidecar.get("advisories")),
        valid_sample_count=valid_sample_count,
        excluded_sample_count=excluded_sample_count,
    )
    return artifact, verification.hexdigest()


def verify_configured_plot_record(
    workspace: Workspace,
    record: dict[str, Any],
) -> VerifiedConfiguredPlotBundle:
    """Verify one successful generation record and its exact configured outcomes."""

    if record.get("job_schema_version") != 1:
        raise PlotArtifactError("activity record uses an unsupported schema")
    if record.get("operation") != "generate" or record.get("status") != "completed":
        raise PlotArtifactError("activity record is not a completed generation")
    record_id = _required_text(record, "request_id", "activity record")
    summary = _required_mapping(record, "summary", "activity record")
    visualization = _required_mapping(summary, "visualization", "generation result")
    output_directory = _direct_child(
        workspace.outputs,
        _required_path(summary, "output_directory", "generation result"),
        "generation output directory",
        require_directory=True,
    )
    figure_directory = _direct_child(
        workspace.figures,
        _required_path(visualization, "figure_directory", "visualization result"),
        "configured figure directory",
        require_directory=True,
    )
    report_path = _regular_path_within(
        figure_directory,
        _required_path(visualization, "report_path", "visualization result"),
        "visualization report",
    )
    if report_path.parent != figure_directory:
        raise PlotArtifactError("visualization report is not a direct figure-directory child")

    report_bytes = _read_stable_regular_bytes(
        figure_directory,
        report_path,
        "visualization report",
    )
    report = _json_object(report_bytes, "visualization report")
    if report.get("visualization_report_schema_version") != VISUALIZATION_REPORT_SCHEMA_VERSION:
        raise PlotArtifactError("visualization report uses an unsupported schema")

    run_id = _required_text(summary, "run_id", "generation result")
    spec_id = _required_text(summary, "spec_id", "generation result")
    generation_context_id = _required_text(
        summary,
        "generation_context_id",
        "generation result",
    )
    source_identity = _required_mapping(report, "source_identity", "visualization report")
    _require_equal_text(source_identity, "run_id", run_id, "visualization report")
    _require_equal_text(source_identity, "spec_id", spec_id, "visualization report")
    _require_equal_text(
        source_identity,
        "generation_context_id",
        generation_context_id,
        "visualization report",
    )
    report_source = _required_path(source_identity, "run_directory", "visualization report")
    if report_source.absolute() != output_directory:
        raise PlotArtifactError("visualization report belongs to another run directory")

    normalized = _required_mapping(
        report,
        "normalized_visualization",
        "visualization report",
    )
    raw_plots = normalized.get("plots")
    if not isinstance(raw_plots, list):
        raise PlotArtifactError("visualization report does not contain an ordered plot list")
    try:
        requests = tuple(PlotRequest.model_validate(item) for item in raw_plots)
    except (TypeError, ValueError) as exc:
        raise PlotArtifactError(f"visualization report contains an invalid request: {exc}") from exc
    names = tuple(request.name for request in requests)
    if any(name is None for name in names) or len(set(names)) != len(names):
        raise PlotArtifactError("visualization report plot names are missing or not unique")
    visualization_request_id = request_id(requests)
    _require_equal_text(
        report,
        "visualization_request_id",
        visualization_request_id,
        "visualization report",
    )
    _require_equal_text(
        normalized,
        "visualization_request_id",
        visualization_request_id,
        "normalized visualization",
    )
    _require_equal_text(
        visualization,
        "visualization_request_id",
        visualization_request_id,
        "generation result",
    )
    report_status = _required_text(report, "status", "visualization report")
    _require_equal_text(visualization, "status", report_status, "generation result")

    raw_outcomes = report.get("outcomes")
    if not isinstance(raw_outcomes, list) or len(raw_outcomes) != len(requests):
        raise PlotArtifactError("visualization report outcomes do not match its requests")
    if report.get("requested_plot_count") != len(requests):
        raise PlotArtifactError("visualization report plot count is inconsistent")

    outcomes: list[VerifiedPlotOutcome] = []
    completed = failed = skipped = 0
    verification = hashlib.sha256(report_bytes)
    for index, (request, raw_outcome) in enumerate(zip(requests, raw_outcomes, strict=True)):
        if not isinstance(raw_outcome, dict):
            raise PlotArtifactError(f"visualization outcome {index + 1} is not an object")
        name = _required_text(raw_outcome, "name", f"visualization outcome {index + 1}")
        kind = _required_text(raw_outcome, "kind", f"visualization outcome {index + 1}")
        if name != request.name or kind != request.kind:
            raise PlotArtifactError(
                f"visualization outcome {index + 1} does not match its ordered request"
            )
        status = _required_text(raw_outcome, "status", f"visualization outcome {index + 1}")
        artifact: VerifiedPlotArtifact | None = None
        error_type = ""
        error_message = ""
        if status == "completed":
            completed += 1
            artifact, sidecar_bytes = _verify_completed_outcome(
                index=index,
                workspace=workspace,
                output_directory=output_directory,
                figure_directory=figure_directory,
                run_id=run_id,
                spec_id=spec_id,
                generation_context_id=generation_context_id,
                visualization_request_id=visualization_request_id,
                request=request,
                outcome=raw_outcome,
            )
            verification.update(sidecar_bytes)
            verification.update(artifact.image_sha256.encode("ascii"))
        elif status == "failed":
            failed += 1
            error_type = _required_text(
                raw_outcome,
                "error_type",
                f"visualization outcome {index + 1}",
            )
            error_message = _required_text(
                raw_outcome,
                "error_message",
                f"visualization outcome {index + 1}",
            )
        elif status == "skipped":
            skipped += 1
            error_message = _required_text(
                raw_outcome,
                "reason",
                f"visualization outcome {index + 1}",
            )
        else:
            raise PlotArtifactError(
                f"visualization outcome {index + 1} has unsupported status {status!r}"
            )
        outcomes.append(
            VerifiedPlotOutcome(
                index=index,
                name=name,
                kind=kind,
                status=status,
                error_type=error_type,
                error_message=error_message,
                artifact=artifact,
            )
        )

    for field, expected in (
        ("requested_plot_count", len(requests)),
        ("succeeded_plot_count", completed),
        ("failed_plot_count", failed),
        ("skipped_plot_count", skipped),
    ):
        if report.get(field) != expected:
            raise PlotArtifactError(f"visualization report {field} is inconsistent")
        if visualization.get(field) != expected:
            raise PlotArtifactError(f"generation result {field} is inconsistent")

    return VerifiedConfiguredPlotBundle(
        request_id=record_id,
        run_id=run_id,
        spec_id=spec_id,
        generation_context_id=generation_context_id,
        output_directory=output_directory,
        figure_directory=figure_directory,
        report_path=report_path,
        visualization_request_id=visualization_request_id,
        status=report_status,
        outcomes=tuple(outcomes),
        verification_revision=verification.hexdigest(),
    )


def validated_plot_bytes(
    figures_root: Path,
    image_path: Path,
    image_format: str,
    expected_sha256: str,
) -> bytes:
    normalized_format = image_format.casefold()
    if normalized_format not in SUPPORTED_PLOT_FORMATS:
        raise PlotArtifactError(f"unsupported plot format: {image_format}")
    if image_path.suffix.casefold() != f".{normalized_format}":
        raise PlotArtifactError("plot suffix does not match its recorded format")
    digest = _sha256_text(expected_sha256, "plot image")
    data = _read_stable_regular_bytes(figures_root, image_path, "plot image")
    if hashlib.sha256(data).hexdigest() != digest:
        raise PlotArtifactError("plot image SHA-256 does not match its sidecar")
    return data


def export_verified_plot_bundle(
    artifact: VerifiedPlotArtifact,
    destination_image: Path,
) -> tuple[Path, Path]:
    """Export one reverified image/sidecar pair without overwriting either path."""

    image_bytes = validated_plot_bytes(
        artifact.figures_root,
        artifact.image_path,
        artifact.image_format,
        artifact.image_sha256,
    )
    sidecar_bytes = _read_stable_regular_bytes(
        artifact.figures_root,
        artifact.sidecar_path,
        "plot sidecar",
    )
    sidecar = _json_object(sidecar_bytes, "plot sidecar")
    _validate_sidecar_against_artifact(sidecar, artifact)

    final_image = destination_image.expanduser().resolve(strict=False)
    if final_image.suffix.casefold() != f".{artifact.image_format}":
        raise PlotArtifactError(
            f"export destination must use .{artifact.image_format} for this plot"
        )
    parent = final_image.parent
    try:
        parent_info = parent.lstat()
    except OSError as exc:
        raise PlotArtifactError(f"export directory is unavailable: {parent}") from exc
    if stat.S_ISLNK(parent_info.st_mode) or not stat.S_ISDIR(parent_info.st_mode):
        raise PlotArtifactError("export destination parent must be a regular directory")
    final_sidecar = final_image.with_suffix(".plot.json")
    existing = next(
        (path for path in (final_image, final_sidecar) if os.path.lexists(path)),
        None,
    )
    if existing is not None:
        raise PlotArtifactError(f"refusing to overwrite existing plot artifact: {existing}")

    rewritten = json.loads(json.dumps(sidecar))
    image = rewritten.get("image")
    if not isinstance(image, dict):
        raise PlotArtifactError("plot sidecar image record is invalid")
    image["path"] = str(final_image)
    image["sidecar_path"] = str(final_sidecar)
    rewritten_bytes = (
        json.dumps(rewritten, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")

    token = uuid4().hex
    staged_image = parent / f".{final_image.name}.{token}.tmp"
    staged_sidecar = parent / f".{final_sidecar.name}.{token}.tmp"
    linked_image = False
    linked_sidecar = False
    try:
        _write_exclusive(staged_image, image_bytes)
        _write_exclusive(staged_sidecar, rewritten_bytes)
        if hashlib.sha256(staged_image.read_bytes()).hexdigest() != artifact.image_sha256:
            raise PlotArtifactError("staged plot image changed during export")
        os.link(staged_image, final_image)
        linked_image = True
        os.link(staged_sidecar, final_sidecar)
        linked_sidecar = True
    except PlotArtifactError:
        if linked_sidecar:
            _unlink_if_same_file(final_sidecar, staged_sidecar)
        if linked_image:
            _unlink_if_same_file(final_image, staged_image)
        raise
    except OSError as exc:
        if linked_sidecar:
            _unlink_if_same_file(final_sidecar, staged_sidecar)
        if linked_image:
            _unlink_if_same_file(final_image, staged_image)
        if exc.errno in {errno.ENOTSUP, errno.EOPNOTSUPP, errno.EPERM, errno.EXDEV}:
            raise PlotArtifactError(
                "plot export requires same-filesystem hard-link support; "
                f"could not promote staged artifacts: {exc}"
            ) from exc
        raise PlotArtifactError(f"could not export plot artifacts: {exc}") from exc
    finally:
        _unlink_staged(staged_sidecar)
        _unlink_staged(staged_image)
    return final_image, final_sidecar


def _verify_completed_outcome(
    *,
    index: int,
    workspace: Workspace,
    output_directory: Path,
    figure_directory: Path,
    run_id: str,
    spec_id: str,
    generation_context_id: str,
    visualization_request_id: str,
    request: PlotRequest,
    outcome: dict[str, Any],
) -> tuple[VerifiedPlotArtifact, bytes]:
    image_path = _regular_path_within(
        figure_directory,
        _required_path(outcome, "image_path", f"visualization outcome {index + 1}"),
        "configured plot image",
    )
    sidecar_path = _regular_path_within(
        figure_directory,
        _required_path(outcome, "sidecar_path", f"visualization outcome {index + 1}"),
        "configured plot sidecar",
    )
    if image_path.parent != figure_directory or sidecar_path.parent != figure_directory:
        raise PlotArtifactError("configured plot artifacts are not direct figure children")
    if sidecar_path != image_path.with_suffix(".plot.json"):
        raise PlotArtifactError("configured plot image and sidecar names do not form a pair")
    sidecar_bytes = _read_stable_regular_bytes(
        figure_directory,
        sidecar_path,
        "configured plot sidecar",
    )
    sidecar = _json_object(sidecar_bytes, "configured plot sidecar")
    if sidecar.get("plot_schema_version") != PLOT_SCHEMA_VERSION:
        raise PlotArtifactError("configured plot sidecar uses an unsupported schema")
    if sidecar.get("plot_kind") != request.kind:
        raise PlotArtifactError("configured plot sidecar kind does not match its request")
    canonical_request = request.canonical_dict()
    if sidecar.get("normalized_request") != canonical_request:
        raise PlotArtifactError("configured plot sidecar request does not match its report")
    _require_equal_text(
        sidecar,
        "visualization_request_id",
        visualization_request_id,
        "configured plot sidecar",
    )
    source_identity = _required_mapping(sidecar, "source_identity", "configured plot sidecar")
    _require_equal_text(source_identity, "run_id", run_id, "configured plot sidecar")
    _require_equal_text(source_identity, "spec_id", spec_id, "configured plot sidecar")
    _require_equal_text(
        source_identity,
        "generation_context_id",
        generation_context_id,
        "configured plot sidecar",
    )
    requested_path = _required_path(
        source_identity,
        "requested_path",
        "configured plot sidecar",
    )
    if requested_path.absolute() != output_directory:
        raise PlotArtifactError("configured plot sidecar belongs to another run directory")
    dataset_path = _regular_path_within(
        output_directory,
        _required_path(source_identity, "dataset_path", "configured plot sidecar"),
        "configured plot source dataset",
    )
    if dataset_path.parent != output_directory or dataset_path.suffix.casefold() not in {
        ".csv",
        ".parquet",
    }:
        raise PlotArtifactError("configured plot source dataset is not a run dataset artifact")
    _sha256_text(
        _required_text(
            source_identity,
            "dataset_sha256",
            "configured plot sidecar",
        ),
        "configured plot source dataset",
    )

    image = _required_mapping(sidecar, "image", "configured plot sidecar")
    if _required_path(image, "path", "configured plot sidecar").absolute() != image_path:
        raise PlotArtifactError("configured plot sidecar records another image path")
    if _required_path(image, "sidecar_path", "configured plot sidecar").absolute() != sidecar_path:
        raise PlotArtifactError("configured plot sidecar records another sidecar path")
    image_format = _required_text(image, "format", "configured plot sidecar").casefold()
    image_sha256 = _sha256_text(
        _required_text(image, "sha256", "configured plot sidecar"),
        "configured plot image",
    )
    validated_plot_bytes(workspace.figures, image_path, image_format, image_sha256)
    advisories = _mapping_tuple(sidecar.get("advisories"))
    valid_sample_count = _required_nonnegative_int(
        sidecar.get("valid_sample_count"),
        "configured plot sidecar valid_sample_count",
    )
    excluded_sample_count = _required_nonnegative_int(
        sidecar.get("excluded_sample_count"),
        "configured plot sidecar excluded_sample_count",
    )
    if outcome.get("valid_sample_count") != valid_sample_count:
        raise PlotArtifactError(
            "configured plot outcome valid-sample count does not match its sidecar"
        )
    if outcome.get("excluded_sample_count") != excluded_sample_count:
        raise PlotArtifactError(
            "configured plot outcome excluded-sample count does not match its sidecar"
        )
    if outcome.get("advisories") != list(advisories):
        raise PlotArtifactError("configured plot outcome advisories do not match its sidecar")
    return (
        VerifiedPlotArtifact(
            index=index,
            name=str(request.name),
            kind=request.kind,
            figures_root=workspace.figures,
            image_path=image_path,
            sidecar_path=sidecar_path,
            image_sha256=image_sha256,
            image_format=image_format,
            normalized_request=canonical_request,
            visualization_request_id=visualization_request_id,
            source_identity=dict(source_identity),
            advisories=advisories,
            valid_sample_count=valid_sample_count,
            excluded_sample_count=excluded_sample_count,
        ),
        sidecar_bytes,
    )


def _validate_sidecar_against_artifact(
    sidecar: dict[str, Any],
    artifact: VerifiedPlotArtifact,
) -> None:
    if sidecar.get("plot_schema_version") != PLOT_SCHEMA_VERSION:
        raise PlotArtifactError("plot sidecar uses an unsupported schema")
    if sidecar.get("plot_kind") != artifact.kind:
        raise PlotArtifactError("plot sidecar kind changed after verification")
    if sidecar.get("normalized_request") != artifact.normalized_request:
        raise PlotArtifactError("plot sidecar request changed after verification")
    if sidecar.get("visualization_request_id") != artifact.visualization_request_id:
        raise PlotArtifactError("plot sidecar visualization identity changed after verification")
    if sidecar.get("source_identity") != artifact.source_identity:
        raise PlotArtifactError("plot sidecar source identity changed after verification")
    image = _required_mapping(sidecar, "image", "plot sidecar")
    if _required_path(image, "path", "plot sidecar").absolute() != artifact.image_path:
        raise PlotArtifactError("plot sidecar image path changed after verification")
    if _required_path(image, "sidecar_path", "plot sidecar").absolute() != artifact.sidecar_path:
        raise PlotArtifactError("plot sidecar path changed after verification")
    if image.get("sha256") != artifact.image_sha256:
        raise PlotArtifactError("plot sidecar image hash changed after verification")
    if str(image.get("format", "")).casefold() != artifact.image_format:
        raise PlotArtifactError("plot sidecar image format changed after verification")


def _required_mapping(
    value: dict[str, Any] | dict[str, object],
    key: str,
    source: str,
) -> dict[str, Any]:
    candidate = value.get(key)
    if not isinstance(candidate, dict):
        raise PlotArtifactError(f"{source} is missing {key}")
    return candidate


def _required_text(value: dict[str, Any], key: str, source: str) -> str:
    candidate = value.get(key)
    if not isinstance(candidate, str) or not candidate:
        raise PlotArtifactError(f"{source} is missing {key}")
    return candidate


def _required_path(value: dict[str, Any], key: str, source: str) -> Path:
    return Path(_required_text(value, key, source)).expanduser().absolute()


def _require_equal_text(
    value: dict[str, Any],
    key: str,
    expected: str,
    source: str,
) -> None:
    if _required_text(value, key, source) != expected:
        raise PlotArtifactError(f"{source} {key} does not match its generation record")


def _direct_child(
    root: Path,
    path: Path,
    label: str,
    *,
    require_directory: bool,
) -> Path:
    root_path = _regular_directory(root, f"workspace {root.name} directory")
    candidate = path.absolute()
    if candidate.parent != root_path:
        raise PlotArtifactError(f"{label} is not a direct workspace child")
    try:
        info = candidate.lstat()
    except OSError as exc:
        raise PlotArtifactError(f"{label} is unavailable: {candidate}") from exc
    expected = stat.S_ISDIR(info.st_mode) if require_directory else stat.S_ISREG(info.st_mode)
    if stat.S_ISLNK(info.st_mode) or not expected:
        raise PlotArtifactError(f"{label} is not a regular filesystem object")
    if candidate.resolve(strict=True).parent != root_path.resolve(strict=True):
        raise PlotArtifactError(f"{label} escapes its workspace root")
    return candidate


def _regular_directory(path: Path, label: str) -> Path:
    candidate = path.absolute()
    try:
        info = candidate.lstat()
    except OSError as exc:
        raise PlotArtifactError(f"{label} is unavailable: {candidate}") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise PlotArtifactError(f"{label} must be a regular directory")
    return candidate


def _regular_path_within(root: Path, path: Path, label: str) -> Path:
    root_path = _regular_directory(root, f"{label} root")
    candidate = path.absolute()
    try:
        relative = candidate.relative_to(root_path)
    except ValueError as exc:
        raise PlotArtifactError(f"{label} is outside its expected root") from exc
    if not relative.parts:
        raise PlotArtifactError(f"{label} does not identify a file")
    current = root_path
    for index, part in enumerate(relative.parts):
        current /= part
        try:
            info = current.lstat()
        except OSError as exc:
            raise PlotArtifactError(f"{label} is unavailable: {current}") from exc
        if stat.S_ISLNK(info.st_mode):
            raise PlotArtifactError(f"{label} path must not contain symbolic links")
        if index < len(relative.parts) - 1 and not stat.S_ISDIR(info.st_mode):
            raise PlotArtifactError(f"{label} parent is not a directory")
        if index == len(relative.parts) - 1 and not stat.S_ISREG(info.st_mode):
            raise PlotArtifactError(f"{label} is not a regular file")
    if not candidate.resolve(strict=True).is_relative_to(root_path.resolve(strict=True)):
        raise PlotArtifactError(f"{label} escapes its expected root")
    return candidate


def _read_stable_regular_bytes(root: Path, path: Path, label: str) -> bytes:
    candidate = _regular_path_within(root, path, label)
    try:
        before = candidate.lstat()
        data = candidate.read_bytes()
        after = candidate.lstat()
    except OSError as exc:
        raise PlotArtifactError(f"{label} could not be read: {candidate}") from exc
    if stat.S_ISLNK(after.st_mode) or (before.st_dev, before.st_ino) != (
        after.st_dev,
        after.st_ino,
    ):
        raise PlotArtifactError(f"{label} changed while it was being read")
    return data


def _json_object(data: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise PlotArtifactError(f"{label} is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise PlotArtifactError(f"{label} root is not an object")
    return value


def _sha256_text(value: str, label: str) -> str:
    normalized = value.casefold()
    if len(normalized) != 64 or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        raise PlotArtifactError(f"{label} SHA-256 is invalid")
    return normalized


def _mapping_tuple(value: object) -> tuple[dict[str, object], ...]:
    if not isinstance(value, list):
        return ()
    return tuple(dict(item) for item in value if isinstance(item, dict))


def _required_nonnegative_int(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise PlotArtifactError(f"{label} is missing or invalid")
    return value


def _write_exclusive(path: Path, data: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        path.unlink(missing_ok=True)
        raise


def _unlink_if_same_file(final_path: Path, staged_path: Path) -> None:
    try:
        final = final_path.lstat()
        staged = staged_path.lstat()
    except OSError:
        return
    if (final.st_dev, final.st_ino) != (staged.st_dev, staged.st_ino):
        return
    try:
        final_path.unlink()
    except OSError:
        return


def _unlink_staged(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        return
