from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication, QGraphicsView

from carnopy.app import plot_preview as preview_module
from carnopy.app.plot_preview import MAXIMUM_ZOOM, PlotPreview, PlotPreviewError


@pytest.fixture(scope="module")
def application() -> QApplication:
    existing = QApplication.instance()
    app = existing if isinstance(existing, QApplication) else QApplication([])
    yield app


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _png(path: Path) -> Path:
    image = QImage(80, 40, QImage.Format.Format_RGB32)
    image.fill(Qt.GlobalColor.cyan)
    assert image.save(str(path), "PNG")
    return path


def _svg(path: Path) -> Path:
    path.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="80" height="40">'
        '<rect width="80" height="40" fill="#00aacc"/></svg>',
        encoding="utf-8",
    )
    return path


def test_png_preview_loads_fits_and_preserves_manual_zoom_on_resize(
    tmp_path: Path,
    application: QApplication,
) -> None:
    figures = tmp_path / "figures"
    figures.joinpath("dataset").mkdir(parents=True)
    image = _png(figures / "dataset" / "plot.png")
    preview = PlotPreview()
    preview.resize(600, 400)
    preview.show()

    preview.load_export(figures, image, "png", _sha256(image))
    application.processEvents()

    assert preview.has_graphic
    assert preview.fit_button.isEnabled()
    assert preview.view.dragMode() == QGraphicsView.DragMode.ScrollHandDrag
    preview.actual_size()
    assert preview.view.transform().m11() == pytest.approx(1.0)
    preview.zoom_in()
    zoom = preview.view.transform().m11()
    assert zoom > 1.0
    preview.resize(800, 500)
    application.processEvents()
    assert preview.view.transform().m11() == pytest.approx(zoom)
    for _ in range(100):
        preview.zoom_in()
    assert preview.view.transform().m11() <= MAXIMUM_ZOOM
    preview.close()


def test_svg_preview_keeps_renderer_alive(
    tmp_path: Path,
    application: QApplication,
) -> None:
    figures = tmp_path / "figures"
    figures.joinpath("dataset").mkdir(parents=True)
    image = _svg(figures / "dataset" / "plot.svg")
    preview = PlotPreview()

    preview.load_export(figures, image, "svg", _sha256(image))
    application.processEvents()

    assert preview.has_graphic
    assert preview.svg_renderer is not None
    assert preview.svg_renderer.isValid()
    assert len(preview.scene.items()) == 1
    preview.clear()
    assert preview.svg_renderer is None


def test_pdf_opens_only_after_explicit_action_and_reports_launch_failure(
    tmp_path: Path,
    application: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del application
    figures = tmp_path / "figures"
    figures.joinpath("dataset").mkdir(parents=True)
    pdf = figures / "dataset" / "plot.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
    preview = PlotPreview()
    opened: list[Path] = []
    monkeypatch.setattr(
        preview_module,
        "_open_local_file",
        lambda path: opened.append(path) or False,
    )

    preview.load_export(figures, pdf, "pdf", _sha256(pdf))

    assert opened == []
    assert not preview.has_graphic
    assert preview.open_pdf_button.isEnabled()
    assert not preview.open_pdf()
    assert opened == [pdf]
    assert "could not be opened" in preview.status.text()

    monkeypatch.setattr(preview_module, "_open_local_file", lambda path: path == pdf)
    preview.load_export(figures, pdf, "pdf", _sha256(pdf))
    assert preview.open_pdf()

    pdf.write_bytes(b"changed")
    assert not preview.open_pdf()
    assert "validation failed" in preview.status.text()


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("suffix", "suffix"),
        ("hash", "SHA-256 does not match"),
        ("outside", "outside"),
        ("directory", "regular file"),
        ("symlink", "symbolic links"),
        ("format", "unsupported"),
    ],
)
def test_preview_rejects_unsafe_or_changed_paths(
    tmp_path: Path,
    application: QApplication,
    case: str,
    message: str,
) -> None:
    del application
    figures = tmp_path / "figures"
    figures.mkdir()
    dataset = figures / "dataset"
    dataset.mkdir()
    image = _png(dataset / "plot.png")
    image_format = "png"
    expected_hash = _sha256(image)

    if case == "suffix":
        image_format = "svg"
    elif case == "hash":
        expected_hash = "0" * 64
    elif case == "outside":
        image = _png(tmp_path / "outside.png")
        expected_hash = _sha256(image)
    elif case == "directory":
        image = dataset / "folder.png"
        image.mkdir()
        image_format = "png"
    elif case == "symlink":
        real = tmp_path / "real"
        real.mkdir()
        target = _png(real / "plot.png")
        linked = figures / "linked"
        linked.symlink_to(real, target_is_directory=True)
        image = linked / "plot.png"
        expected_hash = _sha256(target)
    elif case == "format":
        image_format = "bmp"

    with pytest.raises(PlotPreviewError, match=message):
        PlotPreview().load_export(figures, image, image_format, expected_hash)


def test_preview_rejects_symlinked_figures_root(
    tmp_path: Path,
    application: QApplication,
) -> None:
    del application
    real = tmp_path / "real-figures"
    real.joinpath("dataset").mkdir(parents=True)
    image = _png(real / "dataset" / "plot.png")
    linked = tmp_path / "figures"
    linked.symlink_to(real, target_is_directory=True)

    with pytest.raises(PlotPreviewError, match="regular directory"):
        PlotPreview().load_export(linked, linked / "dataset" / "plot.png", "png", _sha256(image))


def test_importing_plot_preview_does_not_load_scientific_or_rendering_modules() -> None:
    code = """
import sys
import carnopy.app.plot_preview
for name in (
    "CoolProp", "numpy", "pandas", "pyarrow", "matplotlib",
    "carnopy.visualization.plots", "carnopy.visualization.render",
    "carnopy.visualization.io", "carnopy.app.plot_rendering",
):
    if name in sys.modules:
        raise SystemExit(name)
"""
    completed = subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
