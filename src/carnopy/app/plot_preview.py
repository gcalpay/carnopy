from __future__ import annotations

import hashlib
import stat
from pathlib import Path

from PySide6.QtCore import QByteArray, Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtSvgWidgets import QGraphicsSvgItem
from PySide6.QtWidgets import (
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

SUPPORTED_PREVIEW_FORMATS = frozenset({"png", "svg", "pdf"})
ZOOM_FACTOR = 1.25
MINIMUM_ZOOM = 0.05
MAXIMUM_ZOOM = 32.0


class PlotPreviewError(ValueError):
    """A rendered plot cannot be validated or displayed safely."""


class PlotPreview(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._figures_root: Path | None = None
        self._image_path: Path | None = None
        self._image_format: str | None = None
        self._image_sha256: str | None = None
        self._svg_renderer: QSvgRenderer | None = None

        layout = QVBoxLayout(self)
        actions = QHBoxLayout()
        self.fit_button = QPushButton("Fit")
        self.zoom_in_button = QPushButton("Zoom In")
        self.zoom_out_button = QPushButton("Zoom Out")
        self.actual_size_button = QPushButton("100%")
        self.open_pdf_button = QPushButton("Open PDF")
        self.fit_button.clicked.connect(self.fit_preview)
        self.zoom_in_button.clicked.connect(self.zoom_in)
        self.zoom_out_button.clicked.connect(self.zoom_out)
        self.actual_size_button.clicked.connect(self.actual_size)
        self.open_pdf_button.clicked.connect(self.open_pdf)
        for button in (
            self.fit_button,
            self.zoom_in_button,
            self.zoom_out_button,
            self.actual_size_button,
            self.open_pdf_button,
        ):
            actions.addWidget(button)
        actions.addStretch(1)
        layout.addLayout(actions)

        self.status = QLabel("No rendered plot to preview.")
        self.status.setWordWrap(True)
        self.status.setAccessibleName("Plot preview status")
        layout.addWidget(self.status)
        self.scene = QGraphicsScene(self)
        self.view = QGraphicsView(self.scene)
        self.view.setAccessibleName("Rendered plot preview")
        self.view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.view.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.view.setResizeAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self.view.setMinimumHeight(260)
        layout.addWidget(self.view, 1)
        self._update_actions(has_graphic=False, is_pdf=False)

    @property
    def has_graphic(self) -> bool:
        return bool(self.scene.items())

    @property
    def image_path(self) -> Path | None:
        return self._image_path

    @property
    def svg_renderer(self) -> QSvgRenderer | None:
        return self._svg_renderer

    def clear(self) -> None:
        self.scene.clear()
        if self._svg_renderer is not None:
            self._svg_renderer.deleteLater()
        self._svg_renderer = None
        self._figures_root = None
        self._image_path = None
        self._image_format = None
        self._image_sha256 = None
        self.view.resetTransform()
        self.status.setText("No rendered plot to preview.")
        self._update_actions(has_graphic=False, is_pdf=False)

    def load_export(
        self,
        figures_root: Path,
        image_path: Path,
        image_format: str,
        expected_sha256: str,
    ) -> None:
        self.clear()
        normalized_format = image_format.casefold()
        data = _validated_bytes(
            figures_root,
            image_path,
            normalized_format,
            expected_sha256,
        )
        self._figures_root = figures_root
        self._image_path = image_path
        self._image_format = normalized_format
        self._image_sha256 = expected_sha256

        if normalized_format == "png":
            pixmap = QPixmap()
            if not pixmap.loadFromData(data):
                self.clear()
                raise PlotPreviewError("rendered PNG data could not be decoded by Qt")
            self.scene.addItem(QGraphicsPixmapItem(pixmap))
            self.status.setText(f"PNG preview: {image_path}")
            self._update_actions(has_graphic=True, is_pdf=False)
            QTimer.singleShot(0, self.fit_preview)
            return

        if normalized_format == "svg":
            renderer = QSvgRenderer(QByteArray(data), self)
            if not renderer.isValid():
                renderer.deleteLater()
                self.clear()
                raise PlotPreviewError("rendered SVG data could not be decoded by Qt")
            item = QGraphicsSvgItem()
            item.setSharedRenderer(renderer)
            self._svg_renderer = renderer
            self.scene.addItem(item)
            self.status.setText(f"SVG preview: {image_path}")
            self._update_actions(has_graphic=True, is_pdf=False)
            QTimer.singleShot(0, self.fit_preview)
            return

        self.status.setText(f"PDF export ready. Use Open PDF to view it: {image_path}")
        self._update_actions(has_graphic=False, is_pdf=True)

    def fit_preview(self) -> None:
        if not self.has_graphic:
            return
        bounds = self.scene.itemsBoundingRect()
        if bounds.isEmpty():
            return
        self.view.resetTransform()
        self.view.fitInView(bounds, Qt.AspectRatioMode.KeepAspectRatio)

    def actual_size(self) -> None:
        if self.has_graphic:
            self.view.resetTransform()

    def zoom_in(self) -> None:
        self._zoom(ZOOM_FACTOR)

    def zoom_out(self) -> None:
        self._zoom(1.0 / ZOOM_FACTOR)

    def open_pdf(self) -> bool:
        figures_root = self._figures_root
        image_path = self._image_path
        image_sha256 = self._image_sha256
        if (
            figures_root is None
            or image_path is None
            or image_sha256 is None
            or self._image_format != "pdf"
        ):
            return False
        try:
            _validated_bytes(figures_root, image_path, "pdf", image_sha256)
        except PlotPreviewError as exc:
            self.status.setText(f"PDF validation failed: {exc}")
            return False
        opened = _open_local_file(image_path)
        if not opened:
            self.status.setText(
                "The system PDF viewer could not be opened. The exported file was preserved at "
                f"{image_path}."
            )
        return opened

    def _zoom(self, factor: float) -> None:
        if not self.has_graphic:
            return
        current = abs(self.view.transform().m11())
        if current == 0:
            self.view.resetTransform()
            current = 1.0
        target = min(MAXIMUM_ZOOM, max(MINIMUM_ZOOM, current * factor))
        if target != current:
            self.view.scale(target / current, target / current)

    def _update_actions(self, *, has_graphic: bool, is_pdf: bool) -> None:
        for button in (
            self.fit_button,
            self.zoom_in_button,
            self.zoom_out_button,
            self.actual_size_button,
        ):
            button.setEnabled(has_graphic)
        self.open_pdf_button.setEnabled(is_pdf)


def _validated_bytes(
    figures_root: Path,
    image_path: Path,
    image_format: str,
    expected_sha256: str,
) -> bytes:
    if image_format not in SUPPORTED_PREVIEW_FORMATS:
        raise PlotPreviewError(f"unsupported plot preview format: {image_format}")
    if image_path.suffix.casefold() != f".{image_format}":
        raise PlotPreviewError("rendered plot suffix does not match its reported format")
    if len(expected_sha256) != 64 or any(
        character not in "0123456789abcdef" for character in expected_sha256.casefold()
    ):
        raise PlotPreviewError("rendered plot SHA-256 is invalid")

    root = figures_root.absolute()
    path = image_path.absolute()
    try:
        root_info = root.lstat()
    except OSError as exc:
        raise PlotPreviewError(f"workspace figures directory is unavailable: {root}") from exc
    if stat.S_ISLNK(root_info.st_mode) or not stat.S_ISDIR(root_info.st_mode):
        raise PlotPreviewError("workspace figures path must be a regular directory")
    try:
        relative = path.relative_to(root)
    except ValueError as exc:
        raise PlotPreviewError("rendered plot is outside the workspace figures directory") from exc
    if not relative.parts:
        raise PlotPreviewError("rendered plot path does not identify a file")

    current = root
    before = None
    for index, part in enumerate(relative.parts):
        current /= part
        try:
            info = current.lstat()
        except OSError as exc:
            raise PlotPreviewError(f"rendered plot path is unavailable: {current}") from exc
        if stat.S_ISLNK(info.st_mode):
            raise PlotPreviewError("rendered plot path must not contain symbolic links")
        if index < len(relative.parts) - 1 and not stat.S_ISDIR(info.st_mode):
            raise PlotPreviewError("rendered plot parent path is not a directory")
        before = info
    assert before is not None
    if not stat.S_ISREG(before.st_mode):
        raise PlotPreviewError("rendered plot is not a regular file")
    try:
        if not path.resolve(strict=True).is_relative_to(root.resolve(strict=True)):
            raise PlotPreviewError("rendered plot escapes the workspace figures directory")
        data = path.read_bytes()
        after = path.lstat()
    except OSError as exc:
        raise PlotPreviewError(f"rendered plot could not be read: {path}") from exc
    if stat.S_ISLNK(after.st_mode) or (before.st_dev, before.st_ino) != (
        after.st_dev,
        after.st_ino,
    ):
        raise PlotPreviewError("rendered plot changed while it was being validated")
    if hashlib.sha256(data).hexdigest() != expected_sha256.casefold():
        raise PlotPreviewError("rendered plot SHA-256 does not match the worker result")
    return data


def _open_local_file(path: Path) -> bool:
    return QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
