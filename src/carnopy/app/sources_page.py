from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from carnopy.app.workspace import Workspace

SOURCE_PATH_ROLE = Qt.ItemDataRole.UserRole


@dataclass(frozen=True)
class SourceCandidate:
    path: Path
    kind_hint: str


class WorkspaceSourcesPanel(QWidget):
    inspect_requested = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.workspace: Workspace | None = None
        self._errors: dict[Path, str] = {}
        root = QVBoxLayout(self)
        header = QHBoxLayout()
        header.addWidget(QLabel("Generated sources"))
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        header.addWidget(refresh)
        header.addStretch(1)
        root.addLayout(header)
        self.sources = QListWidget()
        self.sources.itemDoubleClicked.connect(self._inspect_item)
        root.addWidget(self.sources, 1)
        inspect = QPushButton("Inspect Selected")
        inspect.clicked.connect(self.inspect_selected)
        root.addWidget(inspect)

    def set_workspace(self, workspace: Workspace | None) -> None:
        self.workspace = workspace
        self._errors.clear()
        self.refresh()

    def refresh(self) -> None:
        self.sources.clear()
        workspace = self.workspace
        if workspace is None:
            return
        candidates = discover_workspace_sources(workspace.outputs)
        paths = {candidate.path for candidate in candidates}
        self._errors = {path: value for path, value in self._errors.items() if path in paths}
        for candidate in candidates:
            error = self._errors.get(candidate.path)
            label = f"{candidate.path.name} — {candidate.kind_hint}"
            if error:
                label += f" — Uninspectable: {error}"
            item = QListWidgetItem(label)
            item.setData(SOURCE_PATH_ROLE, str(candidate.path))
            item.setToolTip(error or str(candidate.path))
            self.sources.addItem(item)

    def inspect_selected(self) -> None:
        self._inspect_item(self.sources.currentItem())

    def _inspect_item(self, item: QListWidgetItem | None) -> None:
        if item is not None:
            self.inspect_requested.emit(Path(str(item.data(SOURCE_PATH_ROLE))))

    def mark_uninspectable(self, path: Path, message: str) -> None:
        self._errors[path.resolve()] = message
        self.refresh()

    def mark_inspectable(self, path: Path) -> None:
        self._errors.pop(path.resolve(), None)
        self.refresh()


def discover_workspace_sources(output_root: Path) -> tuple[SourceCandidate, ...]:
    if not output_root.is_dir():
        return ()
    candidates: list[SourceCandidate] = []
    for path in output_root.iterdir():
        if path.is_symlink():
            continue
        if path.is_file() and path.suffix.lower() in {".csv", ".parquet"}:
            candidates.append(SourceCandidate(path.resolve(), path.suffix[1:].upper()))
            continue
        if not path.is_dir():
            continue
        if (path / "preparation.normalized.json").is_file():
            hint = "preparation bundle"
        elif (path / "sweep.normalized.json").is_file():
            hint = "model-sweep bundle"
        elif any(
            (path / name).is_file() for name in ("metadata.json", "dataset.csv", "dataset.parquet")
        ):
            hint = "dataset run"
        else:
            continue
        candidates.append(SourceCandidate(path.resolve(), hint))
    return tuple(sorted(candidates, key=lambda item: item.path.name))
