from __future__ import annotations

import argparse
import hashlib
import json
import re
import tarfile
import zipfile
from email.message import Message
from email.parser import Parser
from pathlib import Path, PurePosixPath
from typing import Protocol

PROJECT_NAME = "carnopy"
PROJECT_SUMMARY = (
    "Reproducible thermophysical datasets from scientific backends with visualization, "
    "provenance, and leakage-aware preparation for physics-informed machine-learning "
    "and engineering workflows."
)
PROJECT_KEYWORDS = {
    "chemical-engineering",
    "coolprop",
    "data leakage prevention",
    "data provenance",
    "data visualization",
    "dataset generation",
    "fluid properties",
    "leakage-aware",
    "machine learning",
    "surrogate modeling",
    "synthetic data",
    "thermodynamics",
    "thermophysical",
    "thermophysical properties",
}
SOURCE_VERSION_PATTERN = re.compile(r'^__version__\s*=\s*"([^"]+)"\s*$')
QML_SHELL_APP_FILES = {
    "qml_settings.py",
    "qml/Carnopy/Main.qml",
    "qml/Carnopy/Theme.qml",
    "qml/Carnopy/qmldir",
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
    "qml/Carnopy/components/ActivityContextInspector.qml",
    "qml/Carnopy/components/InspectionContextInspector.qml",
    "qml/Carnopy/components/DecisionDialog.qml",
    "qml/Carnopy/components/LineNumberedTextArea.qml",
    "qml/Carnopy/components/MappingEditor.qml",
    "qml/Carnopy/components/NavRail.qml",
    "qml/Carnopy/components/OperationFeedback.qml",
    "qml/Carnopy/components/PlotEditor.qml",
    "qml/Carnopy/components/VerifiedPlotView.qml",
    "qml/Carnopy/components/PropertySymbol.qml",
    "qml/Carnopy/components/ResponsiveCardGrid.qml",
    "qml/Carnopy/components/RunContextInspector.qml",
    "qml/Carnopy/components/SamplerEditor.qml",
    "qml/Carnopy/components/StatusBadge.qml",
    "qml/Carnopy/components/ToastHost.qml",
    "qml/Carnopy/components/ValidationIssue.qml",
    "qml/Carnopy/components/WorkspaceOperationDialog.qml",
    "qml/Carnopy/pages/EmptyStatePage.qml",
    "qml/Carnopy/pages/ActivityPage.qml",
    "qml/Carnopy/pages/DatasetPage.qml",
    "qml/Carnopy/pages/HelpPage.qml",
    "qml/Carnopy/pages/InspectPage.qml",
    "qml/Carnopy/pages/RunPage.qml",
    "qml/Carnopy/pages/SettingsPage.qml",
    "qml/Carnopy/pages/WorkspacePage.qml",
    "qml/Carnopy/pages/VisualizationPage.qml",
    "qml/Carnopy/pages/YamlPreviewPage.qml",
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
}
WHEEL_REQUIRED = {
    "carnopy/__init__.py",
    "carnopy/__main__.py",
    "carnopy/_execution.py",
    "carnopy/app/__init__.py",
    "carnopy/app/activity_controller.py",
    "carnopy/app/application_identity.py",
    "carnopy/app/capabilities.py",
    "carnopy/app/client.py",
    "carnopy/app/config_controller.py",
    "carnopy/app/config_document.py",
    "carnopy/app/configured_plot_results_controller.py",
    "carnopy/app/dataset_draft.py",
    "carnopy/app/desktop_controller.py",
    "carnopy/app/draft_models.py",
    "carnopy/app/execution_controller.py",
    "carnopy/app/export_cleanup.py",
    "carnopy/app/field_ids.py",
    "carnopy/app/inspection_controller.py",
    "carnopy/app/inspection_models.py",
    "carnopy/app/jobs.py",
    "carnopy/app/mapping_draft.py",
    "carnopy/app/plot_context.py",
    "carnopy/app/plot_draft.py",
    "carnopy/app/plot_artifacts.py",
    "carnopy/app/plot_preview_provider.py",
    "carnopy/app/plot_rendering.py",
    "carnopy/app/plot_staging.py",
    "carnopy/app/property_presentation.py",
    "carnopy/app/qml/Carnopy/Main.qml",
    "carnopy/app/qml/Carnopy/qmldir",
    "carnopy/app/qml_launcher.py",
    "carnopy/app/qml_resources.py",
    "carnopy/app/qml_runtime.py",
    "carnopy/app/visualization_draft.py",
    "carnopy/app/protocol.py",
    "carnopy/app/recovery.py",
    "carnopy/app/request_coordinator.py",
    "carnopy/app/session_plot_controller.py",
    "carnopy/app/resources/branding/carnopy-mark.png",
    "carnopy/app/resources/fonts/IBMPlexMono-Medium.ttf",
    "carnopy/app/resources/fonts/IBMPlexMono-Regular.ttf",
    "carnopy/app/resources/fonts/IBMPlexSans-Medium.ttf",
    "carnopy/app/resources/fonts/IBMPlexSans-Regular.ttf",
    "carnopy/app/resources/fonts/IBMPlexSans-SemiBold.ttf",
    "carnopy/app/resources/icons/flask-conical.svg",
    "carnopy/app/resources/licenses/IBM-Plex-OFL-1.1.txt",
    "carnopy/app/resources/licenses/Lucide-LICENSE.txt",
    "carnopy/app/resources/third-party-resources.json",
    "carnopy/app/sampler_draft.py",
    "carnopy/sampling/projection.py",
    "carnopy/app/source_inspection.py",
    "carnopy/app/table_model.py",
    "carnopy/app/table_preview.py",
    "carnopy/app/worker.py",
    "carnopy/app/workspace.py",
    "carnopy/app/workspace_controller.py",
    "carnopy/cli.py",
    "carnopy/domain/numbers.py",
    "carnopy/inspection.py",
    "carnopy/config/sweep.py",
    "carnopy/py.typed",
    "carnopy/preparation/__init__.py",
    "carnopy/preparation/arrays.py",
    "carnopy/preparation/baselines.py",
    "carnopy/preparation/derived.py",
    "carnopy/preparation/grid_diagnostics.py",
    "carnopy/preparation/fields.py",
    "carnopy/preparation/layout.py",
    "carnopy/preparation/matrix_diagnostics.py",
    "carnopy/preparation/models.py",
    "carnopy/preparation/pipeline.py",
    "carnopy/preparation/quality.py",
    "carnopy/preparation/reference.py",
    "carnopy/preparation/reporting.py",
    "carnopy/preparation/rows.py",
    "carnopy/preparation/scenarios.py",
    "carnopy/preparation/stratification.py",
    "carnopy/preparation/source.py",
    "carnopy/sampling/canonical.py",
    "carnopy/sweeps/__init__.py",
    "carnopy/sweeps/comparison.py",
    "carnopy/sweeps/layout.py",
    "carnopy/sweeps/normalize.py",
    "carnopy/sweeps/pipeline.py",
    "carnopy/sweeps/plots.py",
    "carnopy/templates/__init__.py",
    "carnopy/templates/full_reference.yaml",
    "carnopy/templates/model_sweep.yaml",
    "carnopy/templates/preparation.yaml",
    "carnopy/templates/property_table.yaml",
    "carnopy/templates/saturation_table.yaml",
    "carnopy/templates/vapor_mass_fraction_table.yaml",
}
SDIST_REQUIRED = {
    "AGENTS.md",
    "CITATION.cff",
    "DESKTOP_ARCHITECTURE.md",
    "docs/agent-guides/DELEGATION.md",
    "docs/agent-guides/DEVELOPMENT.md",
    "docs/agent-guides/RELEASE.md",
    "docs/agent-guides/SCIENTIFIC_CONTRACTS.md",
    "LICENSE",
    "ML_PREPARATION_ROADMAP.md",
    "PRODUCT_SCOPE.md",
    "README.md",
    "configs/model_sweep_example.yaml",
    "configs/property_table_example.yaml",
    "configs/saturation_table_example.yaml",
    "configs/vapor_mass_fraction_table_example.yaml",
    "pyproject.toml",
    "scripts/check_distribution.py",
    "scripts/check_qml.py",
    "scripts/hash_distributions.py",
    "scripts/smoke_installed.py",
    "scripts/verify_index_release.py",
    "src/carnopy/__init__.py",
    "src/carnopy/_execution.py",
    "src/carnopy/app/__init__.py",
    "src/carnopy/app/activity_controller.py",
    "src/carnopy/app/application_identity.py",
    "src/carnopy/app/capabilities.py",
    "src/carnopy/app/client.py",
    "src/carnopy/app/config_controller.py",
    "src/carnopy/app/config_document.py",
    "src/carnopy/app/configured_plot_results_controller.py",
    "src/carnopy/app/dataset_draft.py",
    "src/carnopy/app/desktop_controller.py",
    "src/carnopy/app/draft_models.py",
    "src/carnopy/app/execution_controller.py",
    "src/carnopy/app/export_cleanup.py",
    "src/carnopy/app/field_ids.py",
    "src/carnopy/app/inspection_controller.py",
    "src/carnopy/app/inspection_models.py",
    "src/carnopy/app/jobs.py",
    "src/carnopy/app/mapping_draft.py",
    "src/carnopy/app/plot_context.py",
    "src/carnopy/app/plot_draft.py",
    "src/carnopy/app/plot_artifacts.py",
    "src/carnopy/app/plot_preview_provider.py",
    "src/carnopy/app/plot_rendering.py",
    "src/carnopy/app/plot_staging.py",
    "src/carnopy/app/property_presentation.py",
    "src/carnopy/app/qml/Carnopy/Main.qml",
    "src/carnopy/app/qml/Carnopy/qmldir",
    "src/carnopy/app/qml_launcher.py",
    "src/carnopy/app/qml_resources.py",
    "src/carnopy/app/qml_runtime.py",
    "src/carnopy/app/visualization_draft.py",
    "src/carnopy/app/protocol.py",
    "src/carnopy/app/recovery.py",
    "src/carnopy/app/request_coordinator.py",
    "src/carnopy/app/session_plot_controller.py",
    "src/carnopy/app/resources/branding/carnopy-mark.png",
    "src/carnopy/app/resources/fonts/IBMPlexMono-Medium.ttf",
    "src/carnopy/app/resources/fonts/IBMPlexMono-Regular.ttf",
    "src/carnopy/app/resources/fonts/IBMPlexSans-Medium.ttf",
    "src/carnopy/app/resources/fonts/IBMPlexSans-Regular.ttf",
    "src/carnopy/app/resources/fonts/IBMPlexSans-SemiBold.ttf",
    "src/carnopy/app/resources/icons/flask-conical.svg",
    "src/carnopy/app/resources/licenses/IBM-Plex-OFL-1.1.txt",
    "src/carnopy/app/resources/licenses/Lucide-LICENSE.txt",
    "src/carnopy/app/resources/third-party-resources.json",
    "src/carnopy/app/sampler_draft.py",
    "src/carnopy/sampling/projection.py",
    "src/carnopy/app/source_inspection.py",
    "src/carnopy/app/table_model.py",
    "src/carnopy/app/table_preview.py",
    "src/carnopy/app/worker.py",
    "src/carnopy/app/workspace.py",
    "src/carnopy/app/workspace_controller.py",
    "src/carnopy/config/sweep.py",
    "src/carnopy/domain/numbers.py",
    "src/carnopy/inspection.py",
    "src/carnopy/py.typed",
    "src/carnopy/preparation/__init__.py",
    "src/carnopy/preparation/arrays.py",
    "src/carnopy/preparation/baselines.py",
    "src/carnopy/preparation/derived.py",
    "src/carnopy/preparation/fields.py",
    "src/carnopy/preparation/grid_diagnostics.py",
    "src/carnopy/preparation/layout.py",
    "src/carnopy/preparation/matrix_diagnostics.py",
    "src/carnopy/preparation/models.py",
    "src/carnopy/preparation/pipeline.py",
    "src/carnopy/preparation/quality.py",
    "src/carnopy/preparation/reference.py",
    "src/carnopy/preparation/reporting.py",
    "src/carnopy/preparation/rows.py",
    "src/carnopy/preparation/scenarios.py",
    "src/carnopy/preparation/stratification.py",
    "src/carnopy/preparation/source.py",
    "src/carnopy/sampling/canonical.py",
    "src/carnopy/sweeps/__init__.py",
    "src/carnopy/sweeps/comparison.py",
    "src/carnopy/sweeps/layout.py",
    "src/carnopy/sweeps/normalize.py",
    "src/carnopy/sweeps/pipeline.py",
    "src/carnopy/sweeps/plots.py",
    "src/carnopy/templates/model_sweep.yaml",
    "src/carnopy/templates/preparation.yaml",
    "src/carnopy/templates/property_table.yaml",
    "src/carnopy/templates/full_reference.yaml",
    "tests/test_cli.py",
    "uv.lock",
}
WHEEL_REQUIRED.update(f"carnopy/app/{path}" for path in QML_SHELL_APP_FILES)
SDIST_REQUIRED.update(f"src/carnopy/app/{path}" for path in QML_SHELL_APP_FILES)
SDIST_MARKDOWN = {
    "AGENTS.md",
    "DESKTOP_ARCHITECTURE.md",
    "docs/agent-guides/DELEGATION.md",
    "docs/agent-guides/DEVELOPMENT.md",
    "docs/agent-guides/RELEASE.md",
    "docs/agent-guides/SCIENTIFIC_CONTRACTS.md",
    "ML_PREPARATION_ROADMAP.md",
    "PRODUCT_SCOPE.md",
    "README.md",
}
FORBIDDEN_ANYWHERE = {
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
}
FORBIDDEN_TOP_LEVEL = {
    ".venv",
    "build",
    "dist",
    "figures",
    "outputs",
}


