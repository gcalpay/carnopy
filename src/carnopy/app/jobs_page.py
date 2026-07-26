from __future__ import annotations

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

from carnopy.app.activity_controller import ActivityController

RECORD_ID_ROLE = Qt.ItemDataRole.UserRole
RECOVERY_ROW_ROLE = Qt.ItemDataRole.UserRole


class JobsDiagnosticsPage(QWidget):
    """Display persisted GUI requests and opt-in stale-staging recovery."""

    def __init__(
        self,
        activity_controller: ActivityController,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.controller = activity_controller

        root = QVBoxLayout(self)
        heading = QLabel("Jobs and Diagnostics")
        heading.setStyleSheet("font-size: 18px; font-weight: bold;")
        root.addWidget(heading)
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_jobs_tab(), "Jobs")
        self.tabs.addTab(self._build_recovery_tab(), "Staging Recovery")
        root.addWidget(self.tabs, 1)

        activity_controller.state_changed.connect(self._controller_changed)
        self._controller_changed()

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
        self.recovery_list.itemChanged.connect(self._recovery_item_changed)
        layout.addWidget(self.recovery_list, 1)
        self.recovery_status = QLabel("Open a workspace to scan its output root.")
        self.recovery_status.setWordWrap(True)
        layout.addWidget(self.recovery_status)
        return page

    def refresh_jobs(self) -> None:
        selected = self.controller.get_selected_record_id()
        self.jobs_list.clear()
        for row_index, row in enumerate(self.controller.records_model.rows()):
            item = QListWidgetItem(_job_label(row))
            item.setData(RECORD_ID_ROLE, row["recordId"])
            item.setToolTip(str(row["issue"] or row["configurationPath"]))
            self.jobs_list.addItem(item)
            if row["recordId"] == selected:
                self.jobs_list.setCurrentRow(row_index)
        self.job_details.setPlainText(self.controller.get_selected_diagnostic_text())

    def _job_selected(self, current: QListWidgetItem | None, _previous: object) -> None:
        if current is None:
            self.job_details.clear()
            return
        record_id = str(current.data(RECORD_ID_ROLE))
        self.controller.select_record(record_id)
        self.job_details.setPlainText(self.controller.get_selected_diagnostic_text())

    def remove_selected_job(self) -> None:
        item = self.jobs_list.currentItem()
        if item is None:
            return
        record_id = str(item.data(RECORD_ID_ROLE))
        if not self.controller.select_record(record_id):
            return
        answer = QMessageBox.question(
            self,
            "Remove Activity Record?",
            "Remove this private activity record?\n\nGenerated runs and figures are not removed.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        if not self.controller.remove_selected_record():
            QMessageBox.warning(
                self,
                "Removal Failed",
                self.controller.get_selected_diagnostic_text(),
            )

    def refresh_recovery(self) -> None:
        self.controller.refresh_recovery()
        self._render_recovery()

    def _render_recovery(self) -> None:
        self.recovery_list.blockSignals(True)
        self.recovery_list.clear()
        for row_index, row in enumerate(self.controller.recovery_candidates_model.rows()):
            age_value = row["ageSeconds"]
            age_seconds = age_value if isinstance(age_value, (int, float)) else 0.0
            age_minutes = age_seconds / 60.0
            label = f"{row['name']} — {age_minutes:.1f} minutes old"
            if row["issue"]:
                label += f" — not removable: {row['issue']}"
            item = QListWidgetItem(label)
            item.setData(RECOVERY_ROW_ROLE, row_index)
            flags = item.flags() | Qt.ItemFlag.ItemIsUserCheckable
            if not bool(row["removable"]):
                flags &= ~Qt.ItemFlag.ItemIsEnabled
            item.setFlags(flags)
            item.setCheckState(
                Qt.CheckState.Checked if bool(row["selected"]) else Qt.CheckState.Unchecked
            )
            self.recovery_list.addItem(item)
        self.recovery_list.blockSignals(False)
        issue = self.controller.get_recovery_issue()
        if issue:
            self.recovery_status.setText(issue)
        else:
            count = self.controller.recovery_candidates_model.get_count()
            self.recovery_status.setText(
                f"Found {count} recognized staging candidate(s); "
                f"{self.controller.get_selected_recovery_count()} selected."
            )

    def remove_checked_staging(self) -> None:
        paths = self.controller.selected_recovery_paths()
        if not paths:
            self.recovery_status.setText("Check one or more staging directories first.")
            return
        answer = QMessageBox.question(
            self,
            "Remove Staging Directories?",
            f"Permanently remove {len(paths)} checked staging directories?\n\n"
            + "\n".join(str(path) for path in paths),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.controller.remove_selected_recovery()

    def _recovery_item_changed(self, item: QListWidgetItem) -> None:
        row = int(item.data(RECOVERY_ROW_ROLE))
        self.controller.set_recovery_selected(
            row,
            item.checkState() == Qt.CheckState.Checked,
        )

    def _controller_changed(self) -> None:
        self.refresh_jobs()
        self._render_recovery()


def _job_label(row: dict[str, object]) -> str:
    if not row["readable"]:
        return f"Unreadable — {row['recordId']}"
    return f"{row['stateLabel']} — {row['operation']} — {row['createdAtUtc']}"
