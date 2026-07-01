from __future__ import annotations

from typing import Any

from carnopy._execution import ExecutionControl
from carnopy.backends.base import PropertyBackend
from carnopy.config.models import NormalizedConfig
from carnopy.generation.common import (
    RowFailure,
    assign_case_ids,
    base_row,
    evaluate_phase,
    evaluate_properties,
    finalize_row,
)


def generate_vapor_mass_fraction_table(
    config: NormalizedConfig,
    backend: PropertyBackend,
    run_id: str,
    *,
    execution: ExecutionControl | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    coordinate_axis = "temperature" if "temperature" in config.grid else "pressure"
    input_key = "T" if coordinate_axis == "temperature" else "P"
    output_key = "P" if coordinate_axis == "temperature" else "T"

    for fluid in config.fluids:
        for coordinate in config.grid[coordinate_axis]:
            for fraction in config.grid["vapor_mass_fraction"]:
                if execution is not None:
                    execution.raise_if_cancelled()
                row = base_row(
                    run_id=run_id,
                    mode=config.mode,
                    fluid=fluid,
                    backend=backend,
                )
                row["vapor_mass_fraction"] = fraction
                coordinate_result = backend.property(
                    output_key,
                    fluid,
                    input_key,
                    coordinate,
                    "Q",
                    fraction,
                )
                failures: list[RowFailure] = []
                if coordinate_result.valid and coordinate_result.value is not None:
                    computed = coordinate_result.value
                else:
                    computed = None
                    failures.append(
                        RowFailure(
                            layer="domain",
                            code="outside_saturation_domain",
                            message="could not evaluate the missing saturation coordinate",
                            backend_error_type=coordinate_result.backend_error_type,
                            backend_error_message=coordinate_result.backend_error_message,
                        )
                    )
                if coordinate_axis == "temperature":
                    row["temperature_K"] = coordinate
                    row["pressure_Pa"] = computed
                else:
                    row["pressure_Pa"] = coordinate
                    row["temperature_K"] = computed
                forced_phase = (
                    "saturated_liquid"
                    if fraction == 0.0
                    else "saturated_vapor"
                    if fraction == 1.0
                    else "two_phase"
                )
                failures.extend(
                    evaluate_phase(
                        row,
                        backend=backend,
                        fluid=fluid,
                        input1=input_key,
                        value1=coordinate,
                        input2="Q",
                        value2=fraction,
                        forced_phase=forced_phase,
                    )
                )
                failures.extend(
                    evaluate_properties(
                        row,
                        backend=backend,
                        mode=config.mode,
                        fluid=fluid,
                        input1=input_key,
                        value1=coordinate,
                        input2="Q",
                        value2=fraction,
                        properties=config.properties,
                    )
                )
                rows.append(finalize_row(row, failures))
                if execution is not None:
                    execution.checkpoint(len(rows), config.projected_rows)
    assign_case_ids(rows)
    return rows