class DistributionReader(Protocol):
    def names(self) -> set[str]: ...

    def read(self, name: str) -> bytes: ...


class WheelReader:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.archive = zipfile.ZipFile(path)

    def __enter__(self) -> WheelReader:
        return self

    def __exit__(self, *_args: object) -> None:
        self.archive.close()

    def names(self) -> set[str]:
        return set(self.archive.namelist())

    def read(self, name: str) -> bytes:
        return self.archive.read(name)


class SdistReader:
    def __init__(self, path: Path) -> None:
        self.path = path
        # The reader itself is a context manager and closes this archive in __exit__.
        self.archive = tarfile.open(path, mode="r:gz")  # noqa: SIM115

    def __enter__(self) -> SdistReader:
        return self

    def __exit__(self, *_args: object) -> None:
        self.archive.close()

    def names(self) -> set[str]:
        return {
            member.name.removeprefix("./")
            for member in self.archive.getmembers()
            if member.isfile()
        }

    def read(self, name: str) -> bytes:
        member = self.archive.getmember(name)
        stream = self.archive.extractfile(member)
        if stream is None:
            raise ValueError(f"could not read archive member {name}")
        with stream:
            return stream.read()


def resource_manifest_entries(content: bytes) -> dict[str, str]:
    try:
        manifest = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid packaged resource manifest: {exc}") from exc
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        raise ValueError("packaged resource manifest must use schema version 1")
    records: dict[str, str] = {}

    def add_record(entry: object, *, label: str) -> None:
        if not isinstance(entry, dict):
            raise ValueError(f"{label} must be an object")
        path = entry.get("packaged_path")
        digest = entry.get("sha256")
        if not isinstance(path, str) or not path or PurePosixPath(path).is_absolute():
            raise ValueError(f"{label} has an invalid packaged path")
        if ".." in PurePosixPath(path).parts:
            raise ValueError(f"{label} packaged path escapes the resource directory")
        if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise ValueError(f"{label} has an invalid SHA-256")
        if path in records:
            raise ValueError(f"duplicate packaged resource manifest path: {path}")
        records[path] = digest

    branding = manifest.get("branding")
    if not isinstance(branding, dict):
        raise ValueError("branding must be an object")
    for key in ("name", "source"):
        if not isinstance(branding.get(key), str) or not branding[key]:
            raise ValueError(f"branding.{key} must be a non-empty string")
    add_record(branding, label="branding")
    first_party = manifest.get("first_party_resources")
    if not isinstance(first_party, list) or not first_party:
        raise ValueError("packaged resource manifest must list first-party resources")
    for resource_index, resource in enumerate(first_party):
        label = f"first_party_resources[{resource_index}]"
        if not isinstance(resource, dict):
            raise ValueError(f"{label} must be an object")
        for key in ("name", "source"):
            if not isinstance(resource.get(key), str) or not resource[key]:
                raise ValueError(f"{label}.{key} must be a non-empty string")
        add_record(resource, label=label)
    projects = manifest.get("third_party_projects")
    if not isinstance(projects, list) or not projects:
        raise ValueError("packaged resource manifest must list third-party projects")
    for project_index, project in enumerate(projects):
        label = f"third_party_projects[{project_index}]"
        if not isinstance(project, dict):
            raise ValueError(f"{label} must be an object")
        for key in ("name", "revision", "source_url", "license_expression", "license_path"):
            if not isinstance(project.get(key), str) or not project[key]:
                raise ValueError(f"{label}.{key} must be a non-empty string")
        files = project.get("files")
        if not isinstance(files, list) or not files:
            raise ValueError(f"{label}.files must be a non-empty array")
        project_paths: set[str] = set()
        for file_index, entry in enumerate(files):
            file_label = f"{label}.files[{file_index}]"
            if not isinstance(entry, dict) or not isinstance(entry.get("source_path"), str):
                raise ValueError(f"{file_label}.source_path must be a string")
            add_record(entry, label=file_label)
            project_paths.add(str(entry["packaged_path"]))
        if project["license_path"] not in project_paths:
            raise ValueError(f"{label}.license_path is not listed as a file")
    return records


