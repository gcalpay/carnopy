from __future__ import annotations

import math
from typing import Any

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

SATURATION_RTOL = 1e-10
TEMPERATURE_ATOL_K = 1e-8
PRESSURE_ATOL_PA = 1e-3


def generate_saturation_table(
    config: NormalizedConfig,
    backend: PropertyBackend,
    run_id: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    input_axis = next(iter(config.grid))
    input_key = "T" if input_axis == "temperature" else "P"
    output_key = "P" if input_axis == "temperature" else "T"

    for fluid in config.fluids:
        for coordinate in config.grid[input_axis]:
            pair_rows: list[dict[str, Any]] = []
            pair_failures: list[list[RowFailure]] = []
            computed_coordinates: list[float | None] = []
            for fraction, endpoint in (
                (0.0, "saturated_liquid"),
                (1.0, "saturated_vapor"),
            ):
                row = base_row(
                    run_id=run_id,
                    mode=config.mode,
                    fluid=fluid,
                    backend=backend,
                )
                row["vapor_mass_fraction"] = fraction
                row["saturation_endpoint"] = endpoint
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
                computed_coordinates.append(computed)
                if input_axis == "temperature":
                    row["temperature_K"] = coordinate
                    row["pressure_Pa"] = computed
                else:
                    row["pressure_Pa"] = coordinate
                    row["temperature_K"] = computed
                failures.extend(
                    evaluate_phase(
                        row,
                        backend=backend,
                        fluid=fluid,
                        input1=input_key,
                        value1=coordinate,
                        input2="Q",
                        value2=fraction,
                        forced_phase=endpoint,
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
                pair_rows.append(row)
                pair_failures.append(failures)

            first, second = computed_coordinates
            if first is not None and second is not None:
                atol = PRESSURE_ATOL_PA if input_axis == "temperature" else TEMPERATURE_ATOL_K
                if not math.isclose(
                    first,
                    second,
                    rel_tol=SATURATION_RTOL,
                    abs_tol=atol,
                ):
                    mismatch = RowFailure(
                        layer="state",
                        code="saturation_endpoint_mismatch",
                        message=(
                            "CoolProp saturation endpoints disagree on their shared coordinate"
                        ),
                    )
                    pair_failures[0].insert(0, mismatch)
                    pair_failures[1].insert(0, mismatch)
            for row, failures in zip(pair_rows, pair_failures, strict=True):
                rows.append(finalize_row(row, failures))
    assign_case_ids(rows)
    return rows
