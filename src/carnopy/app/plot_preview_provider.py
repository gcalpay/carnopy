from __future__ import annotations

import secrets
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, QSize, Qt
from PySide6.QtGui import QImage
from PySide6.QtQuick import QQuickImageProvider

from carnopy.app.plot_artifacts import PlotArtifactError, validated_plot_bytes

PLOT_PREVIEW_PROVIDER = "carnopy-plots"


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
            data, _image_format = self.registry.read(image_id)
        except PlotArtifactError:
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
