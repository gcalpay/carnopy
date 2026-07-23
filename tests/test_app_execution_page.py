from __future__ import annotations

import os
from pathlib import Path
from typing import cast

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from carnopy.app.execution_controller import DatasetExecutionController
from carnopy.app.execution_page import DatasetExecutionPage
from carnopy.app.workspace import Workspace, initialize_workspace


class StubCoordinator(QObject):
    def __init__(self) -> None:
        super().__init__()
        self.is_busy = False


class StubExecutionController(QObject):
    state_changed = Signal()
    run_finalized = Signal(object)

    def __init__(self, workspace: Workspace, config: Path) -> None:
        super().__init__()
        self.coordinator = StubCoordinator()
        self.workspace = workspace
        self.snapshot_path = str(config)
        self.snapshot_sha = "a" * 64
        self.snapshot_issue = ""
        self.operation = ""
        self.state = "ready"
        self.phase = ""
        self.completed = 0
        self.total = 0
        self.output = ""
        self.run_status = ""
        self.rows = 0
        self.valid_rows = 0
        self.invalid_rows = 0
        self.visualization_status = ""
        self.mode = ""
        self.projected_rows = 0
        self.backend_model = ""
        self.failure_code = ""
        self.failure_message = ""
        self.can_cancel = False
        self.can_force_stop = False
        self.calls: list[str] = []

    @property
    def owns_active_request(self) -> bool:
        return self.state in {"starting", "running", "cancellation_requested"}

    def validate(self) -> bool:
        self.calls.append("validate")
        return True

    def generate(self) -> bool:
        self.calls.append("generate")
        return True

    def cancel(self) -> bool:
        self.calls.append("cancel")
        return self.can_cancel

    def force_stop(self) -> bool:
        self.calls.append("force_stop")
        return self.can_force_stop

    def get_snapshot_available(self) -> bool:
        return bool(self.snapshot_path)

    def get_snapshot_path(self) -> str:
        return self.snapshot_path

    def get_snapshot_sha256(self) -> str:
        return self.snapshot_sha

    def get_snapshot_issue(self) -> str:
        return self.snapshot_issue

    def get_operation(self) -> str:
        return self.operation

    def get_state(self) -> str:
        return self.state

    def get_phase(self) -> str:
        return self.phase

    def get_completed_rows(self) -> int:
        return self.completed

    def get_total_rows(self) -> int:
        return self.total

    def get_can_validate(self) -> bool:
        return self.state == "ready"

    def get_can_generate(self) -> bool:
        return self.state == "ready"

    def get_can_cancel(self) -> bool:
        return self.can_cancel

    def get_can_force_stop(self) -> bool:
        return self.can_force_stop

    def get_result_output_directory(self) -> str:
        return self.output

    def get_result_mode(self) -> str:
        return self.mode

    def get_result_projected_rows(self) -> int:
        return self.projected_rows

    def get_result_backend_model(self) -> str:
        return self.backend_model

    def get_result_visualization_status(self) -> str:
        return self.visualization_status

    def get_result_run_status(self) -> str:
        return self.run_status

    def get_result_row_count(self) -> int:
        return self.rows

    def get_result_valid_row_count(self) -> int:
        return self.valid_rows

    def get_result_invalid_row_count(self) -> int:
        return self.invalid_rows

    def get_failure_code(self) -> str:
        return self.failure_code

    def get_failure_message(self) -> str:
        return self.failure_message


@pytest.fixture(scope="module")
def application() -> QApplication:
    existing = QApplication.instance()
    app = existing if isinstance(existing, QApplication) else QApplication([])
    yield app


def page_for(tmp_path: Path) -> tuple[DatasetExecutionPage, StubExecutionController]:
    workspace = initialize_workspace(tmp_path / "workspace")
    config = workspace.configs / "dataset.yaml"
    config.write_text("schema_version: 2\n", encoding="utf-8")
    controller = StubExecutionController(workspace, config)
    page = DatasetExecutionPage(cast(DatasetExecutionController, controller))
    return page, controller


def test_execution_page_is_a_view_over_one_controller(
    tmp_path: Path,
    application: QApplication,
) -> None:
    del application
    page, controller = page_for(tmp_path)

    page.generate_button.click()
    page.validate_button.click()

    assert controller.calls == ["generate", "validate"]
    assert page.coordinator is controller.coordinator
    assert str(controller.workspace.outputs) in page.command.toPlainText()
    assert controller.snapshot_sha in page.config_label.text()


def test_execution_page_projects_progress_and_generation_result(
    tmp_path: Path,
    application: QApplication,
) -> None:
    del application
    page, controller = page_for(tmp_path)
    run = controller.workspace.outputs / "run"
    finalized: list[Path] = []
    page.run_finalized.connect(finalized.append)

    controller.operation = "generate"
    controller.state = "running"
    controller.phase = "generation"
    controller.completed = 7
    controller.total = 10
    controller.state_changed.emit()

    assert page.progress.value() == 7
    assert page.progress.maximum() == 10
    assert page.phase_label.text() == "Phase: generation"

    controller.state = "succeeded"
    controller.output = str(run)
    controller.run_status = "completed_with_invalid_rows"
    controller.rows = 10
    controller.valid_rows = 9
    controller.invalid_rows = 1
    controller.state_changed.emit()
    controller.run_finalized.emit(run)

    assert "9 valid" in page.result.text()
    assert page.inspect_button.isEnabled()
    assert finalized == [run]


def test_execution_page_projects_controller_cancel_and_force_policy(
    tmp_path: Path,
    application: QApplication,
) -> None:
    del application
    page, controller = page_for(tmp_path)
    controller.state = "running"
    controller.can_cancel = True
    controller.state_changed.emit()

    page.cancel_button.click()

    assert controller.calls == ["cancel"]
    controller.can_cancel = False
    controller.can_force_stop = True
    controller.state_changed.emit()
    assert not page.force_stop_button.isHidden()

    page.force_stop_button.click()

    assert controller.calls == ["cancel", "force_stop"]