def validate_packaged_resource_bytes(
    reader: DistributionReader,
    *,
    manifest_name: str,
    resource_prefix: str,
) -> None:
    records = resource_manifest_entries(reader.read(manifest_name))
    names = reader.names()
    for relative_path, expected in records.items():
        archive_name = f"{resource_prefix}{relative_path}"
        if archive_name not in names:
            raise ValueError(f"distribution is missing manifested resource: {archive_name}")
        actual = hashlib.sha256(reader.read(archive_name)).hexdigest()
        if actual != expected:
            raise ValueError(f"distribution resource hash mismatch: {archive_name}")


def source_version(path: Path) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        match = SOURCE_VERSION_PATTERN.fullmatch(line.strip())
        if match is not None:
            return match.group(1)
    raise ValueError(f"could not find __version__ in {path}")


def parse_metadata(content: bytes) -> Message:
    return Parser().parsestr(content.decode("utf-8"))


def validate_metadata(metadata: Message, expected_version: str, *, artifact: str) -> None:
    if metadata.get("Name", "").casefold() != PROJECT_NAME:
        raise ValueError(f"{artifact} metadata Name is not {PROJECT_NAME!r}")
    if metadata.get("Version") != expected_version:
        raise ValueError(
            f"{artifact} metadata version {metadata.get('Version')!r} "
            f"does not match {expected_version!r}"
        )
    if metadata.get("Summary") != PROJECT_SUMMARY:
        raise ValueError(f"{artifact} metadata summary is not the approved project description")
    if metadata.get("License-Expression") != "MIT":
        raise ValueError(f"{artifact} does not declare License-Expression: MIT")
    if "LICENSE" not in metadata.get_all("License-File", []):
        raise ValueError(f"{artifact} metadata does not record LICENSE")
    if metadata.get("Requires-Python") != ">=3.11":
        raise ValueError(f"{artifact} metadata does not declare Requires-Python: >=3.11")
    classifiers = metadata.get_all("Classifier", [])
    if "Typing :: Typed" not in classifiers:
        raise ValueError(f"{artifact} metadata does not declare Typing :: Typed")
    for version in ("3.11", "3.12", "3.13", "3.14"):
        classifier = f"Programming Language :: Python :: {version}"
        if classifier not in classifiers:
            raise ValueError(f"{artifact} metadata does not declare Python {version} support")
    if "Programming Language :: Python :: 3.10" in classifiers:
        raise ValueError(f"{artifact} metadata still declares Python 3.10 support")
    for classifier in (
        "Environment :: Console",
        "Intended Audience :: Science/Research",
        "Operating System :: OS Independent",
    ):
        if classifier not in classifiers:
            raise ValueError(f"{artifact} metadata does not declare {classifier!r}")
    private = [classifier for classifier in classifiers if classifier.startswith("Private ::")]
    if private:
        raise ValueError(f"{artifact} contains forbidden private classifiers: {private}")
    urls = metadata.get_all("Project-URL", [])
    if not any(value.startswith("Repository, ") for value in urls):
        raise ValueError(f"{artifact} metadata does not contain the Repository project URL")
    if not any(value.startswith("Documentation, ") for value in urls):
        raise ValueError(f"{artifact} metadata does not contain the Documentation project URL")
    if not any(value.startswith("Issues, ") for value in urls):
        raise ValueError(f"{artifact} metadata does not contain the Issues project URL")
    if not any(value.startswith("Releases, ") for value in urls):
        raise ValueError(f"{artifact} metadata does not contain the Releases project URL")
    keywords = {
        keyword.strip().casefold()
        for keyword in metadata.get("Keywords", "").split(",")
        if keyword.strip()
    }
    if keywords != PROJECT_KEYWORDS:
        raise ValueError(f"{artifact} metadata declares unexpected keywords: {sorted(keywords)}")
    extras = set(metadata.get_all("Provides-Extra", []))
    if extras != {"all", "analysis", "app", "ml", "viz"}:
        raise ValueError(f"{artifact} metadata declares unexpected optional extras: {extras}")
    coolprop_requirements = [
        requirement
        for requirement in metadata.get_all("Requires-Dist", [])
        if requirement.casefold().startswith("coolprop")
    ]
    if len(coolprop_requirements) != 1 or not all(
        bound in coolprop_requirements[0] for bound in (">=8", "<9")
    ):
        raise ValueError(f"{artifact} must require CoolProp >=8,<9")
    matplotlib_requirements = [
        requirement
        for requirement in metadata.get_all("Requires-Dist", [])
        if requirement.casefold().startswith("matplotlib")
    ]
    if len(matplotlib_requirements) != 3 or any(
        "extra ==" not in requirement for requirement in matplotlib_requirements
    ):
        raise ValueError(
            f"{artifact} must declare Matplotlib only through all, app, and viz extras"
        )
    pillow_requirements = [
        requirement
        for requirement in metadata.get_all("Requires-Dist", [])
        if requirement.casefold().startswith("pillow")
    ]
    if len(pillow_requirements) != 3 or any(
        ">=12.3.0" not in requirement or "extra ==" not in requirement
        for requirement in pillow_requirements
    ):
        raise ValueError(
            f"{artifact} must declare Pillow >=12.3.0 only through all, app, and viz extras"
        )
    safetensors_requirements = [
        requirement
        for requirement in metadata.get_all("Requires-Dist", [])
        if requirement.casefold().startswith("safetensors")
    ]
    if len(safetensors_requirements) != 2 or any(
        "extra ==" not in requirement for requirement in safetensors_requirements
    ):
        raise ValueError(f"{artifact} must declare SafeTensors only through all and ml extras")
    pyside_requirements = [
        requirement
        for requirement in metadata.get_all("Requires-Dist", [])
        if requirement.casefold().startswith("pyside6-essentials")
    ]
    if len(pyside_requirements) != 2 or any(
        ">=6.11.1" not in requirement or "<6.12" not in requirement or "extra ==" not in requirement
        for requirement in pyside_requirements
    ):
        raise ValueError(
            f"{artifact} must declare PySide6 >=6.11.1,<6.12 only through all and app extras"
        )
    sklearn_requirements = [
        requirement
        for requirement in metadata.get_all("Requires-Dist", [])
        if requirement.casefold().startswith("scikit-learn")
    ]
    if len(sklearn_requirements) != 2 or any(
        "extra ==" not in requirement for requirement in sklearn_requirements
    ):
        raise ValueError(
            f"{artifact} must declare scikit-learn only through all and analysis extras"
        )


