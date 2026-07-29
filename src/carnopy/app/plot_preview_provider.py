from __future__ import annotations

import secrets
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from PySide6.QtCore import QObject, QSize, Qt
from PySide6.QtGui import QImage
from PySide6.QtQuick import QQuickImageProvider

from carnopy.app.plot_artifacts import PlotArtifactError, validated_plot_bytes

PLOT_PREVIEW_PROVIDER = "carnopy-plots"
_SVG_NAMESPACE = "http://www.w3.org/2000/svg"
_XLINK_NAMESPACE = "http://www.w3.org/1999/xlink"


@dataclass(frozen=True)
class _PreviewBinding:
    workspace_identity: str
    figures_root: Path
    image_path: Path
    image_sha256: str
    image_format: str
    verification_revision: str


class VerifiedPlotPreviewRegistry(QObject):
    """Issue opaque, revision-bound handles for verified local plot images."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._bindings: dict[str, _PreviewBinding] = {}

    def issue(
        self,
        *,
        workspace_identity: str,
        figures_root: Path,
        image_path: Path,
        image_sha256: str,
        image_format: str,
        verification_revision: str,
    ) -> str:
        normalized_format = image_format.casefold()
        if normalized_format not in {"png", "svg"}:
            raise PlotArtifactError("only PNG and SVG plots have in-app preview tokens")
        token = secrets.token_urlsafe(32)
        self._bindings[token] = _PreviewBinding(
            workspace_identity=workspace_identity,
            figures_root=figures_root,
            image_path=image_path,
            image_sha256=image_sha256,
            image_format=normalized_format,
            verification_revision=verification_revision,
        )
        return token

    def revoke(self, token: str) -> None:
        self._bindings.pop(token, None)

    def revoke_all(self) -> None:
        self._bindings.clear()

    def read(self, token: str) -> tuple[bytes, str]:
        binding = self._bindings.get(token)
        if binding is None:
            raise PlotArtifactError("plot preview token is unavailable")
        return (
            validated_plot_bytes(
                binding.figures_root,
                binding.image_path,
                binding.image_format,
                binding.image_sha256,
            ),
            binding.image_format,
        )

    @staticmethod
    def url(token: str) -> str:
        return f"image://{PLOT_PREVIEW_PROVIDER}/{token}"


class VerifiedPlotImageProvider(QQuickImageProvider):
    """Decode only images authorized by the verified-preview registry."""

    def __init__(self, registry: VerifiedPlotPreviewRegistry) -> None:
        super().__init__(QQuickImageProvider.ImageType.Image)
        self.registry = registry

    def requestImage(
        self,
        image_id: str,
        size: QSize,
        requested_size: QSize,
    ) -> QImage:
        try:
            data, image_format = self.registry.read(image_id)
            if image_format == "svg":
                data = _qt_compatible_svg_preview(data)
        except (ET.ParseError, PlotArtifactError):
            return QImage()
        image = QImage.fromData(data)
        if image.isNull():
            return image
        if requested_size.isValid() and not requested_size.isEmpty():
            image = image.scaled(
                requested_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        size.setWidth(image.width())
        size.setHeight(image.height())
        return image


def _qt_compatible_svg_preview(data: bytes) -> bytes:
    """Remove empty Matplotlib glyphs that QtSvg rejects from preview bytes only."""
    root = ET.fromstring(data)
    path_tag = f"{{{_SVG_NAMESPACE}}}path"
    use_tag = f"{{{_SVG_NAMESPACE}}}use"
    href_key = f"{{{_XLINK_NAMESPACE}}}href"
    empty_path_ids = {
        element.attrib["id"]
        for element in root.iter(path_tag)
        if element.attrib.get("id") and not element.attrib.get("d", "").strip()
    }
    if not empty_path_ids:
        return data
    for parent in root.iter():
        for child in tuple(parent):
            if child.tag == path_tag and child.attrib.get("id") in empty_path_ids:
                parent.remove(child)
                continue
            if child.tag != use_tag:
                continue
            href = child.attrib.get(href_key, child.attrib.get("href", ""))
            if href.removeprefix("#") in empty_path_ids:
                parent.remove(child)
    ET.register_namespace("", _SVG_NAMESPACE)
    ET.register_namespace("xlink", _XLINK_NAMESPACE)
    return cast(bytes, ET.tostring(root, encoding="utf-8", xml_declaration=True))
