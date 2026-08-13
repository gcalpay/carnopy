from __future__ import annotations

import json
import tomllib
from pathlib import Path
from typing import Any

import yaml

from carnopy._version import __version__


def test_all_extra_contains_every_user_facing_optional_dependency() -> None:
    root = Path(__file__).resolve().parents[1]
    pyproject: dict[str, Any] = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    optional = pyproject["project"]["optional-dependencies"]
    assert "all" in optional

    feature_dependencies = {
        dependency
        for extra, dependencies in optional.items()
        if extra != "all"
        for dependency in dependencies
    }
    assert set(optional["all"]) == feature_dependencies


def test_coolprop_major_version_is_bounded() -> None:
    root = Path(__file__).resolve().parents[1]
    pyproject: dict[str, Any] = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))

    assert "CoolProp>=8,<9" in pyproject["project"]["dependencies"]


def test_desktop_extra_and_launcher_are_declared() -> None:
    root = Path(__file__).resolve().parents[1]
    pyproject: dict[str, Any] = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    readme = (root / "README.md").read_text(encoding="utf-8")

    assert pyproject["project"]["optional-dependencies"]["app"] == [
        "PySide6-Essentials>=6.11.1,<6.12",
        "matplotlib>=3.8",
        "Pillow>=12.3.0",
    ]
    assert (
        "PySide6-Essentials>=6.11.1,<6.12" in pyproject["project"]["optional-dependencies"]["all"]
    )
    assert pyproject["project"]["scripts"]["carnopy-app"] == "carnopy.app.qml_launcher:main_app"
    assert pyproject["project"]["scripts"]["carnopy-gui"] == "carnopy.app.qml_launcher:main_gui"
    assert "PySide6 Essentials 6.11.1 or later within the 6.11 release line" in readme
    assert "native bridge remains qualified against exactly Qt 6.11.1" in readme


def test_qml_runtime_is_public_and_resources_live_in_the_app_package() -> None:
    root = Path(__file__).resolve().parents[1]
    pyproject: dict[str, Any] = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    scripts = pyproject["project"]["scripts"]
    assert scripts == {
        "carnopy": "carnopy.__main__:main",
        "carnopy-app": "carnopy.app.qml_launcher:main_app",
        "carnopy-gui": "carnopy.app.qml_launcher:main_gui",
    }
    app_root = root / "src" / "carnopy" / "app"
    for relative_path in (
        "qml/Carnopy/Main.qml",
        "qml/Carnopy/pages/ActivityPage.qml",
        "qml/Carnopy/pages/DatasetPage.qml",
        "qml/Carnopy/pages/InspectPage.qml",
        "qml/Carnopy/pages/ModelSweepPage.qml",
        "qml/Carnopy/pages/RunPage.qml",
        "qml/Carnopy/pages/VisualizationPage.qml",
        "qml/Carnopy/pages/YamlPreviewPage.qml",
        "qml/Carnopy/components/BlockingBanner.qml",
        "qml/Carnopy/components/ComparisonPlotEditor.qml",
        "qml/Carnopy/components/PreparationScenarioEditor.qml",
        "qml/Carnopy/components/ActivityContextInspector.qml",
        "qml/Carnopy/components/InspectionContextInspector.qml",
        "qml/Carnopy/components/LineNumberedTextArea.qml",
        "qml/Carnopy/components/MappingEditor.qml",
        "qml/Carnopy/components/OperationFeedback.qml",
        "qml/Carnopy/components/PlotEditor.qml",
        "qml/Carnopy/components/VerifiedPlotView.qml",
        "qml/Carnopy/components/RunContextInspector.qml",
        "qml/Carnopy/components/WorkflowContextInspector.qml",
        "qml/Carnopy/components/WorkflowRunPanel.qml",
        "qml/Carnopy/qmldir",
        "resources/third-party-resources.json",
        "resources/branding/carnopy-mark.png",
        "resources/fonts/IBMPlexSans-Regular.ttf",
        "resources/fonts/IBMPlexMono-Regular.ttf",
        "resources/icons/appearance-dark.svg",
        "resources/icons/appearance-light.svg",
        "resources/icons/appearance-warm.svg",
        "resources/icons/flask-conical.svg",
        "resources/licenses/IBM-Plex-OFL-1.1.txt",
        "resources/licenses/Lucide-LICENSE.txt",
    ):
        assert (app_root / relative_path).is_file()


