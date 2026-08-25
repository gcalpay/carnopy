from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, cast

import pandas as pd

from carnopy.app.scene_contracts import (
    SceneFieldClassification,
    SceneSourceBinding,
    SceneTopologyEvidence,
)
from carnopy.app.scene_profiles import (
    _PREPARED_ID,
    _PREPARED_SOURCE_CONTEXTS,
    Checkpoint,
    LoadedSceneProfileSource,
    SceneFieldData,
    _categorical_field,
    _exact_int,
    _field_from_dtype,
    _label,
    _numeric_field,
    _parse_scenario_table_id,
    _prepared_ids,
    _read_json_identity,
    _read_table,
    _require_recorded_hash,
    _require_unique_field_ids,
    _require_version,
    _strict_boolean_series,
    _string_list,
    _unit_status,
    _unsupported,
    _validate_control_hashes,
)


def load_prepared_source(
    binding: SceneSourceBinding,
    *,
    checkpoint: Checkpoint | None,
) -> LoadedSceneProfileSource:
    controls = {control.name: control.artifact for control in binding.controls}
    manifest_identity = controls.get("manifest.json")
    diagnostics_identity = controls.get("diagnostics.json")
    if manifest_identity is None or diagnostics_identity is None:
        _unsupported("prepared scene sources require manifest and diagnostics controls")
    if "preparation.normalized.json" not in controls:
        _unsupported("prepared scene sources require the normalized preparation control")
    manifest = _read_json_identity(manifest_identity, "preparation manifest", checkpoint)
    diagnostics_summary = _read_json_identity(
        diagnostics_identity,
        "preparation diagnostics",
        checkpoint,
    )
    _require_version(manifest, "preparation_schema_version", 1, "preparation")
    _validate_control_hashes(
        manifest,
        binding,
        source_root=Path(binding.source_path),
        unhashed_names={"manifest.json"},
    )
    tables = {table.table_id: table for table in binding.tables}
    required = {"table", "provenance", "diagnostics", "exclusions"}
    if not required.issubset(tables):
        _unsupported("prepared scene binding omits required support tables")
    for table in tables.values():
        _require_recorded_hash(
            manifest,
            table.artifact,
            table.artifact.path,
            source_root=Path(binding.source_path),
        )
    main = _read_table(tables["table"], checkpoint)
    provenance = _read_table(tables["provenance"], checkpoint)
    source_diagnostics = _read_table(tables["diagnostics"], checkpoint)
    exclusions = _read_table(tables["exclusions"], checkpoint)
    _validate_prepared_joins(
        manifest,
        diagnostics_summary,
        main,
        provenance,
        source_diagnostics,
        exclusions,
    )
    selected = binding.selected_table()
    scenario_context: tuple[str, str] | None = None
    scenario_metadata: Mapping[str, Any] | None = None
    if selected.table_id == "table":
        selected_frame = main
    else:
        scenario_name, partition = _parse_scenario_table_id(selected.table_id)
        selected_frame = _read_table(selected, checkpoint)
        scenario_metadata = _validate_scenario_partition(
            binding,
            manifest,
            main,
            selected,
            selected_frame,
            scenario_name,
            partition,
            checkpoint,
        )
        scenario_context = (scenario_name, partition)
    ids = _prepared_ids(selected_frame, "selected prepared table")
    joined = _join_prepared_evidence(selected_frame, provenance, source_diagnostics, ids)
    source_valid = _strict_boolean_series(joined["source_valid"], "prepared source_valid")
    fields, priority = _prepared_fields(
        manifest,
        joined,
        list(selected_frame.columns),
        scenario_metadata=scenario_metadata,
        scenario_context=scenario_context,
    )
    topology = SceneTopologyEvidence(
        status="unavailable",
        reason_code="source_sampling_levels_not_recorded",
        reason=(
            "prepared bundles preserve exact source coordinates but do not record the original "
            "ordered sampler levels required to infer adjacency"
        ),
    )
    return LoadedSceneProfileSource(
        binding=binding,
        source_row_count=len(selected_frame),
        source_valid=source_valid.reset_index(drop=True),
        fields=fields,
        topology=topology,
        default_priority=priority,
    )


