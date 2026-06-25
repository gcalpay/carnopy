from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import pandas as pd

from carnopy.visualization.inspect import PlotInspection, inspect_plot_source
from carnopy.visualization.models import VisualizationError

INSPECTION_SCHEMA_VERSION = 1


class Inspection(Protocol):
    def format_json(self) -> str: ...

    def format_text(self) -> str: ...


@dataclass(frozen=True)
class PreparationInspection:
    source: Path
    manifest: dict[str, Any]
    diagnostics: dict[str, Any]
    table_path: Path | None
    provenance_path: Path
    diagnostics_table_path: Path
    exclusions_path: Path
    table_columns: tuple[str, ...]
    provenance_columns: tuple[str, ...]
    diagnostics_columns: tuple[str, ...]
    exclusions_columns: tuple[str, ...]
    scenario_summary: dict[str, Any] | None
    reference_state: dict[str, Any] | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "inspection_schema_version": INSPECTION_SCHEMA_VERSION,
            "source_kind": "preparation_bundle",
            "source": str(self.source),
            "status": self.manifest.get("status"),
            "row_counts": {
                "eligible": self.manifest.get("eligible_row_count"),
                "excluded": self.manifest.get("excluded_row_count"),
                "source": self.diagnostics.get("source_row_count"),
            },
            "artifacts": {
                "table": None if self.table_path is None else str(self.table_path),
                "provenance": str(self.provenance_path),
                "diagnostics": str(self.diagnostics_table_path),
                "exclusions": str(self.exclusions_path),
            },
            "columns": {
                "table": list(self.table_columns),
                "provenance": list(self.provenance_columns),
                "diagnostics": list(self.diagnostics_columns),
                "exclusions": list(self.exclusions_columns),
            },
            "features": self.manifest.get("features"),
            "targets": self.manifest.get("targets"),
            "auxiliary": self.manifest.get("auxiliary"),
            "categorical_vocabularies": self.manifest.get("categorical_vocabularies"),
            "scenarios": self.scenario_summary,
            "source_identity": self.manifest.get("source"),
            "source_artifacts": self.manifest.get("source_artifacts"),
            "artifact_hashes": self.manifest.get("artifact_hashes"),
            "reference_state": self.reference_state,
        }

    def format_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True, ensure_ascii=False)

    def format_text(self) -> str:
        lines = [
            f"Source: {self.source}",
            "Source kind: preparation bundle",
            f"Status: {self.manifest.get('status', 'unreported')}",
            (
                f"Rows: {self.manifest.get('eligible_row_count', 'unreported')} eligible, "
                f"{self.manifest.get('excluded_row_count', 'unreported')} excluded"
            ),
            "Artifacts:",
            f"  table: {self.table_path or 'absent'}",
            f"  provenance: {self.provenance_path}",
            f"  diagnostics: {self.diagnostics_table_path}",
            f"  exclusions: {self.exclusions_path}",
            "Columns:",
            f"  table: {', '.join(self.table_columns) or 'none'}",
            f"  provenance: {', '.join(self.provenance_columns) or 'none'}",
            f"  diagnostics: {', '.join(self.diagnostics_columns) or 'none'}",
            "Features:",
            f"  numeric: {', '.join(self._feature_list('numeric')) or 'none'}",
            f"  derived: {', '.join(self._feature_list('derived')) or 'none'}",
            f"  categorical: {', '.join(self._categorical_fields()) or 'none'}",
            "Targets: " + (", ".join(self._string_list(self.manifest.get("targets"))) or "none"),
            "Auxiliary: "
            + (", ".join(self._string_list(self.manifest.get("auxiliary"))) or "none"),
        ]
        if isinstance(self.reference_state, dict):
            selected = self.reference_state.get("selected_reference_dependent_fields")
            if isinstance(selected, list) and selected:
                lines.extend(
                    [
                        "Reference state:",
                        "  selected reference-dependent fields: "
                        + ", ".join(str(item) for item in selected),
                    ]
                )
        scenarios = self.scenario_summary
        if isinstance(scenarios, dict):
            lines.extend(
                [
                    "Scenarios:",
                    f"  count: {scenarios.get('scenario_count', 0)}",
                    f"  partitions: {scenarios.get('partition_count', 0)}",
                ]
            )
            for scenario in scenarios.get("scenarios", []):
                if isinstance(scenario, dict):
                    lines.append(
                        "  "
                        + str(scenario.get("name"))
                        + ": "
                        + json.dumps(scenario.get("partition_counts", {}), sort_keys=True)
                    )
        return "\n".join(lines)

    def _feature_list(self, key: str) -> list[str]:
        features = self.manifest.get("features")
        if not isinstance(features, dict):
            return []
        return self._string_list(features.get(key))

    def _categorical_fields(self) -> list[str]:
        features = self.manifest.get("features")
        if not isinstance(features, dict):
            return []
        categorical = features.get("categorical")
        if not isinstance(categorical, list):
            return []
        return [
            str(item.get("field"))
            for item in categorical
            if isinstance(item, dict) and isinstance(item.get("field"), str)
        ]

    @staticmethod
    def _string_list(value: object) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item) for item in value]


