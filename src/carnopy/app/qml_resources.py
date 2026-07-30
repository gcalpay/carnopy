from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path, PurePosixPath
from typing import cast

PACKAGE_NAME = "carnopy.app"
MANIFEST_PATH = "resources/third-party-resources.json"
QML_MODULE = "Carnopy"
QML_TYPE = "Main"

MANDATORY_FONT_FILES = (
    "resources/fonts/IBMPlexSans-Regular.ttf",
    "resources/fonts/IBMPlexSans-Medium.ttf",
    "resources/fonts/IBMPlexSans-SemiBold.ttf",
    "resources/fonts/IBMPlexMono-Regular.ttf",
    "resources/fonts/IBMPlexMono-Medium.ttf",
)
MANDATORY_QML_FILES = (
    "qml/Carnopy/qmldir",
    "qml/Carnopy/Main.qml",
    "qml/Carnopy/Theme.qml",
    "qml/Carnopy/components/AppButton.qml",
    "qml/Carnopy/components/AppearanceSelector.qml",
    "qml/Carnopy/components/AppComboBox.qml",
    "qml/Carnopy/components/AppIcon.qml",
    "qml/Carnopy/components/BlockingBanner.qml",
    "qml/Carnopy/components/Card.qml",
    "qml/Carnopy/components/ChoiceList.qml",
    "qml/Carnopy/components/SearchableChoiceList.qml",
    "qml/Carnopy/components/CommandBar.qml",
    "qml/Carnopy/components/ContextInspector.qml",
    "qml/Carnopy/components/InspectionContextInspector.qml",
    "qml/Carnopy/components/ActivityContextInspector.qml",
    "qml/Carnopy/components/DecisionDialog.qml",
    "qml/Carnopy/components/LineNumberedTextArea.qml",
    "qml/Carnopy/components/MappingEditor.qml",
    "qml/Carnopy/components/NavRail.qml",
    "qml/Carnopy/components/OperationFeedback.qml",
    "qml/Carnopy/components/PlotEditor.qml",
    "qml/Carnopy/components/VerifiedPlotView.qml",
    "qml/Carnopy/components/ResponsiveCardGrid.qml",
    "qml/Carnopy/components/SamplerEditor.qml",
    "qml/Carnopy/components/StatusBadge.qml",
    "qml/Carnopy/components/ToastHost.qml",
    "qml/Carnopy/components/ValidationIssue.qml",
    "qml/Carnopy/components/WorkspaceOperationDialog.qml",
    "qml/Carnopy/pages/EmptyStatePage.qml",
    "qml/Carnopy/pages/DatasetPage.qml",
    "qml/Carnopy/pages/HelpPage.qml",
    "qml/Carnopy/pages/InspectPage.qml",
    "qml/Carnopy/pages/ActivityPage.qml",
    "qml/Carnopy/pages/SettingsPage.qml",
    "qml/Carnopy/pages/WorkspacePage.qml",
    "qml/Carnopy/pages/VisualizationPage.qml",
    "qml/Carnopy/pages/YamlPreviewPage.qml",
)
MANDATORY_ICON_FILES = (
    "resources/icons/activity.svg",
    "resources/icons/appearance-dark.svg",
    "resources/icons/appearance-light.svg",
    "resources/icons/appearance-warm.svg",
    "resources/icons/box.svg",
    "resources/icons/chart-spline.svg",
    "resources/icons/circle-question-mark.svg",
    "resources/icons/database.svg",
    "resources/icons/file-code.svg",
    "resources/icons/flask-conical.svg",
    "resources/icons/git-compare-arrows.svg",
    "resources/icons/layout-dashboard.svg",
    "resources/icons/monitor.svg",
    "resources/icons/moon.svg",
    "resources/icons/panel-left-close.svg",
    "resources/icons/panel-left-open.svg",
    "resources/icons/panel-right-close.svg",
    "resources/icons/panel-right-open.svg",
    "resources/icons/play.svg",
    "resources/icons/rotate-ccw.svg",
    "resources/icons/search.svg",
    "resources/icons/settings.svg",
    "resources/icons/sun.svg",
)
MANDATORY_RESOURCE_FILES = (
    *MANDATORY_QML_FILES,
    "resources/branding/carnopy-mark.png",
    *MANDATORY_ICON_FILES,
    *MANDATORY_FONT_FILES,
)

_SHA256 = re.compile(r"[0-9a-f]{64}")


class PackagedResourceError(RuntimeError):
    """Raised when an installed QML resource is missing or altered."""


@dataclass(frozen=True)
class ResourceRecord:
    packaged_path: str
    sha256: str
    owner: str


def package_root() -> Path:
    root = Path(str(files(PACKAGE_NAME)))
    if not root.is_dir():
        raise PackagedResourceError("the installed Carnopy application package is not a directory")
    return root