def forbidden_paths(names: set[str], *, strip_root: bool) -> list[str]:
    invalid: list[str] = []
    for name in names:
        path = PurePosixPath(name)
        parts = path.parts[1:] if strip_root and path.parts else path.parts
        if (
            any(part.endswith(".ipynb") for part in parts)
            or (parts and parts[0] in FORBIDDEN_TOP_LEVEL)
            or any(part in FORBIDDEN_ANYWHERE for part in parts)
        ):
            invalid.append(name)
        if any(part.endswith((".pyc", ".pyo")) for part in parts):
            invalid.append(name)
    return sorted(set(invalid))


def inspect_wheel(path: Path, expected_version: str) -> None:
    with WheelReader(path) as reader:
        names = reader.names()
        missing = sorted(WHEEL_REQUIRED - names)
        if missing:
            raise ValueError(f"wheel is missing required files: {', '.join(missing)}")
        invalid = forbidden_paths(names, strip_root=False)
        if invalid:
            raise ValueError(f"wheel contains forbidden files: {', '.join(invalid)}")
        if any(name.startswith("tests/") for name in names):
            raise ValueError("wheel must not contain tests")
        validate_packaged_resource_bytes(
            reader,
            manifest_name="carnopy/app/resources/third-party-resources.json",
            resource_prefix="carnopy/app/resources/",
        )

        metadata_names = [name for name in names if name.endswith(".dist-info/METADATA")]
        entry_point_names = [name for name in names if name.endswith(".dist-info/entry_points.txt")]
        license_names = [name for name in names if name.endswith(".dist-info/licenses/LICENSE")]
        if len(metadata_names) != 1 or len(entry_point_names) != 1 or len(license_names) != 1:
            raise ValueError("wheel dist-info metadata, entry point, or license layout is invalid")
        validate_metadata(
            parse_metadata(reader.read(metadata_names[0])),
            expected_version,
            artifact="wheel",
        )
        entry_points = reader.read(entry_point_names[0]).decode("utf-8")
        if "carnopy = carnopy.__main__:main" not in entry_points:
            raise ValueError("wheel does not contain the carnopy console entry point")
        if "carnopy-app = carnopy.app.qml_launcher:main_app" not in entry_points:
            raise ValueError("wheel does not contain the carnopy-app console entry point")
        if "carnopy-gui = carnopy.app.qml_launcher:main_gui" not in entry_points:
            raise ValueError("wheel does not contain the carnopy-gui console entry point")


