from __future__ import annotations

from typing import Any

from carnopy._execution import ExecutionControl
from carnopy.backends.base import PropertyBackend
from carnopy.config.models import NormalizedConfig
from carnopy.generation.common import (
    assign_case_ids,
    base_row,
    evaluate_phase,
    evaluate_properties,
    finalize_row,
)


def generate_property_table(
    config: NormalizedConfig,
    backend: PropertyBackend,
    run_id: str,
    *,
    execution: ExecutionControl | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for fluid in config.fluids:
        for temperature in config.grid["temperature"]:
            for pressure in config.grid["pressure"]:
                if execution is not None:
                    execution.raise_if_cancelled()
                row = base_row(
                    run_id=run_id,
                    mode=config.mode,
                    fluid=fluid,
                    backend=backend,
                )
                row["temperature_K"] = temperature
                row["pressure_Pa"] = pressure
                failures = evaluate_phase(
                    row,
                    backend=backend,
                    fluid=fluid,
                    input1="T",
                    value1=temperature,
                    input2="P",
                    value2=pressure,
                )
                failures.extend(
                    evaluate_properties(
                        row,
                        backend=backend,
                        mode=config.mode,
                        fluid=fluid,
                        input1="T",
                        value1=temperature,
                        input2="P",
                        value2=pressure,
                        properties=config.properties,
                    )
                )
                rows.append(finalize_row(row, failures))
                if execution is not None:
                    execution.checkpoint(len(rows), config.projected_rows)
    assign_case_ids(rows)
    return rows