@dataclass(frozen=True)
class SweepInspection:
    source: Path
    metadata: dict[str, Any]
    report: dict[str, Any]
    child_directories: tuple[str, ...]
    values_path: Path | None
    deltas_path: Path | None
    values_row_count: int | None
    deltas_row_count: int | None
    delta_summaries: tuple[dict[str, Any], ...]
    delta_reason_counts: dict[str, int]
    comparison_plots_configured: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "inspection_schema_version": INSPECTION_SCHEMA_VERSION,
            "source_kind": "model_sweep_bundle",
            "source": str(self.source),
            "sweep_id": self.metadata.get("sweep_id"),
            "sweep_run_id": self.metadata.get("sweep_run_id"),
            "status": self.metadata.get("sweep_status"),
            "mode": self.metadata.get("mode"),
            "models": self.metadata.get("models"),
            "reference_model": self.metadata.get("reference_model"),
            "child_directories": list(self.child_directories),
            "comparison_artifacts": {
                "values": None if self.values_path is None else str(self.values_path),
                "deltas": None if self.deltas_path is None else str(self.deltas_path),
                "values_row_count": self.values_row_count,
                "deltas_row_count": self.deltas_row_count,
            },
            "delta_summaries": list(self.delta_summaries),
            "delta_reason_counts": self.delta_reason_counts,
            "comparison_plots_configured": self.comparison_plots_configured,
            "comparison_plot_snippet": _comparison_plot_snippet(),
            "artifact_hashes": self.metadata.get("artifact_hashes"),
            "failure_message": self.metadata.get("failure_message")
            or self.report.get("failure_message"),
        }

    def format_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True, ensure_ascii=False)

    def format_text(self) -> str:
        lines = [
            f"Source: {self.source}",
            "Source kind: model-sweep bundle",
            f"Sweep status: {self.metadata.get('sweep_status', 'unreported')}",
            f"Mode: {self.metadata.get('mode', 'unreported')}",
            "Models: " + ", ".join(self._models()),
            f"Reference model: {self.metadata.get('reference_model', 'unreported')}",
            "Child runs:",
            *(f"  {path}" for path in self.child_directories),
            "Comparison artifacts:",
            f"  values: {self.values_path or 'absent'}"
            + ("" if self.values_row_count is None else f" ({self.values_row_count} rows)"),
            f"  deltas: {self.deltas_path or 'absent'}"
            + ("" if self.deltas_row_count is None else f" ({self.deltas_row_count} rows)"),
            "Relative delta summaries:",
        ]
        if self.delta_summaries:
            lines.extend(
                "  {backend_model} {property}: min={minimum:.6g}, max={maximum:.6g}, "
                "mean={mean:.6g}, count={count}".format(**summary)
                for summary in self.delta_summaries
            )
        else:
            lines.append("  none")
        if self.delta_reason_counts:
            lines.append("Delta unavailable reasons:")
            lines.extend(
                f"  {reason}: {count}" for reason, count in sorted(self.delta_reason_counts.items())
            )
        lines.extend(
            [
                "Comparison plots configured: "
                + ("yes" if self.comparison_plots_configured else "no"),
                "Comparison plot YAML snippet:",
                *_indent(_comparison_plot_snippet().splitlines(), prefix="  "),
            ]
        )
        return "\n".join(lines)

    def _models(self) -> list[str]:
        models = self.metadata.get("models")
        if isinstance(models, list):
            return [str(model) for model in models]
        return []


def inspect_source(source: str | Path) -> Inspection | PlotInspection:
    path = Path(source).expanduser()
    if path.is_dir() and (path / "preparation.normalized.json").is_file():
        return _inspect_preparation_bundle(path)
    if path.is_dir() and (path / "sweep.normalized.json").is_file():
        return _inspect_sweep_bundle(path)
    return inspect_plot_source(path)


def _inspect_preparation_bundle(path: Path) -> PreparationInspection:
    manifest = _read_json(path / "manifest.json", "preparation manifest")
    diagnostics = _read_json(path / "diagnostics.json", "preparation diagnostics")
    artifacts = manifest.get("data_artifacts")
    if not isinstance(artifacts, dict):
        raise VisualizationError("preparation manifest does not contain data_artifacts")
    table_path = _optional_artifact_path(path, artifacts.get("table"))
    provenance_path = _required_artifact_path(path, artifacts.get("provenance"), "provenance")
    diagnostics_path = _required_artifact_path(path, artifacts.get("diagnostics"), "diagnostics")
    exclusions_path = _required_artifact_path(path, artifacts.get("exclusions"), "exclusions")
    return PreparationInspection(
        source=path,
        manifest=manifest,
        diagnostics=diagnostics,
        table_path=table_path,
        provenance_path=provenance_path,
        diagnostics_table_path=diagnostics_path,
        exclusions_path=exclusions_path,
        table_columns=() if table_path is None else _parquet_columns(table_path),
        provenance_columns=_parquet_columns(provenance_path),
        diagnostics_columns=_parquet_columns(diagnostics_path),
        exclusions_columns=_parquet_columns(exclusions_path),
        scenario_summary=(
            manifest.get("scenarios") if isinstance(manifest.get("scenarios"), dict) else None
        ),
        reference_state=(
            manifest.get("reference_state")
            if isinstance(manifest.get("reference_state"), dict)
            else None
        ),
    )