def _validate_prepared_joins(
    manifest: Mapping[str, Any],
    diagnostics_summary: Mapping[str, Any],
    main: pd.DataFrame,
    provenance: pd.DataFrame,
    diagnostics: pd.DataFrame,
    exclusions: pd.DataFrame,
) -> None:
    column_roles = manifest.get("column_roles")
    if not isinstance(column_roles, dict):
        _unsupported("preparation manifest has no recorded column roles")
    recorded_table_columns = _string_list(
        column_roles.get("table"),
        "prepared table column roles",
    )
    if recorded_table_columns != list(main.columns):
        _unsupported("prepared main table columns disagree with the manifest")
    for label, frame, key in (
        ("provenance", provenance, "provenance"),
        ("diagnostics", diagnostics, "diagnostics"),
    ):
        recorded = _string_list(column_roles.get(key), f"prepared {label} column roles")
        if recorded != list(frame.columns):
            _unsupported(f"prepared {label} columns disagree with the manifest")
    eligible = manifest.get("eligible_row_count")
    excluded = manifest.get("excluded_row_count")
    if not _exact_int(eligible) or eligible != len(main):
        _unsupported("preparation eligible row count disagrees with the main table")
    if not _exact_int(excluded) or excluded != len(exclusions):
        _unsupported("preparation excluded row count disagrees with exclusions")
    if diagnostics_summary.get("excluded_row_count") != excluded:
        _unsupported("preparation diagnostics and manifest exclusion counts disagree")
    if diagnostics_summary.get("source_row_count") != eligible + excluded:
        _unsupported("preparation source row count disagrees with retained and excluded rows")
    main_ids = _prepared_ids(main, "prepared main table")
    if main_ids != list(range(len(main))):
        _unsupported("prepared main table IDs are not the exact materialized row sequence")
    for label, support in (("provenance", provenance), ("diagnostics", diagnostics)):
        support_ids = _prepared_ids(support, f"prepared {label}")
        if set(support_ids) != set(main_ids) or len(support_ids) != len(main_ids):
            _unsupported(f"prepared {label} IDs do not join one-to-one with the main table")
    required_provenance = {
        _PREPARED_ID,
        "source_artifact",
        "source_run_id",
        "source_row_index",
        "source_row_hash",
        "source_state_hash",
        "source_mode",
        "source_fluid",
        "source_phase",
        "backend_model",
    }
    required_diagnostics = {_PREPARED_ID, "source_valid"}
    required_exclusions = {
        "source_artifact",
        "source_row_index",
        "primary_reason",
        "reason_codes",
        "missing_or_invalid_fields",
    }
    if not required_provenance.issubset(provenance.columns):
        _unsupported("prepared provenance is missing required identity columns")
    if not required_diagnostics.issubset(diagnostics.columns):
        _unsupported("prepared diagnostics is missing source-valid evidence")
    if not required_exclusions.issubset(exclusions.columns):
        _unsupported("prepared exclusions are missing required scientific evidence")
    _strict_boolean_series(diagnostics["source_valid"], "prepared source_valid")
    source_keys = ["source_artifact", "source_row_index"]
    if provenance.duplicated(source_keys).any():
        _unsupported("prepared provenance repeats a source row identity")
    if set(source_keys).issubset(exclusions.columns):
        retained = set(map(tuple, provenance[source_keys].itertuples(index=False, name=None)))
        rejected = set(map(tuple, exclusions[source_keys].itertuples(index=False, name=None)))
        if retained & rejected:
            _unsupported("prepared provenance and exclusions contradict source row identity")


def _validate_scenario_partition(
    binding: SceneSourceBinding,
    manifest: Mapping[str, Any],
    main: pd.DataFrame,
    selected: Any,
    selected_frame: pd.DataFrame,
    scenario_name: str,
    partition: str,
    checkpoint: Checkpoint | None,
) -> Mapping[str, Any]:
    scenarios = manifest.get("scenarios")
    entries = scenarios.get("scenarios") if isinstance(scenarios, dict) else None
    if not isinstance(entries, list):
        _unsupported("prepared scenario partition has no manifest scenario evidence")
    matches = [
        item for item in entries if isinstance(item, dict) and item.get("name") == scenario_name
    ]
    if len(matches) != 1:
        _unsupported("prepared scenario identity is not recorded exactly once")
    summary = cast(dict[str, Any], matches[0])
    counts = summary.get("partition_counts")
    if not isinstance(counts, dict) or counts.get(partition) != len(selected_frame):
        _unsupported("prepared scenario partition count disagrees with its table")
    expected_relative = f"data/scenarios/{scenario_name}/{partition}.parquet"
    artifacts = summary.get("partition_artifacts")
    if not isinstance(artifacts, list) or artifacts.count(expected_relative) != 1:
        _unsupported("prepared scenario partition path is not recorded exactly once")
    hashes = summary.get("partition_artifact_hashes")
    if not isinstance(hashes, dict) or hashes.get(expected_relative) != selected.artifact.sha256:
        _unsupported("prepared scenario partition hash evidence disagrees")
    control = next(
        (item.artifact for item in binding.controls if item.name == f"scenario:{scenario_name}"),
        None,
    )
    if control is None:
        _unsupported("prepared scenario partition has no verified scenario metadata")
    scenario = _read_json_identity(control, f"scenario {scenario_name}", checkpoint)
    for key in ("name", "kind", "partition_counts", "transformations"):
        if scenario.get(key) != summary.get(key):
            _unsupported(f"prepared scenario metadata contradicts manifest field {key!r}")
    report_control = next(
        (item.artifact for item in binding.controls if item.name == "scenario_report.json"),
        None,
    )
    if report_control is None:
        _unsupported("prepared scenario partition has no verified scenario report")
    report = _read_json_identity(report_control, "preparation scenario report", checkpoint)
    _require_version(report, "scenario_report_schema_version", 1, "scenario report")
    report_entries = report.get("scenarios")
    report_matches = (
        [
            item
            for item in report_entries
            if isinstance(item, dict) and item.get("name") == scenario_name
        ]
        if isinstance(report_entries, list)
        else []
    )
    if len(report_matches) != 1 or report_matches[0] != summary:
        _unsupported("prepared scenario report contradicts the manifest summary")
    selected_ids = _prepared_ids(selected_frame, "prepared scenario partition")
    main_ids = set(_prepared_ids(main, "prepared main table"))
    if not set(selected_ids).issubset(main_ids):
        _unsupported("prepared scenario partition references an unknown prepared row")
    shared = [column for column in main.columns if column in selected_frame.columns]
    expected = (
        main.set_index(_PREPARED_ID, drop=False).loc[selected_ids, shared].reset_index(drop=True)
    )
    actual = selected_frame.loc[:, shared].reset_index(drop=True)
    if list(expected.columns) != list(actual.columns) or not expected.equals(actual):
        _unsupported("prepared scenario rows contradict the main table")
    return scenario


