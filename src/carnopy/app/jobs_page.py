from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from carnopy.app.config_document import SavedConfigSnapshot
from carnopy.app.execution_page import DatasetExecutionPage
from carnopy.app.jobs import JobStore, LoadedJob
from carnopy.app.protocol import WorkerEvent
from carnopy.app.recovery import (
    StagingCandidate,
    remove_staging_candidate,
    scan_staging_candidates,
)
from carnopy.app.workspace import Workspace

JOB_PATH_ROLE = Qt.ItemDataRole.UserRole
STAGING_ROLE = Qt.ItemDataRole.UserRole


class JobsDiagnosticsPage(QWidget):
    """Display persisted GUI requests and opt-in stale-staging recovery."""

    def __init__(
        self,
        execution_page: DatasetExecutionPage,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.execution_page = execution_page
        self.workspace: Workspace | None = None
        self.store: JobStore | None = None
        self._active_record: dict[str, Any] | None = None

        root = QVBoxLayout(self)
        heading = QLabel("Jobs and Diagnostics")
        heading.setStyleSheet("font-size: 18px; font-weight: bold;")
        root.addWidget(heading)
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_jobs_tab(), "Jobs")
        self.tabs.addTab(self._build_recovery_tab(), "Staging Recovery")
        root.addWidget(self.tabs, 1)

        execution_page.request_started.connect(self._request_started)
        execution_page.request_event.connect(self._event_received)
        execution_page.request_terminal.connect(self._request_terminal)

    def _build_jobs_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        actions = QHBoxLayout()
        refresh = QPushButton("Refresh")
        remove = QPushButton("Remove Selected Record…")
        refresh.clicked.connect(self.refresh_jobs)
        remove.clicked.connect(self.remove_selected_job)
        actions.addWidget(refresh)
        actions.addWidget(remove)
        actions.addStretch(1)
        layout.addLayout(actions)
        self.jobs_list = QListWidget()
        self.jobs_list.currentItemChanged.connect(self._job_selected)
        layout.addWidget(self.jobs_list, 1)
        self.job_details = QPlainTextEdit()
        self.job_details.setReadOnly(True)
        self.job_details.setAccessibleName("Job diagnostic details")
        layout.addWidget(self.job_details, 1)
        return page

    def _build_recovery_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(
            QLabel(
                "Only recognized direct staging directories are shown. Nothing is selected "
                "or removed automatically."
            )
        )
        actions = QHBoxLayout()
        scan = QPushButton("Rescan")
        remove = QPushButton("Remove Checked…")
        scan.clicked.connect(self.refresh_recovery)
        remove.clicked.connect(self.remove_checked_staging)
        actions.addWidget(scan)
        actions.addWidget(remove)
        actions.addStretch(1)
        layout.addLayout(actions)
        self.recovery_list = QListWidget()
        layout.addWidget(self.recovery_list, 1)
        self.recovery_status = QLabel("Open a workspace to scan its output root.")
        self.recovery_status.setWordWrap(True)
        layout.addWidget(self.recovery_status)
        return page

    def set_workspace(self, workspace: Workspace | None) -> None:
        self.workspace = workspace
        self.store = None if workspace is None else JobStore(workspace.private_directory)
        self._active_record = None
        self.refresh_jobs()
        self.refresh_recovery()

    def refresh_jobs(self) -> None:
        self.jobs_list.clear()
        self.job_details.clear()
        if self.store is None:
            return
        for loaded in self.store.load():
            item = QListWidgetItem(_job_label(loaded))
            item.setData(JOB_PATH_ROLE, str(loaded.path))
            item.setToolTip(loaded.error or str(loaded.path))
            self.jobs_list.addItem(item)

    def _job_selected(self, current: QListWidgetItem | None, _previous: object) -> None:
        if current is None:
            self.job_details.clear()
            return
        path = Path(str(current.data(JOB_PATH_ROLE)))
        try:
            text = path.read_text(encoding="utf-8")
            value = json.loads(text)
        except (OSError, json.JSONDecodeError) as exc:
            self.job_details.setPlainText(f"Unreadable job record: {exc}")
            return
        self.job_details.setPlainText(json.dumps(value, indent=2, sort_keys=True))

    def remove_selected_job(self) -> None:
        item = self.jobs_list.currentItem()
        store = self.store
        if item is None or store is None:
            return
        path = Path(str(item.data(JOB_PATH_ROLE)))
        answer = QMessageBox.question(
            self,
            "Remove Job Record?",
            f"Remove this GUI diagnostic record?\n\n{path}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            store.remove(path)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Removal Failed", str(exc))
        self.refresh_jobs()

    def refresh_recovery(self) -> None:
        self.recovery_list.clear()
        workspace = self.workspace
        if workspace is None:
            self.recovery_status.setText("Open a workspace to scan its output root.")
            return
        candidates = scan_staging_candidates(workspace.outputs)
        for candidate in candidates:
            age_minutes = candidate.age_seconds / 60.0
            label = f"{candidate.path.name} — {age_minutes:.1f} minutes old"
            if candidate.issue:
                label += f" — not removable: {candidate.issue}"
            item = QListWidgetItem(label)
            item.setData(STAGING_ROLE, candidate)
            flags = item.flags() | Qt.ItemFlag.ItemIsUserCheckable
            if not candidate.removable:
                flags &= ~Qt.ItemFlag.ItemIsEnabled
            item.setFlags(flags)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.recovery_list.addItem(item)
        self.recovery_status.setText(f"Found {len(candidates)} recognized staging candidate(s).")

    def remove_checked_staging(self) -> None:
        workspace = self.workspace
        if workspace is None:
            return
        candidates = [
            cast(StagingCandidate, self.recovery_list.item(index).data(STAGING_ROLE))
            for index in range(self.recovery_list.count())
            if self.recovery_list.item(index).checkState() == Qt.CheckState.Checked
        ]
        if not candidates:
            self.recovery_status.setText("Check one or more staging directories first.")
            return
        answer = QMessageBox.question(
            self,
            "Remove Staging Directories?",
            f"Permanently remove {len(candidates)} checked staging directories?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        errors: list[str] = []
        for candidate in candidates:
            try:
                remove_staging_candidate(candidate, workspace.outputs)
            except (OSError, ValueError) as exc:
                errors.append(f"{candidate.path.name}: {exc}")
        self.refresh_recovery()
        if errors:
            self.recovery_status.setText("; ".join(errors))

    def _request_started(self, value: object) -> None:
        store = self.store
        workspace = self.workspace
        payload = cast(dict[str, Any], value)
        snapshot = payload.get("snapshot")
        if store is None or workspace is None or not isinstance(snapshot, SavedConfigSnapshot):
            return
        try:
            relative = snapshot.path.relative_to(workspace.root).as_posix()
        except ValueError:
            return
        self._active_record = store.start(
            request_id=str(payload["request_id"]),
            operation=str(payload["operation"]),
            config_relative_path=relative,
            yaml_snapshot=snapshot.yaml_bytes.decode("utf-8"),
            config_sha256=snapshot.sha256,
        )
        self.refresh_jobs()

    def _event_received(self, value: object) -> None:
        record = self._active_record
        store = self.store
        event = cast(WorkerEvent, value)
        if record is None or store is None or str(event.request_id) != record["request_id"]:
            return
        if event.type in {"phase", "progress"}:
            store.update_event(record, event.type, event.payload)

    def _request_terminal(self, value: object) -> None:
        record = self._active_record
        store = self.store
        envelope = cast(dict[str, Any], value)
        if record is None or store is None or envelope.get("request_id") != record["request_id"]:
            return
        store.finish(record, envelope)
        self._active_record = None
        self.refresh_jobs()
        if envelope.get("force_stopped"):
            self.refresh_recovery()


def _job_label(loaded: LoadedJob) -> str:
    if loaded.data is None:
        return f"Unreadable — {loaded.path.name}"
    return (
        f"{loaded.data.get('status', 'unknown')} — "
        f"{loaded.data.get('operation', 'unknown')} — "
        f"{loaded.data.get('created_at_utc', 'unknown time')}"
    )
