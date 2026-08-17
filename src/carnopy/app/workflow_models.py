from __future__ import annotations

import copy
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, cast

from PySide6.QtCore import (
    Property,
    QAbstractListModel,
    QByteArray,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    Qt,
    Signal,
    Slot,
)

IssueOrigin = Literal["local", "schema", "source", "dependency", "plan", "runtime"]
IssueSeverity = Literal["blocking", "advisory"]

ORIGIN_ROLE = int(Qt.ItemDataRole.UserRole) + 1
SEVERITY_ROLE = ORIGIN_ROLE + 1
CODE_ROLE = ORIGIN_ROLE + 2
MESSAGE_ROLE = ORIGIN_ROLE + 3
DOCUMENT_KIND_ROLE = ORIGIN_ROLE + 4
SECTION_ROLE = ORIGIN_ROLE + 5
FIELD_ID_ROLE = ORIGIN_ROLE + 6
ITEM_KEY_ROLE = ORIGIN_ROLE + 7
NESTED_ROW_ROLE = ORIGIN_ROLE + 8
PATH_ROLE = ORIGIN_ROLE + 9
INVALID_INDEX = QModelIndex()


class WorkflowListModel(QAbstractListModel):
    """Expose detached workflow rows through one explicit, stable role set."""

    count_changed = Signal()

    def __init__(self, roles: Sequence[str], parent: QObject | None = None) -> None:
        super().__init__(parent)
        if not roles or len(set(roles)) != len(roles):
            raise ValueError("workflow model roles must be non-empty and unique")
        self._roles = tuple(roles)
        self._role_names = {
            int(Qt.ItemDataRole.UserRole) + offset: name
            for offset, name in enumerate(self._roles, start=1)
        }
        self._rows: tuple[dict[str, object], ...] = ()

    def roleNames(self) -> dict[int, QByteArray]:
        return {role: QByteArray(name.encode("utf-8")) for role, name in self._role_names.items()}

    def rowCount(
        self,
        _parent: QModelIndex | QPersistentModelIndex = INVALID_INDEX,
    ) -> int:
        return len(self._rows)

    def data(
        self,
        index: QModelIndex | QPersistentModelIndex,
        role: int = int(Qt.ItemDataRole.DisplayRole),
    ) -> object:
        if not index.isValid() or not 0 <= index.row() < len(self._rows):
            return None
        name = self._role_names.get(role)
        return None if name is None else copy.deepcopy(self._rows[index.row()].get(name))

    def replace(self, rows: Iterable[Mapping[str, object]]) -> bool:
        updated = tuple(
            {name: copy.deepcopy(row.get(name)) for name in self._roles} for row in rows
        )
        if updated == self._rows:
            return False
        previous_count = len(self._rows)
        self.beginResetModel()
        self._rows = updated
        self.endResetModel()
        if len(updated) != previous_count:
            self.count_changed.emit()
        return True

    def clear(self) -> bool:
        return self.replace(())

    def get_count(self) -> int:
        return len(self._rows)

    count = Property(int, get_count, notify=count_changed)

    @Slot(int, result="QVariantMap")
    def get(self, row: int) -> dict[str, object]:
        return copy.deepcopy(self._rows[row]) if 0 <= row < len(self._rows) else {}

    def rows(self) -> tuple[dict[str, object], ...]:
        return tuple(copy.deepcopy(row) for row in self._rows)