def inspect_sdist(path: Path, expected_version: str) -> None:
    with SdistReader(path) as reader:
        names = reader.names()
        roots = {PurePosixPath(name).parts[0] for name in names if PurePosixPath(name).parts}
        if len(roots) != 1:
            raise ValueError(
                f"sdist must contain exactly one root directory, found {sorted(roots)}"
            )
        root = next(iter(roots))
        relative = {
            PurePosixPath(name).relative_to(root).as_posix() for name in names if name != root
        }
        missing = sorted(SDIST_REQUIRED - relative)
        if missing:
            raise ValueError(f"sdist is missing required files: {', '.join(missing)}")
        markdown = {name for name in relative if name.endswith(".md")}
        if markdown != SDIST_MARKDOWN:
            raise ValueError(
                "sdist Markdown inventory does not match the approved public documents; "
                f"found {sorted(markdown)}"
            )
        invalid = forbidden_paths(names, strip_root=True)
        if invalid:
            raise ValueError(f"sdist contains forbidden files: {', '.join(invalid)}")
        validate_packaged_resource_bytes(
            reader,
            manifest_name=f"{root}/src/carnopy/app/resources/third-party-resources.json",
            resource_prefix=f"{root}/src/carnopy/app/resources/",
        )

        metadata_name = f"{root}/PKG-INFO"
        if metadata_name not in names:
            raise ValueError("sdist does not contain PKG-INFO")
        validate_metadata(
            parse_metadata(reader.read(metadata_name)),
            expected_version,
            artifact="sdist",
        )
        template_pairs = {
            "property_table": "property_table_example",
            "saturation_table": "saturation_table_example",
            "vapor_mass_fraction_table": "vapor_mass_fraction_table_example",
        }
        for template, example in template_pairs.items():
            packaged = reader.read(f"{root}/src/carnopy/templates/{template}.yaml")
            repository = reader.read(f"{root}/configs/{example}.yaml")
            if packaged != repository:
                raise ValueError(f"sdist template {template!r} differs from its repository example")