def test_widgets_presentation_modules_are_retired() -> None:
    app_root = Path(__file__).resolve().parents[1] / "src" / "carnopy" / "app"
    retired_modules = {
        "config_editor.py",
        "config_form.py",
        "config_widgets.py",
        "execution_page.py",
        "inspection_page.py",
        "jobs_page.py",
        "launcher.py",
        "plot_page.py",
        "plot_preview.py",
        "plot_request_dialog.py",
        "sources_page.py",
        "visualization_editor.py",
        "visualization_widgets.py",
        "window.py",
    }

    assert not {path.name for path in app_root.iterdir()} & retired_modules
    qtwidgets_importers = {
        path.name
        for path in app_root.glob("*.py")
        if "PySide6.QtWidgets" in path.read_text(encoding="utf-8")
    }
    assert qtwidgets_importers == {"qml_runtime.py"}


def test_manifest_hashed_resources_disable_checkout_byte_rewriting() -> None:
    root = Path(__file__).resolve().parents[1]
    attributes = (root / ".gitattributes").read_text(encoding="utf-8").splitlines()

    assert "src/carnopy/app/resources/** -text" in attributes


def test_analysis_extra_is_optional_and_scoped() -> None:
    root = Path(__file__).resolve().parents[1]
    pyproject: dict[str, Any] = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["optional-dependencies"]["analysis"] == ["scikit-learn>=1.9,<2"]
    assert "scikit-learn>=1.9,<2" in pyproject["project"]["optional-dependencies"]["all"]
    assert "scikit-learn" not in " ".join(pyproject["project"]["dependencies"]).casefold()


def test_visualization_extras_declare_the_pillow_security_floor() -> None:
    root = Path(__file__).resolve().parents[1]
    pyproject: dict[str, Any] = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    optional = pyproject["project"]["optional-dependencies"]

    assert "Pillow>=12.3.0" in optional["viz"]
    assert "Pillow>=12.3.0" in optional["app"]
    assert "Pillow>=12.3.0" in optional["all"]


def test_alpha_metadata_uses_modern_license_and_release_urls() -> None:
    root = Path(__file__).resolve().parents[1]
    pyproject: dict[str, Any] = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["build-system"] == {
        "requires": ["hatchling>=1.27.0"],
        "build-backend": "hatchling.build",
    }
    project = pyproject["project"]
    assert project["requires-python"] == ">=3.11"
    assert project["description"] == (
        "Reproducible thermophysical datasets from scientific backends with "
        "visualization, provenance, and leakage-aware preparation for physics-informed "
        "machine-learning and engineering workflows."
    )
    assert project["authors"] == [{"name": "gcalpay"}]
    assert project["license"] == "MIT"
    assert project["license-files"] == ["LICENSE"]
    assert project["urls"] == {
        "Repository": "https://github.com/gcalpay/carnopy",
        "Documentation": "https://github.com/gcalpay/carnopy#readme",
        "Issues": "https://github.com/gcalpay/carnopy/issues",
        "Releases": "https://github.com/gcalpay/carnopy/releases",
    }
    assert {
        "thermodynamics",
        "thermophysical",
        "fluid properties",
        "thermophysical properties",
        "dataset generation",
        "synthetic data",
        "data provenance",
        "data visualization",
        "data leakage prevention",
        "leakage-aware",
        "machine learning",
        "surrogate modeling",
        "CoolProp",
        "chemical-engineering",
    } == set(project["keywords"])
    for classifier in (
        "Environment :: Console",
        "Intended Audience :: Science/Research",
        "Operating System :: OS Independent",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "Topic :: Scientific/Engineering :: Chemistry",
        "Topic :: Scientific/Engineering :: Physics",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ):
        assert classifier in project["classifiers"]
    assert "Typing :: Typed" in project["classifiers"]
    for version in ("3.11", "3.12", "3.13", "3.14"):
        assert f"Programming Language :: Python :: {version}" in project["classifiers"]
    assert "Programming Language :: Python :: 3.10" not in project["classifiers"]
    assert not any(classifier.startswith("Private ::") for classifier in project["classifiers"])
    assert "License :: OSI Approved :: MIT License" not in project["classifiers"]


