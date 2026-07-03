from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow.parquet as pq

from carnopy.app.source_inspection import ResolvedTable

MAX_PREVIEW_ROWS = 500


def preview_table(
    table: ResolvedTable,
    *,
    offset: int,
    limit: int,
) -> dict[str, Any]:
    if offset < 0:
        raise ValueError("preview offset must be non-negative")
    if limit < 1 or limit > MAX_PREVIEW_ROWS:
        raise ValueError(f"preview limit must be between 1 and {MAX_PREVIEW_ROWS}")
    if table.source_format == "parquet":
        total, columns, rows = _preview_parquet(table.path, offset=offset, limit=limit)
    elif table.source_format == "csv":
        total, columns, rows = _preview_csv(table.path, offset=offset, limit=limit)
    else:
        raise ValueError(f"unsupported preview table format: {table.source_format}")
    return {
        "table_id": table.table_id,
        "total_row_count": total,
        "block_offset": offset,
        "block_count": len(rows),
        "columns": [
            {"name": name, "dtype": dtype, "unit": table.units.get(name)} for name, dtype in columns
        ],
        "rows": [[_json_value(value) for value in row] for row in rows],
    }


def _preview_parquet(
    path: Path,
    *,
    offset: int,
    limit: int,
) -> tuple[int, list[tuple[str, str]], list[list[object]]]:
    parquet = pq.ParquetFile(path)  # type: ignore[no-untyped-call]
    total = parquet.metadata.num_rows
    columns = [(field.name, str(field.type)) for field in parquet.schema_arrow]
    if offset >= total:
        return total, columns, []

    rows: list[list[object]] = []
    column_names = [name for name, _dtype in columns]
    row_group_start = 0
    for row_group in range(parquet.num_row_groups):
        row_group_count = parquet.metadata.row_group(row_group).num_rows
        row_group_end = row_group_start + row_group_count
        if row_group_end <= offset:
            row_group_start = row_group_end
            continue
        local_skip = max(0, offset - row_group_start)
        consumed = 0
        for batch in parquet.iter_batches(  # type: ignore[no-untyped-call]
            batch_size=MAX_PREVIEW_ROWS,
            row_groups=[row_group],
        ):
            batch_end = consumed + batch.num_rows
            if batch_end <= local_skip:
                consumed = batch_end
                continue
            start = max(0, local_skip - consumed)
            take = min(batch.num_rows - start, limit - len(rows))
            if take > 0:
                rows.extend(
                    [item.get(name) for name in column_names]
                    for item in batch.slice(start, take).to_pylist()
                )
            consumed = batch_end
            if len(rows) >= limit:
                return total, columns, rows
        row_group_start = row_group_end
    return total, columns, rows


def _preview_csv(
    path: Path,
    *,
    offset: int,
    limit: int,
) -> tuple[int, list[tuple[str, str]], list[list[object]]]:
    with path.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.reader(stream)
        try:
            next(reader)
        except StopIteration:
            return 0, [], []
        total = sum(1 for _row in reader)
    if offset >= total:
        header = pd.read_csv(path, nrows=0)
        return total, [(str(name), str(dtype)) for name, dtype in header.dtypes.items()], []

    selected: list[pd.DataFrame] = []
    selected_count = 0
    position = 0
    for chunk in pd.read_csv(path, chunksize=MAX_PREVIEW_ROWS):
        end = position + len(chunk)
        if end <= offset:
            position = end
            continue
        start = max(0, offset - position)
        take = min(len(chunk) - start, limit - selected_count)
        if take > 0:
            selected.append(chunk.iloc[start : start + take])
            selected_count += take
        position = end
        if selected_count >= limit:
            break
    frame = pd.concat(selected, ignore_index=True) if selected else pd.DataFrame()
    columns = [(str(name), str(dtype)) for name, dtype in frame.dtypes.items()]
    return total, columns, frame.astype(object).values.tolist()


def _json_value(value: object) -> object:
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    item = getattr(value, "item", None)
    if callable(item):
        value = item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)
