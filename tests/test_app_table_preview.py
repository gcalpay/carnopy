from __future__ import annotations

import math
import os
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import Qt

from carnopy.app.source_inspection import ResolvedTable
from carnopy.app.table_model import PreviewTableModel
from carnopy.app.table_preview import preview_table
from carnopy.provenance import sha256_file


def _resolved(path: Path, *, units: dict[str, str] | None = None) -> ResolvedTable:
    return ResolvedTable(
        table_id="dataset",
        label="Dataset",
        path=path,
        source_format=path.suffix.removeprefix("."),
        units=units or {},
        sha256=sha256_file(path),
    )


def test_parquet_preview_reads_bounded_ordered_blocks_without_pandas_full_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "table.parquet"
    frame = pd.DataFrame(
        {
            "case_id": range(1_200),
            "value": [float(index) for index in range(1_200)],
        }
    )
    frame.loc[503, "value"] = math.nan
    pq.write_table(pa.Table.from_pandas(frame), path, row_group_size=200)
    monkeypatch.setattr(pd, "read_parquet", lambda *_args, **_kwargs: pytest.fail("full read"))

    payload = preview_table(
        _resolved(path, units={"value": "Pa"}),
        offset=500,
        limit=500,
    )

    assert payload["total_row_count"] == 1_200
    assert payload["block_count"] == 500
    assert payload["rows"][0] == [500, 500.0]
    assert payload["rows"][3] == [503, None]
    assert payload["rows"][-1] == [999, 999.0]
    assert payload["columns"][1]["unit"] == "Pa"


def test_csv_preview_scans_in_bounded_chunks_and_preserves_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "table.csv"
    pd.DataFrame({"case_id": range(1_200), "label": [f"row-{i}" for i in range(1_200)]}).to_csv(
        path,
        index=False,
    )
    original = pd.read_csv
    calls: list[dict[str, object]] = []

    def recorded(*args: object, **kwargs: object) -> object:
        calls.append(dict(kwargs))
        return original(*args, **kwargs)

    monkeypatch.setattr(pd, "read_csv", recorded)

    payload = preview_table(_resolved(path), offset=500, limit=500)

    assert payload["rows"][0] == [500, "row-500"]
    assert payload["rows"][-1] == [999, "row-999"]
    assert calls and all(call.get("chunksize") == 500 for call in calls)


def test_preview_limits_are_strict(tmp_path: Path) -> None:
    path = tmp_path / "table.csv"
    path.write_text("value\n1\n", encoding="utf-8")
    table = _resolved(path)

    with pytest.raises(ValueError, match="between 1 and 500"):
        preview_table(table, offset=0, limit=501)
    with pytest.raises(ValueError, match="non-negative"):
        preview_table(table, offset=-1, limit=1)


def test_preview_model_pages_locally_and_shows_units() -> None:
    model = PreviewTableModel()
    model.set_block(
        {
            "columns": [{"name": "pressure_Pa", "dtype": "double", "unit": "Pa"}],
            "rows": [[index] for index in range(500)],
            "total_row_count": 550,
            "block_offset": 0,
        },
        page_offset=0,
    )

    assert model.rowCount() == 100
    assert model.headerData(0, Qt.Orientation.Horizontal) == "pressure_Pa [Pa]"
    assert model.headerData(0, Qt.Orientation.Vertical) == "0"
    model.set_page(400)
    assert model.rowCount() == 100
    assert model.contains_page(400)
    assert not model.contains_page(500)