def packaged_path(relative_path: str, *, require_file: bool = True) -> Path:
    relative = PurePosixPath(relative_path)
    if relative.is_absolute() or not relative.parts or any(part == ".." for part in relative.parts):
        raise PackagedResourceError(f"invalid packaged resource path: {relative_path!r}")
    root = package_root().resolve()
    candidate = root.joinpath(*relative.parts).resolve()
    if not candidate.is_relative_to(root):
        raise PackagedResourceError(
            f"packaged resource escapes the application root: {relative_path}"
        )
    if require_file and not candidate.is_file():
        raise PackagedResourceError(f"missing packaged resource: {relative_path}")
    return candidate


def qml_import_path() -> Path:
    path = packaged_path("qml", require_file=False)
    if not path.is_dir():
        raise PackagedResourceError("missing packaged QML import directory")
    return path


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise PackagedResourceError(f"{label} must be an object")
    return cast(Mapping[str, object], value)


def _sequence(value: object, label: str) -> Sequence[object]:
    if not isinstance(value, list):
        raise PackagedResourceError(f"{label} must be an array")
    return cast(Sequence[object], value)


def _text(mapping: Mapping[str, object], key: str, label: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value:
        raise PackagedResourceError(f"{label}.{key} must be a non-empty string")
    return value


def load_resource_manifest() -> Mapping[str, object]:
    try:
        document = cast(
            object,
            json.loads(packaged_path(MANIFEST_PATH).read_text(encoding="utf-8")),
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise PackagedResourceError(
            f"could not read the packaged resource manifest: {exc}"
        ) from exc
    manifest = _mapping(document, "resource manifest")
    if manifest.get("schema_version") != 1:
        raise PackagedResourceError("unsupported packaged resource manifest schema")
    return manifest


def manifest_records() -> tuple[ResourceRecord, ...]:
    manifest = load_resource_manifest()
    records: list[ResourceRecord] = []
    branding = _mapping(manifest.get("branding"), "resource manifest branding")
    _text(branding, "name", "resource manifest branding")
    _text(branding, "source", "resource manifest branding")
    records.append(
        ResourceRecord(
            packaged_path=_text(branding, "packaged_path", "resource manifest branding"),
            sha256=_text(branding, "sha256", "resource manifest branding"),
            owner="Carnopy",
        )
    )
    for index, raw_resource in enumerate(
        _sequence(manifest.get("first_party_resources"), "resource manifest first_party_resources")
    ):
        resource_label = f"resource manifest first_party_resources[{index}]"
        resource = _mapping(raw_resource, resource_label)
        _text(resource, "name", resource_label)
        _text(resource, "source", resource_label)
        records.append(
            ResourceRecord(
                packaged_path=_text(resource, "packaged_path", resource_label),
                sha256=_text(resource, "sha256", resource_label),
                owner="Carnopy",
            )
        )
    for index, raw_project in enumerate(
        _sequence(manifest.get("third_party_projects"), "resource manifest third_party_projects")
    ):
        project_label = f"resource manifest third_party_projects[{index}]"
        project = _mapping(raw_project, project_label)
        name = _text(project, "name", project_label)
        _text(project, "revision", project_label)
        _text(project, "source_url", project_label)
        _text(project, "license_expression", project_label)
        license_path = _text(project, "license_path", project_label)
        project_paths: set[str] = set()
        for file_index, raw_file in enumerate(
            _sequence(project.get("files"), f"{project_label}.files")
        ):
            file_label = f"{project_label}.files[{file_index}]"
            file_entry = _mapping(raw_file, file_label)
            packaged = _text(file_entry, "packaged_path", file_label)
            _text(file_entry, "source_path", file_label)
            digest = _text(file_entry, "sha256", file_label)
            project_paths.add(packaged)
            records.append(ResourceRecord(packaged, digest, name))
        if license_path not in project_paths:
            raise PackagedResourceError(f"{project_label}.license_path is not listed as a file")
    return tuple(records)


def verify_packaged_resources() -> tuple[ResourceRecord, ...]:
    for relative_path in MANDATORY_RESOURCE_FILES:
        packaged_path(relative_path)
    records = manifest_records()
    seen: set[str] = set()
    for record in records:
        if record.packaged_path in seen:
            raise PackagedResourceError(
                f"duplicate packaged resource manifest path: {record.packaged_path}"
            )
        seen.add(record.packaged_path)
        if _SHA256.fullmatch(record.sha256) is None:
            raise PackagedResourceError(
                f"invalid SHA-256 for packaged resource: {record.packaged_path}"
            )
        actual = hashlib.sha256(
            packaged_path(f"resources/{record.packaged_path}").read_bytes()
        ).hexdigest()
        if actual != record.sha256:
            raise PackagedResourceError(f"packaged resource hash mismatch: {record.packaged_path}")
    return records