def distribution_paths(paths: list[Path]) -> tuple[Path, Path]:
    wheels = [path for path in paths if path.suffix == ".whl"]
    sdists = [path for path in paths if path.name.endswith(".tar.gz")]
    if len(wheels) != 1 or len(sdists) != 1 or len(paths) != 2:
        raise ValueError("expected exactly one wheel and one .tar.gz source distribution")
    return wheels[0], sdists[0]


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect Carnopy wheel and sdist contents.")
    parser.add_argument("artifacts", nargs="+", type=Path)
    parser.add_argument("--expected-version")
    parser.add_argument(
        "--source-version-file",
        type=Path,
        default=Path("src/carnopy/_version.py"),
    )
    arguments = parser.parse_args()

    expected_version = arguments.expected_version or source_version(arguments.source_version_file)
    actual_source_version = source_version(arguments.source_version_file)
    if expected_version != actual_source_version:
        raise ValueError(
            f"expected version {expected_version!r} does not match source "
            f"version {actual_source_version!r}"
        )
    wheel, sdist = distribution_paths(arguments.artifacts)
    inspect_wheel(wheel, expected_version)
    inspect_sdist(sdist, expected_version)
    print(f"Verified wheel: {wheel}")
    print(f"Verified sdist: {sdist}")
    print(f"Version: {expected_version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
