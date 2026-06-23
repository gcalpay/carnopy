from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from carnopy.backends.base import PropertyBackend
from carnopy.domain.failures import BackendResult, FailureLayer
from carnopy.domain.phases import normalize_phase
from carnopy.domain.properties import PROPERTY_REGISTRY, PropertyDefinition


@dataclass(frozen=True)
class RowFailure:
    layer: FailureLayer
    code: str
    message: str
    property_name: str | None = None
    backend_error_type: str | None = None
    backend_error_message: str | None = None

    @classmethod
    def from_result(
        cls,
        result: BackendResult[Any],
        *,
        property_name: str | None = None,
    ) -> RowFailure:
        return cls(
            layer=result.failure_layer or "backend",
            code=result.failure_code or "backend_property_call_failed",
            message=result.failure_message or "backend evaluation failed",
            property_name=property_name,
            backend_error_type=result.backend_error_type,
            backend_error_message=result.backend_error_message,
        )


def base_row(
    *,
    run_id: str,
    mode: str,
    fluid: str,
    backend: PropertyBackend,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "case_id": -1,
        "mode": mode,
        "fluid": fluid,
        "backend": backend.name,
        "backend_model": backend.model,
        "backend_version": backend.version,
        "phase": None,
        "backend_phase": None,
    }


def evaluate_phase(
    row: dict[str, Any],
    *,
    backend: PropertyBackend,
    fluid: str,
    input1: str,
    value1: float,
    input2: str,
    value2: float,
    forced_phase: str | None = None,
) -> list[RowFailure]:
    result = backend.phase(fluid, input1, value1, input2, value2)
    if not result.valid or result.value is None:
        row["phase"] = forced_phase or "unknown"
        return [RowFailure.from_result(result)]
    row["backend_phase"] = result.value
    row["phase"] = forced_phase or normalize_phase(result.value)
    if row["phase"] == "unknown":
        return [
            RowFailure(
                layer="state",
                code="phase_evaluation_failed",
                message=f"unrecognized backend phase {result.value!r}",
            )
        ]
    return []


def evaluate_properties(
    row: dict[str, Any],
    *,
    backend: PropertyBackend,
    mode: str,
    fluid: str,
    input1: str,
    value1: float,
    input2: str,
    value2: float,
    properties: list[str],
) -> list[RowFailure]:
    failures: list[RowFailure] = []
    cache: dict[str, BackendResult[float]] = {}

    def evaluate(name: str) -> BackendResult[float]:
        cached = cache.get(name)
        if cached is not None:
            return cached
        definition = PROPERTY_REGISTRY[name]
        if definition.classification == "derived":
            result = _evaluate_derived(definition, evaluate)
        elif definition.classification == "fluid_constant":
            assert definition.backend_key is not None
            result = backend.fluid_constant(definition.backend_key, fluid)
        elif definition.classification == "mode_limited" and mode == "property_table":
            result = BackendResult.failure(
                layer="domain",
                code="unsupported_property_region",
                message=(
                    f"{name} is only defined for a liquid-vapor interface and is "
                    "unsupported in property_table"
                ),
            )
        else:
            assert definition.backend_key is not None
            result = backend.property(
                definition.backend_key,
                fluid,
                input1,
                value1,
                input2,
                value2,
            )
            if definition.classification == "mode_limited" and not result.valid:
                result = BackendResult(
                    value=None,
                    valid=False,
                    failure_layer="domain",
                    failure_code="unsupported_property_region",
                    failure_message=f"{name} is unsupported for this state",
                    backend_error_type=result.backend_error_type,
                    backend_error_message=result.backend_error_message,
                )
        cache[name] = result
        return result

    for property_name in properties:
        definition = PROPERTY_REGISTRY[property_name]
        result = evaluate(property_name)
        row[definition.column] = result.value
        if not result.valid:
            failures.append(RowFailure.from_result(result, property_name=property_name))
    return failures


def finalize_row(row: dict[str, Any], failures: list[RowFailure]) -> dict[str, Any]:
    row["valid"] = not failures
    if not failures:
        row.update(
            {
                "failure_layer": None,
                "failure_code": None,
                "failure_message": None,
                "failure_property": None,
                "backend_error_type": None,
                "backend_error_message": None,
            }
        )
        return row
    primary = failures[0]
    row.update(
        {
            "failure_layer": primary.layer,
            "failure_code": primary.code,
            "failure_message": primary.message,
            "failure_property": primary.property_name,
            "backend_error_type": primary.backend_error_type,
            "backend_error_message": primary.backend_error_message,
        }
    )
    return row


def assign_case_ids(rows: list[dict[str, Any]]) -> None:
    for case_id, row in enumerate(rows):
        row["case_id"] = case_id


def _evaluate_derived(
    definition: PropertyDefinition,
    evaluate: Any,
) -> BackendResult[float]:
    dependency_results = {
        dependency: evaluate(dependency) for dependency in definition.dependencies
    }
    failed = next(
        (result for result in dependency_results.values() if not result.valid),
        None,
    )
    if failed is not None:
        return BackendResult(
            value=None,
            valid=False,
            failure_layer=failed.failure_layer,
            failure_code="derived_property_dependency_failed",
            failure_message=(
                f"could not evaluate dependencies for derived property {definition.name}"
            ),
            backend_error_type=failed.backend_error_type,
            backend_error_message=failed.backend_error_message,
        )
    if definition.name == "kinematic_viscosity":
        dynamic = dependency_results["dynamic_viscosity"].value
        density = dependency_results["mass_density"].value
        assert dynamic is not None
        assert density is not None
        if density == 0.0:
            return BackendResult.failure(
                layer="state",
                code="derived_property_dependency_failed",
                message="mass density is zero",
            )
        return BackendResult.success(dynamic / density)
    raise ValueError(f"unsupported derived property {definition.name}")