@dataclass(frozen=True)
class PreparationPlanProjection:
    """Validated, detached QML-facing rows from one worker Preparation plan."""

    source_row_count: int
    eligible_row_count: int
    excluded_row_count: int
    reference_context_required: bool
    reference_context_compatible: bool
    reference_policy: str
    reference_backend: str
    reference_backend_model: str
    semantic_fields: tuple[dict[str, object], ...]
    reference_fields: tuple[dict[str, object], ...]
    reference_contexts: tuple[dict[str, object], ...]
    exclusion_reasons: tuple[dict[str, object], ...]
    categories: tuple[dict[str, object], ...]
    scenarios: tuple[dict[str, object], ...]
    partitions: tuple[dict[str, object], ...]
    transformations: tuple[dict[str, object], ...]
    leakage_audits: tuple[dict[str, object], ...]
    output_formats: tuple[dict[str, object], ...]
    array_scopes: tuple[dict[str, object], ...]
    array_conversion_errors: tuple[dict[str, object], ...]
    array_auxiliary_shapes: tuple[dict[str, object], ...]
    matrix_checks: tuple[dict[str, object], ...]
    baseline_checks: tuple[dict[str, object], ...]
    baseline_estimators: tuple[dict[str, object], ...]
    dependencies: tuple[dict[str, object], ...]

    @classmethod
    def from_worker_payload(
        cls,
        payload: Mapping[str, object],
    ) -> PreparationPlanProjection:
        source_rows = _nonnegative_integer(payload.get("source_row_count"), "source row count")
        eligible_rows = _nonnegative_integer(
            payload.get("eligible_row_count"), "eligible row count"
        )
        excluded_rows = _nonnegative_integer(
            payload.get("excluded_row_count"), "excluded row count"
        )
        if eligible_rows + excluded_rows != source_rows:
            raise ValueError("Preparation plan row counts are inconsistent")

        semantics = _required_mapping(payload, "resolved_semantics")
        semantic_fields = tuple(
            _semantic_field_row(name, value) for name, value in sorted(semantics.items())
        )
        reference = _required_mapping(payload, "reference_state")
        reference_required = _boolean(
            reference.get("requires_context_compatibility"),
            "reference-context requirement",
        )
        reference_compatible = _boolean(
            reference.get("compatible"),
            "reference-context compatibility",
        )
        reference_field_rows: list[dict[str, object]] = [
            {"name": value}
            for value in sorted(
                _string_list(
                    reference.get("selected_reference_dependent_fields"),
                    "reference-dependent fields",
                )
            )
        ]
        reference_fields = tuple(reference_field_rows)
        compatible_context = reference.get("compatible_context")
        if compatible_context is None:
            context: Mapping[str, object] = {}
        elif isinstance(compatible_context, Mapping):
            context = compatible_context
        else:
            raise ValueError("Preparation plan compatible reference context must be a mapping")
        reference_contexts = tuple(
            sorted(
                (
                    _reference_context_row(value)
                    for value in _mapping_list(reference.get("contexts"), "reference contexts")
                ),
                key=lambda row: (str(row["artifact"]), str(row["runId"])),
            )
        )

        exclusion_counts = _required_mapping(payload, "exclusion_reason_counts")
        exclusion_reasons = tuple(
            {
                "reason": _nonempty_text(reason, "exclusion reason"),
                "count": _nonnegative_integer(count, "exclusion reason count"),
            }
            for reason, count in sorted(exclusion_counts.items())
        )
        category_rows: list[dict[str, object]] = [
            {"field": field, "value": category}
            for field, values in sorted(_required_mapping(payload, "categories").items())
            for category in _string_list(values, f"categories for {field}")
        ]
        categories = tuple(category_rows)

        scenario_rows: list[dict[str, object]] = []
        partition_rows: list[dict[str, object]] = []
        transformation_rows: list[dict[str, object]] = []
        leakage_rows: list[dict[str, object]] = []
        for scenario_order, scenario_value in enumerate(
            _mapping_list(payload.get("scenarios"), "Preparation scenarios")
        ):
            name = _nonempty_text(scenario_value.get("name"), "scenario name")
            kind = _nonempty_text(scenario_value.get("kind"), "scenario kind")
            partition_counts = _required_mapping(scenario_value, "partition_counts")
            ordered_partitions = _partition_count_rows(name, partition_counts)
            transformations = _mapping_list(
                scenario_value.get("transformations"), "scenario transformations"
            )
            leakage = _required_mapping(scenario_value, "state_leakage")
            duplicate_groups = _nonnegative_integer(
                leakage.get("duplicate_state_group_count"),
                "duplicate state group count",
            )
            cross_partition_groups = _nonnegative_integer(
                leakage.get("cross_partition_group_count"),
                "cross-partition group count",
            )
            scenario_row_count = sum(cast(int, row["rowCount"]) for row in ordered_partitions)
            if scenario_row_count != eligible_rows:
                raise ValueError(
                    f"Preparation plan scenario {name!r} does not partition every eligible row"
                )
            scenario_rows.append(
                {
                    "name": name,
                    "kind": kind,
                    "order": scenario_order,
                    "rowCount": scenario_row_count,
                    "partitionCount": len(ordered_partitions),
                    "transformationCount": len(transformations),
                    "duplicateStateGroupCount": duplicate_groups,
                    "crossPartitionGroupCount": cross_partition_groups,
                }
            )
            partition_rows.extend(ordered_partitions)
            transformation_rows.extend(
                _transformation_row(name, order, value)
                for order, value in enumerate(transformations)
            )
            leakage_rows.append(
                {
                    "scenario": name,
                    "identityColumn": _nonempty_text(
                        leakage.get("identity_column"), "leakage identity column"
                    ),
                    "duplicateStateGroupCount": duplicate_groups,
                    "crossPartitionGroupCount": cross_partition_groups,
                }
            )

        outputs = _required_mapping(payload, "outputs")
        output_format_rows: list[dict[str, object]] = [
            {"name": value}
            for value in _string_list(outputs.get("formats"), "Preparation output formats")
        ]
        output_formats = tuple(output_format_rows)
        array_scopes: list[dict[str, object]] = []
        conversion_rows: list[dict[str, object]] = []
        auxiliary_rows: list[dict[str, object]] = []
        for scope_order, feasibility in enumerate(
            _mapping_list(outputs.get("array_feasibility"), "array feasibility")
        ):
            scope = _nonempty_text(feasibility.get("scope"), "array scope")
            scope_kind, array_scenario, partition = _array_scope_parts(scope)
            status = _nonempty_text(feasibility.get("status"), "array feasibility status")
            feature_shape = _optional_shape(feasibility.get("feature_shape"), "feature shape")
            target_shape = _optional_shape(feasibility.get("target_shape"), "target shape")
            formats = _optional_string_list(feasibility.get("formats"), "array formats")
            auxiliary_shapes = _optional_mapping(
                feasibility.get("auxiliary_shapes"), "auxiliary shapes"
            )
            conversions = _optional_mapping(
                feasibility.get("float_conversion"), "float-conversion evidence"
            )
            conversion_count = 0
            for role, raw_fields in sorted(conversions.items()):
                fields = _mapping(raw_fields, f"{role} conversion evidence")
                for field, raw_metrics in sorted(fields.items()):
                    metrics = _mapping(raw_metrics, f"conversion evidence for {field}")
                    conversion_rows.append(
                        {
                            "scope": scope,
                            "role": _nonempty_text(role, "array conversion role"),
                            "field": _nonempty_text(field, "array conversion field"),
                            "maxAbsoluteError": _number(
                                metrics.get("max_abs_error"), "maximum absolute error"
                            ),
                            "maxRelativeError": _number(
                                metrics.get("max_rel_error"), "maximum relative error"
                            ),
                            "meanAbsoluteError": _number(
                                metrics.get("mean_abs_error"), "mean absolute error"
                            ),
                        }
                    )
                    conversion_count += 1
            for field, raw_shape in sorted(auxiliary_shapes.items()):
                shape = _shape(raw_shape, f"auxiliary shape for {field}")
                auxiliary_rows.append(
                    {
                        "scope": scope,
                        "field": _nonempty_text(field, "auxiliary array field"),
                        "rowCount": shape[0],
                        "columnCount": shape[1],
                    }
                )
            array_scopes.append(
                {
                    "scope": scope,
                    "scopeKind": scope_kind,
                    "scenario": array_scenario,
                    "partition": partition,
                    "order": scope_order,
                    "status": status,
                    "dtype": _optional_text(feasibility.get("dtype"), "array dtype"),
                    "formats": formats,
                    "shapeAvailable": feature_shape is not None and target_shape is not None,
                    "featureRows": 0 if feature_shape is None else feature_shape[0],
                    "featureColumns": 0 if feature_shape is None else feature_shape[1],
                    "targetRows": 0 if target_shape is None else target_shape[0],
                    "targetColumns": 0 if target_shape is None else target_shape[1],
                    "auxiliaryArrayCount": len(auxiliary_shapes),
                    "conversionFieldCount": conversion_count,
                }
            )

        baseline_checks: list[dict[str, object]] = []
        baseline_estimators: list[dict[str, object]] = []
        raw_baselines = payload.get("baseline_feasibility")
        baselines = (
            [] if raw_baselines is None else _mapping_list(raw_baselines, "baseline feasibility")
        )
        for order, baseline in enumerate(baselines):
            baseline_scenario = _nullable_text(baseline.get("scenario"), "baseline scenario")
            feature_columns = _optional_string_list(
                baseline.get("feature_columns"), "baseline feature columns"
            )
            target_columns = _optional_string_list(
                baseline.get("target_columns"), "baseline target columns"
            )
            estimators = _optional_mapping_list(baseline.get("estimators"), "baseline estimators")
            train_rows = _first_shape_dimension(
                baseline.get("train_shapes"), "baseline train shapes"
            )
            evaluation_rows = _evaluation_shape_rows(
                baseline.get("evaluation_shapes"), "baseline evaluation shapes"
            )
            fit_performed = _optional_boolean(baseline.get("fit_performed"), "baseline fit state")
            if fit_performed:
                raise ValueError("Preparation planning must not report a fitted baseline")
            baseline_checks.append(
                {
                    "scenario": baseline_scenario,
                    "order": order,
                    "status": _nonempty_text(baseline.get("status"), "baseline feasibility status"),
                    "library": _optional_text(baseline.get("library"), "baseline library"),
                    "libraryVersion": _optional_text(
                        baseline.get("library_version"), "baseline library version"
                    ),
                    "featureCount": len(feature_columns),
                    "targetCount": len(target_columns),
                    "trainRowCount": train_rows,
                    "evaluationPartitionCount": len(evaluation_rows),
                    "evaluationRowCount": sum(evaluation_rows),
                    "estimatorCount": len(estimators),
                    "fitPerformed": fit_performed,
                }
            )
            baseline_estimators.extend(
                {
                    "scenario": baseline_scenario,
                    "model": _nonempty_text(estimator.get("model"), "baseline model"),
                    "target": _nonempty_text(estimator.get("target"), "baseline target"),
                    "estimatorType": _nonempty_text(
                        estimator.get("estimator_type"), "baseline estimator type"
                    ),
                }
                for estimator in estimators
            )

        raw_matrix_diagnostics = payload.get("matrix_diagnostics")
        matrix_diagnostics = (
            []
            if raw_matrix_diagnostics is None
            else _mapping_list(raw_matrix_diagnostics, "matrix diagnostics")
        )
        matrix_checks = tuple(
            _matrix_check_row(order, diagnostic)
            for order, diagnostic in enumerate(matrix_diagnostics)
        )
        dependencies = tuple(
            _dependency_row(name, value)
            for name, value in sorted(_required_mapping(payload, "dependency_readiness").items())
        )
        return cls(
            source_row_count=source_rows,
            eligible_row_count=eligible_rows,
            excluded_row_count=excluded_rows,
            reference_context_required=reference_required,
            reference_context_compatible=reference_compatible,
            reference_policy=_optional_text(
                context.get("reference_state_policy"), "reference-state policy"
            ),
            reference_backend=_optional_text(context.get("backend"), "reference backend"),
            reference_backend_model=_optional_text(
                context.get("backend_model"), "reference backend model"
            ),
            semantic_fields=semantic_fields,
            reference_fields=reference_fields,
            reference_contexts=reference_contexts,
            exclusion_reasons=exclusion_reasons,
            categories=categories,
            scenarios=tuple(scenario_rows),
            partitions=tuple(partition_rows),
            transformations=tuple(transformation_rows),
            leakage_audits=tuple(leakage_rows),
            output_formats=output_formats,
            array_scopes=tuple(array_scopes),
            array_conversion_errors=tuple(conversion_rows),
            array_auxiliary_shapes=tuple(auxiliary_rows),
            matrix_checks=matrix_checks,
            baseline_checks=tuple(baseline_checks),
            baseline_estimators=tuple(baseline_estimators),
            dependencies=dependencies,
        )