def test_citation_metadata_matches_the_package_and_published_release() -> None:
    root = Path(__file__).resolve().parents[1]
    citation = yaml.safe_load((root / "CITATION.cff").read_text(encoding="utf-8"))
    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))

    assert citation["title"] == "Carnopy"
    assert citation["version"] == __version__
    assert citation["license"] == "MIT"
    assert citation["repository-code"] == "https://github.com/gcalpay/carnopy"
    assert citation["abstract"] == pyproject["project"]["description"]
    assert citation["doi"] == "10.5281/zenodo.21709965"
    assert str(citation["date-released"]) == "2026-07-30"
    assert "10.xxxx" not in json.dumps(citation)


def test_public_and_community_markdown_have_intentional_distribution_boundaries() -> None:
    root = Path(__file__).resolve().parents[1]
    assert (root / "README.md").is_file()
    assert (root / "AGENTS.md").is_file()
    assert (root / "DESKTOP_ARCHITECTURE.md").is_file()
    assert (root / "ML_PREPARATION_ROADMAP.md").is_file()
    agent_guides = root / "docs" / "agent-guides"
    assert {path.name for path in agent_guides.glob("*.md")} == {
        "DELEGATION.md",
        "DEVELOPMENT.md",
        "RELEASE.md",
        "SCIENTIFIC_CONTRACTS.md",
    }
    community = root / ".github"
    for name in ("CONTRIBUTING.md", "CODE_OF_CONDUCT.md", "SECURITY.md"):
        assert (community / name).is_file()
    assert not list((root / "docs").glob("*.md"))

    pyproject: dict[str, Any] = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    sdist_includes = set(pyproject["tool"]["hatch"]["build"]["targets"]["sdist"]["include"])
    assert "/README.md" in sdist_includes
    assert "/AGENTS.md" in sdist_includes
    assert "/CITATION.cff" in sdist_includes
    assert "/DESKTOP_ARCHITECTURE.md" in sdist_includes
    assert "/ML_PREPARATION_ROADMAP.md" in sdist_includes
    assert "/PRODUCT_SCOPE.md" not in sdist_includes
    assert "/docs/agent-guides" in sdist_includes
    assert not any(path.startswith("/.github") for path in sdist_includes)
    assert "/docs" not in sdist_includes


def test_public_roadmap_separates_current_contracts_from_future_direction() -> None:
    root = Path(__file__).resolve().parents[1]
    readme = (root / "README.md").read_text(encoding="utf-8")
    normalized_readme = " ".join(readme.split())
    gui_plan = (root / "GUI2_PLAN.md").read_text(encoding="utf-8")
    desktop = (root / "DESKTOP_ARCHITECTURE.md").read_text(encoding="utf-8")

    assert "workflow depth now, source breadth next, and advanced model breadth later" in (
        normalized_readme
    )
    assert "Detailed source and model candidates are maintainer planning" in normalized_readme
    assert "it is neither implemented nor the current product priority" in normalized_readme
    assert "PRODUCT_SCOPE.md" not in readme
    assert "| 5 | Approved next |" in gui_plan
    assert "| 4 | Add controlled sweep and preparation worker operations | Complete" in desktop
    assert "| 5 | Add structured sweep and preparation QML workflows | Approved next" in desktop