def _join_prepared_evidence(
    selected: pd.DataFrame,
    provenance: pd.DataFrame,
    diagnostics: pd.DataFrame,
    ids: list[int],
) -> pd.DataFrame:
    selected_index = selected.set_index(_PREPARED_ID, drop=False)
    provenance_index = provenance.set_index(_PREPARED_ID, drop=False)
    diagnostics_index = diagnostics.set_index(_PREPARED_ID, drop=False)
    if any(
        row_id not in provenance_index.index or row_id not in diagnostics_index.index
        for row_id in ids
    ):
        _unsupported("selected prepared rows do not have complete joined evidence")
    joined = selected_index.loc[ids].reset_index(drop=True).copy()
    for support in (provenance_index.loc[ids], diagnostics_index.loc[ids]):
        for column in support.columns:
            if column == _PREPARED_ID:
                continue
            values = support[column].reset_index(drop=True)
            if column in joined.columns:
                if not joined[column].reset_index(drop=True).equals(values):
                    _unsupported(f"prepared join contradicts shared column {column!r}")
                continue
            joined[column] = values
    return joined


def _prepared_fields(
    manifest: Mapping[str, Any],
    joined: pd.DataFrame,
    selected_columns: Sequence[str],
    *,
    scenario_metadata: Mapping[str, Any] | None,
    scenario_context: tuple[str, str] | None,
) -> tuple[tuple[SceneFieldData, ...], tuple[str, ...]]:
    mapping = manifest.get("semantic_field_mapping")
    if not isinstance(mapping, dict):
        _unsupported("preparation manifest has no semantic field mapping")
    roles = _prepared_roles(manifest)
    fields: list[SceneFieldData] = []
    priority: list[str] = []
    mapped_columns: set[str] = {_PREPARED_ID}
    for semantic_name, raw_details in mapping.items():
        if not isinstance(semantic_name, str) or not isinstance(raw_details, dict):
            _unsupported("preparation semantic field mapping is malformed")
        source_column = raw_details.get("column")
        if not isinstance(source_column, str):
            _unsupported(f"prepared field {semantic_name!r} has no source column")
        column = semantic_name
        if column not in selected_columns:
            continue
        classification = roles.get(semantic_name)
        if classification is None:
            _unsupported(f"prepared field {semantic_name!r} has no unambiguous scientific role")
        unit_value = raw_details.get("unit")
        unit = unit_value if isinstance(unit_value, str) and unit_value else None
        values = joined[column]
        field = _field_from_dtype(
            semantic_name,
            column,
            _label(semantic_name),
            values,
            classification,
            "table",
            unit,
            _unit_status(unit),
        )
        fields.append(field)
        priority.append(semantic_name)
        mapped_columns.add(column)
    vocabularies = manifest.get("categorical_vocabularies")
    if isinstance(vocabularies, dict):
        for semantic_name, raw in vocabularies.items():
            if not isinstance(semantic_name, str) or not isinstance(raw, dict):
                _unsupported("preparation categorical vocabulary is malformed")
            columns = raw.get("columns")
            if not isinstance(columns, list):
                _unsupported(f"prepared category {semantic_name!r} has no encoded columns")
            for column in columns:
                if not isinstance(column, str) or column not in selected_columns:
                    _unsupported(f"prepared category column {column!r} is absent")
                mapped_columns.add(column)
                fields.append(
                    _categorical_field(
                        column,
                        column,
                        _label(column),
                        joined[column].map({True: "true", False: "false"}),
                        "prepared_feature",
                        "table",
                    )
                )
    transforms: dict[str, Mapping[str, Any]] = {}
    if scenario_metadata is not None:
        raw_transforms = scenario_metadata.get("transformations")
        if not isinstance(raw_transforms, list):
            _unsupported("prepared scenario does not record transformations")
        for value in raw_transforms:
            if not isinstance(value, dict) or not isinstance(value.get("output_column"), str):
                _unsupported("prepared scenario transformation metadata is malformed")
            output = cast(str, value["output_column"])
            if output in transforms:
                _unsupported("prepared scenario repeats a transformed output")
            transforms[output] = value
        for output in transforms:
            if output not in selected_columns:
                _unsupported(f"recorded scenario transform {output!r} is absent")
            mapped_columns.add(output)
            fields.append(
                _numeric_field(
                    output,
                    output,
                    _label(output),
                    joined[output],
                    "recorded_transform",
                    "scenario",
                    None,
                    unit_status="transformed",
                )
            )
            priority.append(output)
    unknown = [column for column in selected_columns if column not in mapped_columns]
    if unknown:
        _unsupported("prepared table contains unclassified columns: " + ", ".join(unknown))
    source_priority: list[str] = []
    for field_id, source_column, label in (
        ("source.temperature", "source_temperature_K", "Source temperature"),
        ("source.pressure", "source_pressure_Pa", "Source pressure"),
        (
            "source.vapor_mass_fraction",
            "source_vapor_mass_fraction",
            "Source vapor mass fraction",
        ),
    ):
        if source_column not in joined.columns or joined[source_column].isna().all():
            continue
        unit = {
            "source.temperature": "K",
            "source.pressure": "Pa",
            "source.vapor_mass_fraction": "1",
        }[field_id]
        fields.append(
            _numeric_field(
                field_id,
                source_column,
                label,
                joined[source_column],
                "source_coordinate",
                "provenance",
                unit,
            )
        )
        source_priority.append(field_id)
    for field_id, column, label in _PREPARED_SOURCE_CONTEXTS:
        if column in joined.columns and not joined[column].isna().all():
            fields.append(
                _categorical_field(
                    field_id,
                    column,
                    label,
                    joined[column],
                    "context",
                    "provenance",
                )
            )
    if scenario_context is not None:
        scenario, partition = scenario_context
        fields.extend(
            (
                _categorical_field(
                    "scenario",
                    "scenario",
                    "Scenario",
                    pd.Series([scenario] * len(joined), dtype="string"),
                    "context",
                    "scenario",
                ),
                _categorical_field(
                    "partition",
                    "partition",
                    "Partition",
                    pd.Series([partition] * len(joined), dtype="string"),
                    "context",
                    "scenario",
                ),
            )
        )
    _require_unique_field_ids(fields)
    return tuple(fields), tuple(dict.fromkeys([*source_priority, *priority]))