def _semantic_field_row(name: object, value: object) -> dict[str, object]:
    field = _mapping(value, f"resolved semantics for {name}")
    dependencies = _optional_string_list(field.get("dependencies"), "derived-field dependencies")
    return {
        "name": _nonempty_text(name, "resolved semantic field"),
        "column": _nonempty_text(field.get("column"), "resolved semantic column"),
        "unit": _optional_text(field.get("unit"), "resolved semantic unit"),
        "kind": _nonempty_text(field.get("kind"), "resolved semantic kind"),
        "source": _nonempty_text(field.get("source"), "resolved semantic source"),
        "formula": _optional_text(field.get("formula"), "derived-field formula"),
        "dependencies": dependencies,
        "referenceStateSafe": _optional_boolean(
            field.get("reference_state_safe"), "derived-field reference-state safety"
        ),
        "arrayExportAllowed": _optional_boolean(
            field.get("array_export_allowed"), "derived-field array-export state"
        ),
    }


def _reference_context_row(value: Mapping[str, object]) -> dict[str, object]:
    targets = _optional_string_list(value.get("reference_state_targets"), "reference-state targets")
    return {
        "artifact": _nonempty_text(value.get("artifact"), "reference-context artifact"),
        "runId": _nonempty_text(value.get("run_id"), "reference-context run ID"),
        "backend": _optional_text(value.get("backend"), "reference-context backend"),
        "backendModel": _optional_text(
            value.get("backend_model"), "reference-context backend model"
        ),
        "referenceStatePolicy": _optional_text(
            value.get("reference_state_policy"), "reference-state policy"
        ),
        "referenceStateBackendModel": _optional_text(
            value.get("reference_state_backend_model"),
            "reference-state backend model",
        ),
        "targetCount": len(targets),
    }


