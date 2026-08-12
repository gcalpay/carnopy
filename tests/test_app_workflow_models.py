from __future__ import annotations

import os
import subprocess
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import Qt

from carnopy.app.workflow_models import (
    CODE_ROLE,
    DOCUMENT_KIND_ROLE,
    FIELD_ID_ROLE,
    ITEM_KEY_ROLE,
    MESSAGE_ROLE,
    NESTED_ROW_ROLE,
    ORIGIN_ROLE,
    PATH_ROLE,
    SECTION_ROLE,
    SEVERITY_ROLE,
    WorkflowIssue,
    WorkflowIssueModel,
    WorkflowListModel,
)


def test_workflow_issue_model_exposes_stable_typed_roles() -> None:
    issue = WorkflowIssue(
        origin="schema",
        severity="blocking",
        code="invalid_filter",
        message="A filter value is invalid.",
        document_kind="model_sweep",
        section="comparison_plots",
        field_id="sweep.comparison.active.filters",
        item_key="density-comparison",
        nested_row=2,
        path=("comparison_plots", "plots", 0, "filters", "pressure"),
    )
    model = WorkflowIssueModel()
    count_changes: list[None] = []
    model.count_changed.connect(lambda: count_changes.append(None))

    assert model.replace((issue,))
    assert model.get_count() == 1
    assert count_changes == [None]
    assert not model.replace((issue,))
    index = model.index(0, 0)
    assert model.data(index, int(Qt.ItemDataRole.DisplayRole)) == issue.message
    assert model.data(index, ORIGIN_ROLE) == "schema"
    assert model.data(index, SEVERITY_ROLE) == "blocking"
    assert model.data(index, CODE_ROLE) == "invalid_filter"
    assert model.data(index, MESSAGE_ROLE) == issue.message
    assert model.data(index, DOCUMENT_KIND_ROLE) == "model_sweep"
    assert model.data(index, SECTION_ROLE) == "comparison_plots"
    assert model.data(index, FIELD_ID_ROLE) == "sweep.comparison.active.filters"
    assert model.data(index, ITEM_KEY_ROLE) == "density-comparison"
    assert model.data(index, NESTED_ROW_ROLE) == 2
    assert model.data(index, PATH_ROLE) == [
        "comparison_plots",
        "plots",
        0,
        "filters",
        "pressure",
    ]
    assert {bytes(name).decode("utf-8") for name in model.roleNames().values()} == {
        "origin",
        "severity",
        "code",
        "message",
        "documentKind",
        "section",
        "fieldId",
        "itemKey",
        "nestedRow",
        "path",
    }


def test_workflow_issue_model_count_changes_only_when_length_changes() -> None:
    model = WorkflowIssueModel()
    changes: list[None] = []
    model.count_changed.connect(lambda: changes.append(None))
    first = WorkflowIssue(
        origin="local",
        severity="blocking",
        code="first",
        message="First",
        document_kind="preparation",
        section="plan",
    )
    replacement = WorkflowIssue(
        origin="plan",
        severity="advisory",
        code="replacement",
        message="Replacement",
        document_kind="preparation",
        section="plan",
    )

    assert model.replace((first,))
    assert model.replace((replacement,))
    assert changes == [None]
    assert model.issues == (replacement,)
    assert model.replace(())
    assert changes == [None, None]


def test_workflow_list_model_exposes_only_declared_detached_roles() -> None:
    model = WorkflowListModel(("name", "summary"))
    count_changes: list[None] = []
    model.count_changed.connect(lambda: count_changes.append(None))
    source = {"name": "first", "summary": "Initial", "ignored": "private"}

    assert model.replace((source,))
    source["name"] = "mutated"

    assert model.get_count() == 1
    assert model.get(0) == {"name": "first", "summary": "Initial"}
    assert model.rows() == ({"name": "first", "summary": "Initial"},)
    assert count_changes == [None]
    assert not model.replace(({"name": "first", "summary": "Initial"},))
    assert model.replace(({"name": "first", "summary": "Updated"},))
    assert count_changes == [None]
    assert model.clear()
    assert count_changes == [None, None]


def test_workflow_list_model_detaches_nested_row_values() -> None:
    model = WorkflowListModel(("values",))
    source = {"values": ["original"]}
    assert model.replace((source,))

    source["values"].append("source mutation")
    projected = model.get(0)
    projected["values"].append("consumer mutation")

    assert model.get(0) == {"values": ["original"]}


def test_workflow_models_import_is_qtcore_only_and_scientifically_isolated() -> None:
    code = """
import sys
import carnopy.app.workflow_models
for name in (
    "PySide6.QtWidgets", "CoolProp", "numpy", "pandas", "pyarrow", "matplotlib",
    "carnopy.cli", "carnopy.pipeline",
):
    if name in sys.modules:
        raise SystemExit(name)
"""
    completed = subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