def test_readme_documents_published_and_source_release_boundaries() -> None:
    root = Path(__file__).resolve().parents[1]
    text = (root / "README.md").read_text(encoding="utf-8")
    assert 'uv tool install "carnopy[app]==0.1.0a4"' in text
    assert 'python -m pip install "carnopy==0.1.0a4"' in text
    assert 'python -m pip install "carnopy[app]==0.1.0a4"' not in text
    for extra in ("app", "viz", "ml", "analysis", "all"):
        assert f"| `{extra}` |" in text
    assert "Exact union of all public extras" in text
    assert "The latest published alpha is `0.1.0a4`" in text
    assert "https://doi.org/10.5281/zenodo.21709965" in text
    assert "kind: property_heatmap" in text
    assert "`carnopy-gui` is the canonical" in text
    assert "`carnopy-app` launches the same\nQML application" in text
    assert "0.1.0a2" not in text
    assert "After `0.1.0a3` is published" not in text
    assert "not yet published" not in text
    assert "next-release" not in text
    assert "uv sync --locked --extra app --group dev" in text
    assert "uv run --locked carnopy-gui" in text
    assert "0.1.0a3.dev0" not in text
    assert "0.1.0a4.dev0" not in text
    assert "pending publisher" not in text.casefold()
    assert "Typing: typed" not in text
    assert (
        "Reproducible thermophysical datasets from scientific backends with\n"
        "visualization, provenance, and leakage-aware preparation for physics-informed\n"
        "machine-learning and engineering workflows."
    ) in text


def test_github_community_files_cover_public_reporting_paths() -> None:
    root = Path(__file__).resolve().parents[1]
    github = root / ".github"
    issue_templates = github / "ISSUE_TEMPLATE"
    assert {
        "bug-report.yml",
        "config.yml",
        "feature-request.yml",
        "scientific-discrepancy.yml",
    } == {path.name for path in issue_templates.iterdir() if path.is_file()}
    for path in issue_templates.glob("*.yml"):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert isinstance(document, dict)
        if path.name != "config.yml":
            assert {"name", "description", "body"} <= document.keys()

    security = (github / "SECURITY.md").read_text(encoding="utf-8")
    conduct = (github / "CODE_OF_CONDUCT.md").read_text(encoding="utf-8")
    scientific = (issue_templates / "scientific-discrepancy.yml").read_text(encoding="utf-8")
    bug_report = (issue_templates / "bug-report.yml").read_text(encoding="utf-8")
    assert "0.1.0a3.dev0" not in bug_report
    assert 'placeholder: "carnopy 0.1.0a3 or carnopy-app 0.1.0a3' in bug_report
    assert 'placeholder: "Carnopy 0.1.0a3; CoolProp 8.0.0"' in scientific
    assert "private vulnerability" in security.casefold()
    assert "gc@carnopy.org" in security
    assert "Contributor Covenant, version 2.1" in conduct
    for field in (
        "Carnopy and CoolProp versions",
        "Fluid and generation mode",
        "Normalized coordinates and units",
        "Reference-state policy",
        "Expected result and external source",
        "Metadata and report diagnostics",
    ):
        assert field in scientific


def test_repository_does_not_require_a_social_preview_asset() -> None:
    root = Path(__file__).resolve().parents[1]
    assert not (root / ".github" / "assets" / "social-preview.png").exists()


def test_public_agents_bootstraps_ignored_local_policy() -> None:
    root = Path(__file__).resolve().parents[1]
    agents = (root / "AGENTS.md").read_text(encoding="utf-8")
    gitignore = (root / ".gitignore").read_text(encoding="utf-8")
    assert "<repository-root>/.agents/local.md" in agents
    assert "<repository-root>/PRODUCT_SCOPE.md" in agents
    assert "<repository-root>/.agents/private/PRODUCT_STRATEGY.md" in agents
    assert "highest-priority repository instruction" in agents
    for guide in (
        "DELEGATION.md",
        "DEVELOPMENT.md",
        "RELEASE.md",
        "SCIENTIFIC_CONTRACTS.md",
    ):
        assert f"docs/agent-guides/{guide}" in agents
    assert ".agents/local.md" in gitignore
    assert "/PRODUCT_SCOPE.md" in gitignore
    assert ".agents/private/" in gitignore