def _partition_count_rows(
    scenario: str,
    counts: Mapping[str, object],
) -> tuple[dict[str, object], ...]:
    preferred = {"all": 0, "train": 1, "validation": 2, "test": 3}
    values = [
        (
            _nonempty_text(partition, "scenario partition"),
            _nonnegative_integer(count, "scenario partition count"),
        )
        for partition, count in counts.items()
    ]
    values.sort(key=lambda item: (preferred.get(item[0], len(preferred)), item[0]))
    return tuple(
        {
            "scenario": scenario,
            "partition": partition,
            "order": order,
            "rowCount": count,
        }
        for order, (partition, count) in enumerate(values)
    )


def _transformation_row(
    scenario: str,
    order: int,
    value: Mapping[str, object],
) -> dict[str, object]:
    methods = _string_list(value.get("methods"), "transformation methods")
    steps = _mapping_list(value.get("steps"), "transformation steps")
    if len(steps) != len(methods):
        raise ValueError("Preparation plan transformation steps do not match its methods")
    return {
        "scenario": scenario,
        "order": order,
        "field": _nonempty_text(value.get("field"), "transformation field"),
        "methods": methods,
        "outputColumn": _nonempty_text(value.get("output_column"), "transformation output column"),
        "fitPartition": _nonempty_text(value.get("fit_partition"), "transformation fit partition"),
        "stepCount": len(steps),
    }