def _prepared_roles(manifest: Mapping[str, Any]) -> dict[str, SceneFieldClassification]:
    features = manifest.get("features")
    if not isinstance(features, dict):
        _unsupported("preparation manifest has no feature roles")
    numeric = _string_list(features.get("numeric"), "numeric features")
    derived = _string_list(features.get("derived"), "derived features")
    categorical_raw = features.get("categorical")
    if not isinstance(categorical_raw, list):
        _unsupported("preparation categorical feature roles are malformed")
    categorical: list[str] = []
    for item in categorical_raw:
        field = item.get("field") if isinstance(item, dict) else None
        if not isinstance(field, str):
            _unsupported("preparation categorical feature role is malformed")
        categorical.append(field)
    targets = _string_list(manifest.get("targets"), "prepared targets")
    auxiliary = _string_list(manifest.get("auxiliary"), "prepared auxiliary")
    role_groups: tuple[tuple[SceneFieldClassification, list[str]], ...] = (
        ("prepared_feature", [*numeric, *categorical]),
        ("derived_feature", derived),
        ("prepared_target", targets),
        ("prepared_auxiliary", auxiliary),
    )
    result: dict[str, SceneFieldClassification] = {}
    for role, names in role_groups:
        for name in names:
            if name in result:
                _unsupported(f"prepared field {name!r} has contradictory roles")
            result[name] = role
    return result