def _inspect_sweep_bundle(path: Path) -> SweepInspection:
    metadata = _read_json(path / "metadata.json", "sweep metadata")
    report = _read_json(path / "report.json", "sweep report")
    child_directories = tuple(_child_directories(metadata))
    values_path = path / "comparison" / "values.parquet"
    deltas_path = path / "comparison" / "deltas.parquet"
    values = _optional_parquet(values_path)
    deltas = _optional_parquet(deltas_path)
    return SweepInspection(
        source=path,
        metadata=metadata,
        report=report,
        child_directories=child_directories,
        values_path=values_path if values_path.is_file() else None,
        deltas_path=deltas_path if deltas_path.is_file() else None,
        values_row_count=None if values is None else len(values),
        deltas_row_count=None if deltas is None else len(deltas),
        delta_summaries=_delta_summaries(deltas),
        delta_reason_counts=_delta_reason_counts(deltas),
        comparison_plots_configured=metadata.get("comparison_plots") is not None,
    )


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VisualizationError(f"could not read {label} {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise VisualizationError(f"{label} root must be an object")
    return payload


def _optional_artifact_path(root: Path, value: object) -> Path | None:
    if value is None:
        return None
    return _required_artifact_path(root, value, "artifact")


def _required_artifact_path(root: Path, value: object, label: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise VisualizationError(f"preparation manifest is missing {label} artifact")
    path = root / value
    if not path.is_file():
        raise VisualizationError(f"preparation {label} artifact is missing: {path}")
    return path


def _parquet_columns(path: Path) -> tuple[str, ...]:
    try:
        frame = pd.read_parquet(path)
    except Exception as exc:
        raise VisualizationError(f"could not inspect Parquet artifact {path}: {exc}") from exc
    return tuple(str(column) for column in frame.columns)


def _optional_parquet(path: Path) -> pd.DataFrame | None:
    if not path.is_file():
        return None
    try:
        return pd.read_parquet(path)
    except Exception as exc:
        raise VisualizationError(f"could not inspect Parquet artifact {path}: {exc}") from exc


def _child_directories(metadata: dict[str, Any]) -> list[str]:
    child_runs = metadata.get("child_runs")
    if not isinstance(child_runs, list):
        return []
    result: list[str] = []
    for child in child_runs:
        if isinstance(child, dict) and isinstance(child.get("output_directory"), str):
            result.append(str(child["output_directory"]))
    return result


def _delta_summaries(deltas: pd.DataFrame | None) -> tuple[dict[str, Any], ...]:
    if deltas is None or deltas.empty or "signed_relative_difference" not in deltas:
        return ()
    finite = deltas.loc[deltas["signed_relative_difference"].notna()].copy()
    if finite.empty:
        return ()
    rows: list[dict[str, Any]] = []
    grouped = finite.groupby(["backend_model", "property"], dropna=False)
    for (model, property_name), group in grouped:
        values = pd.to_numeric(group["signed_relative_difference"], errors="coerce").dropna()
        if values.empty:
            continue
        rows.append(
            {
                "backend_model": str(model),
                "property": str(property_name),
                "minimum": float(values.min()),
                "maximum": float(values.max()),
                "mean": float(values.mean()),
                "count": len(values),
            }
        )
    return tuple(rows)


def _delta_reason_counts(deltas: pd.DataFrame | None) -> dict[str, int]:
    if deltas is None or "unavailable_reason" not in deltas:
        return {}
    counts = deltas["unavailable_reason"].dropna().astype(str).value_counts().sort_index()
    return {str(reason): int(count) for reason, count in counts.items()}


def _comparison_plot_snippet() -> str:
    return (
        "comparison_plots:\n"
        "  format: png\n"
        "  plots:\n"
        "    - name: density_value_comparison\n"
        "      kind: property_comparison\n"
        "      fluid: Propane\n"
        "      property: mass_density\n"
        "      x: temperature\n"
        "      group_by: pressure\n"
        "      models: [heos, pr, srk]\n"
        "    - name: density_relative_delta\n"
        "      kind: property_delta\n"
        "      fluid: Propane\n"
        "      property: mass_density\n"
        "      x: temperature\n"
        "      group_by: pressure\n"
        "      models: [pr, srk]\n"
        "      delta_metric: signed_relative_difference"
    )


def _indent(lines: list[str], *, prefix: str) -> list[str]:
    return [prefix + line for line in lines]