def _array_scope_parts(scope: str) -> tuple[str, str, str]:
    if scope == "table":
        return "table", "", ""
    parts = scope.split(":")
    if len(parts) == 3 and parts[0] == "scenario" and parts[1] and parts[2]:
        return "scenario_partition", parts[1], parts[2]
    raise ValueError(f"Preparation plan array scope is malformed: {scope}")


def _matrix_check_row(
    order: int,
    value: Mapping[str, object],
) -> dict[str, object]:
    feature_columns = _optional_string_list(value.get("feature_columns"), "matrix feature columns")
    target_columns = _optional_string_list(value.get("target_columns"), "matrix target columns")
    constant_features = _optional_string_list(
        value.get("constant_feature_columns"), "constant feature columns"
    )
    variable_features = _optional_string_list(
        value.get("variable_feature_columns"), "variable feature columns"
    )
    near_constant_features = _optional_mapping_list(
        value.get("near_constant_feature_columns"), "near-constant feature columns"
    )
    correlated_pairs = _optional_mapping_list(
        value.get("highly_correlated_feature_pairs"), "correlated feature pairs"
    )
    target_correlations = _optional_mapping_list(
        value.get("feature_target_correlations"), "feature-target correlations"
    )
    condition = value.get("condition_number")
    return {
        "scenario": _nullable_text(value.get("scenario"), "matrix scenario"),
        "order": order,
        "fitPartition": _nonempty_text(value.get("fit_partition"), "matrix fit partition"),
        "status": _nonempty_text(value.get("status"), "matrix diagnostic status"),
        "rowCount": _optional_nonnegative_integer(value.get("row_count"), "matrix row count"),
        "featureCount": len(feature_columns),
        "targetCount": len(target_columns),
        "constantFeatureCount": len(constant_features),
        "nearConstantFeatureCount": len(near_constant_features),
        "variableFeatureCount": len(variable_features),
        "numericalRank": _optional_nonnegative_integer(
            value.get("numerical_rank"), "matrix numerical rank"
        ),
        "effectiveRank": _optional_number(value.get("effective_rank"), "effective rank"),
        "conditionNumberAvailable": condition is not None,
        "conditionNumber": _optional_number(condition, "condition number"),
        "conditionNumberInfinite": _optional_boolean(
            value.get("condition_number_is_infinite"), "infinite condition-number state"
        ),
        "correlatedPairCount": len(correlated_pairs),
        "featureTargetCorrelationCount": len(target_correlations),
    }


def _dependency_row(name: object, value: object) -> dict[str, object]:
    dependency = _mapping(value, f"dependency readiness for {name}")
    return {
        "name": _nonempty_text(name, "dependency name"),
        "available": _boolean(dependency.get("available"), "dependency availability"),
        "version": _optional_text(dependency.get("version"), "dependency version"),
    }


def _required_mapping(
    mapping: Mapping[str, object],
    key: str,
) -> Mapping[str, object]:
    return _mapping(mapping.get(key), key)


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"Preparation plan {label} must be a string-keyed mapping")
    return cast(Mapping[str, object], value)


def _optional_mapping(value: object, label: str) -> Mapping[str, object]:
    return {} if value is None else _mapping(value, label)


def _mapping_list(value: object, label: str) -> list[Mapping[str, object]]:
    if not isinstance(value, list):
        raise ValueError(f"Preparation plan {label} must be a list")
    return [_mapping(item, f"{label} entry") for item in value]


def _optional_mapping_list(value: object, label: str) -> list[Mapping[str, object]]:
    return [] if value is None else _mapping_list(value, label)


def _string_list(value: object, label: str) -> list[str]:
    if (
        not isinstance(value, list)
        or not all(isinstance(item, str) and item for item in value)
        or len(set(value)) != len(value)
    ):
        raise ValueError(f"Preparation plan {label} must be unique non-empty text")
    return cast(list[str], value)


def _optional_string_list(value: object, label: str) -> list[str]:
    return [] if value is None else _string_list(value, label)


def _nonempty_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"Preparation plan {label} must be non-empty text")
    return value


def _optional_text(value: object, label: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError(f"Preparation plan {label} must be text or null")
    return value


def _nullable_text(value: object, label: str) -> str:
    if value is None:
        return ""
    return _nonempty_text(value, label)


def _boolean(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"Preparation plan {label} must be boolean")
    return value


def _optional_boolean(value: object, label: str) -> bool:
    return False if value is None else _boolean(value, label)


def _nonnegative_integer(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"Preparation plan {label} must be a non-negative integer")
    return value


def _optional_nonnegative_integer(value: object, label: str) -> int:
    return 0 if value is None else _nonnegative_integer(value, label)


def _number(value: object, label: str) -> float:
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise ValueError(f"Preparation plan {label} must be numeric")
    return float(value)


def _optional_number(value: object, label: str) -> float:
    return 0.0 if value is None else _number(value, label)


def _shape(value: object, label: str) -> tuple[int, int]:
    if not isinstance(value, list) or len(value) not in {1, 2}:
        raise ValueError(f"Preparation plan {label} must be a one- or two-dimensional shape")
    dimensions = tuple(_nonnegative_integer(dimension, f"{label} dimension") for dimension in value)
    return (dimensions[0], 1 if len(dimensions) == 1 else dimensions[1])


def _optional_shape(value: object, label: str) -> tuple[int, int] | None:
    return None if value is None else _shape(value, label)


def _first_shape_dimension(value: object, label: str) -> int:
    if value is None:
        return 0
    shapes = _mapping(value, label)
    features = shapes.get("features")
    return 0 if features is None else _shape(features, f"{label} features")[0]


def _evaluation_shape_rows(value: object, label: str) -> list[int]:
    if value is None:
        return []
    evaluations = _mapping(value, label)
    rows: list[int] = []
    for partition, raw_shapes in sorted(evaluations.items()):
        shapes = _mapping(raw_shapes, f"{label} for {partition}")
        features = shapes.get("features")
        if features is None:
            raise ValueError(f"Preparation plan {label} is missing feature shape")
        rows.append(_shape(features, f"{label} features for {partition}")[0])
    return rows


class PreparationPlanModel(QObject):
    """Own the fixed QML models for the last accepted Preparation plan."""

    changed = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._projection: PreparationPlanProjection | None = None
        self.semantic_fields = WorkflowListModel(
            (
                "name",
                "column",
                "unit",
                "kind",
                "source",
                "formula",
                "dependencies",
                "referenceStateSafe",
                "arrayExportAllowed",
            ),
            self,
        )
        self.reference_fields = WorkflowListModel(("name",), self)
        self.reference_contexts = WorkflowListModel(
            (
                "artifact",
                "runId",
                "backend",
                "backendModel",
                "referenceStatePolicy",
                "referenceStateBackendModel",
                "targetCount",
            ),
            self,
        )
        self.exclusion_reasons = WorkflowListModel(("reason", "count"), self)
        self.category_values = WorkflowListModel(("field", "value"), self)
        self.scenarios = WorkflowListModel(
            (
                "name",
                "kind",
                "order",
                "rowCount",
                "partitionCount",
                "transformationCount",
                "duplicateStateGroupCount",
                "crossPartitionGroupCount",
            ),
            self,
        )
        self.partitions = WorkflowListModel(("scenario", "partition", "order", "rowCount"), self)
        self.transformations = WorkflowListModel(
            (
                "scenario",
                "order",
                "field",
                "methods",
                "outputColumn",
                "fitPartition",
                "stepCount",
            ),
            self,
        )
        self.leakage_audits = WorkflowListModel(
            (
                "scenario",
                "identityColumn",
                "duplicateStateGroupCount",
                "crossPartitionGroupCount",
            ),
            self,
        )
        self.output_formats = WorkflowListModel(("name",), self)
        self.array_feasibility = WorkflowListModel(
            (
                "scope",
                "scopeKind",
                "scenario",
                "partition",
                "order",
                "status",
                "dtype",
                "formats",
                "shapeAvailable",
                "featureRows",
                "featureColumns",
                "targetRows",
                "targetColumns",
                "auxiliaryArrayCount",
                "conversionFieldCount",
            ),
            self,
        )
        self.array_conversion_errors = WorkflowListModel(
            (
                "scope",
                "role",
                "field",
                "maxAbsoluteError",
                "maxRelativeError",
                "meanAbsoluteError",
            ),
            self,
        )
        self.array_auxiliary_shapes = WorkflowListModel(
            ("scope", "field", "rowCount", "columnCount"), self
        )
        self.matrix_diagnostics = WorkflowListModel(
            (
                "scenario",
                "order",
                "fitPartition",
                "status",
                "rowCount",
                "featureCount",
                "targetCount",
                "constantFeatureCount",
                "nearConstantFeatureCount",
                "variableFeatureCount",
                "numericalRank",
                "effectiveRank",
                "conditionNumberAvailable",
                "conditionNumber",
                "conditionNumberInfinite",
                "correlatedPairCount",
                "featureTargetCorrelationCount",
            ),
            self,
        )
        self.baseline_feasibility = WorkflowListModel(
            (
                "scenario",
                "order",
                "status",
                "library",
                "libraryVersion",
                "featureCount",
                "targetCount",
                "trainRowCount",
                "evaluationPartitionCount",
                "evaluationRowCount",
                "estimatorCount",
                "fitPerformed",
            ),
            self,
        )
        self.baseline_estimators = WorkflowListModel(
            ("scenario", "model", "target", "estimatorType"), self
        )
        self.dependencies = WorkflowListModel(("name", "available", "version"), self)

    def replace(self, projection: PreparationPlanProjection) -> None:
        self._projection = projection
        rows = (
            projection.semantic_fields,
            projection.reference_fields,
            projection.reference_contexts,
            projection.exclusion_reasons,
            projection.categories,
            projection.scenarios,
            projection.partitions,
            projection.transformations,
            projection.leakage_audits,
            projection.output_formats,
            projection.array_scopes,
            projection.array_conversion_errors,
            projection.array_auxiliary_shapes,
            projection.matrix_checks,
            projection.baseline_checks,
            projection.baseline_estimators,
            projection.dependencies,
        )
        for model, values in zip(self._models(), rows, strict=True):
            model.replace(values)
        self.changed.emit()

    def clear(self) -> None:
        if self._projection is None:
            return
        self._projection = None
        for model in self._models():
            model.clear()
        self.changed.emit()

    def _models(self) -> tuple[WorkflowListModel, ...]:
        return (
            self.semantic_fields,
            self.reference_fields,
            self.reference_contexts,
            self.exclusion_reasons,
            self.category_values,
            self.scenarios,
            self.partitions,
            self.transformations,
            self.leakage_audits,
            self.output_formats,
            self.array_feasibility,
            self.array_conversion_errors,
            self.array_auxiliary_shapes,
            self.matrix_diagnostics,
            self.baseline_feasibility,
            self.baseline_estimators,
            self.dependencies,
        )

    def get_available(self) -> bool:
        return self._projection is not None

    available = Property(bool, get_available, notify=changed)

    def get_source_row_count(self) -> int:
        return 0 if self._projection is None else self._projection.source_row_count

    sourceRowCount = Property(int, get_source_row_count, notify=changed)

    def get_eligible_row_count(self) -> int:
        return 0 if self._projection is None else self._projection.eligible_row_count

    eligibleRowCount = Property(int, get_eligible_row_count, notify=changed)

    def get_excluded_row_count(self) -> int:
        return 0 if self._projection is None else self._projection.excluded_row_count

    excludedRowCount = Property(int, get_excluded_row_count, notify=changed)

    def get_reference_context_required(self) -> bool:
        return bool(self._projection is not None and self._projection.reference_context_required)

    referenceContextRequired = Property(bool, get_reference_context_required, notify=changed)

    def get_reference_context_compatible(self) -> bool:
        return bool(self._projection is not None and self._projection.reference_context_compatible)

    referenceContextCompatible = Property(
        bool,
        get_reference_context_compatible,
        notify=changed,
    )

    def get_reference_policy(self) -> str:
        return "" if self._projection is None else self._projection.reference_policy

    referencePolicy = Property(str, get_reference_policy, notify=changed)

    def get_reference_backend(self) -> str:
        return "" if self._projection is None else self._projection.reference_backend

    referenceBackend = Property(str, get_reference_backend, notify=changed)

    def get_reference_backend_model(self) -> str:
        return "" if self._projection is None else self._projection.reference_backend_model

    referenceBackendModel = Property(str, get_reference_backend_model, notify=changed)

    semanticFields = Property(QObject, lambda self: self.semantic_fields, constant=True)
    referenceFields = Property(QObject, lambda self: self.reference_fields, constant=True)
    referenceContexts = Property(QObject, lambda self: self.reference_contexts, constant=True)
    exclusionReasons = Property(QObject, lambda self: self.exclusion_reasons, constant=True)
    categoryValues = Property(QObject, lambda self: self.category_values, constant=True)
    scenariosModel = Property(QObject, lambda self: self.scenarios, constant=True)
    partitionsModel = Property(QObject, lambda self: self.partitions, constant=True)
    transformationsModel = Property(QObject, lambda self: self.transformations, constant=True)
    leakageAudits = Property(QObject, lambda self: self.leakage_audits, constant=True)
    outputFormats = Property(QObject, lambda self: self.output_formats, constant=True)
    arrayFeasibility = Property(QObject, lambda self: self.array_feasibility, constant=True)
    arrayConversionErrors = Property(
        QObject, lambda self: self.array_conversion_errors, constant=True
    )
    arrayAuxiliaryShapes = Property(
        QObject, lambda self: self.array_auxiliary_shapes, constant=True
    )
    matrixDiagnostics = Property(QObject, lambda self: self.matrix_diagnostics, constant=True)
    baselineFeasibility = Property(QObject, lambda self: self.baseline_feasibility, constant=True)
    baselineEstimators = Property(QObject, lambda self: self.baseline_estimators, constant=True)
    dependencyReadiness = Property(QObject, lambda self: self.dependencies, constant=True)


@dataclass(frozen=True)
class WorkflowIssue:
    """One private, stable workflow issue projected to QML."""

    origin: IssueOrigin
    severity: IssueSeverity
    code: str
    message: str
    document_kind: str
    section: str
    field_id: str = ""
    item_key: str = ""
    nested_row: int = -1
    path: tuple[str | int, ...] = ()


class WorkflowIssueModel(QAbstractListModel):
    """Expose structured workflow issues through fixed QML model roles."""

    count_changed = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._issues: tuple[WorkflowIssue, ...] = ()

    @property
    def issues(self) -> tuple[WorkflowIssue, ...]:
        return self._issues

    def replace(self, issues: tuple[WorkflowIssue, ...]) -> bool:
        if issues == self._issues:
            return False
        previous_count = len(self._issues)
        self.beginResetModel()
        self._issues = issues
        self.endResetModel()
        if len(self._issues) != previous_count:
            self.count_changed.emit()
        return True

    def rowCount(
        self,
        _parent: QModelIndex | QPersistentModelIndex = INVALID_INDEX,
    ) -> int:
        return len(self._issues)

    def data(
        self,
        index: QModelIndex | QPersistentModelIndex,
        role: int = int(Qt.ItemDataRole.DisplayRole),
    ) -> object:
        if not index.isValid() or not 0 <= index.row() < len(self._issues):
            return None
        issue = self._issues[index.row()]
        values: dict[int, object] = {
            int(Qt.ItemDataRole.DisplayRole): issue.message,
            int(Qt.ItemDataRole.ToolTipRole): issue.message,
            ORIGIN_ROLE: issue.origin,
            SEVERITY_ROLE: issue.severity,
            CODE_ROLE: issue.code,
            MESSAGE_ROLE: issue.message,
            DOCUMENT_KIND_ROLE: issue.document_kind,
            SECTION_ROLE: issue.section,
            FIELD_ID_ROLE: issue.field_id,
            ITEM_KEY_ROLE: issue.item_key,
            NESTED_ROW_ROLE: issue.nested_row,
            PATH_ROLE: list(issue.path),
        }
        return values.get(role)

    def roleNames(self) -> dict[int, QByteArray]:
        return {
            ORIGIN_ROLE: QByteArray(b"origin"),
            SEVERITY_ROLE: QByteArray(b"severity"),
            CODE_ROLE: QByteArray(b"code"),
            MESSAGE_ROLE: QByteArray(b"message"),
            DOCUMENT_KIND_ROLE: QByteArray(b"documentKind"),
            SECTION_ROLE: QByteArray(b"section"),
            FIELD_ID_ROLE: QByteArray(b"fieldId"),
            ITEM_KEY_ROLE: QByteArray(b"itemKey"),
            NESTED_ROW_ROLE: QByteArray(b"nestedRow"),
            PATH_ROLE: QByteArray(b"path"),
        }

    def get_count(self) -> int:
        return len(self._issues)

    count = Property(int, get_count, notify=count_changed)
