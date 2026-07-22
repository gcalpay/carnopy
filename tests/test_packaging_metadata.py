from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

import yaml


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
    assert pyproject["project"]["scripts"]["carnopy-app"] == "carnopy.app.launcher:main"
    assert pyproject["project"]["scripts"]["carnopy-gui"] == "carnopy.app.launcher:main_gui"
    assert "PySide6 Essentials 6.11.1 or later within the 6.11 release line" in readme
    assert "native bridge remains qualified against exactly Qt 6.11.1" in readme


def test_qml_runtime_is_private_and_resources_live_in_the_app_package() -> None:
    root = Path(__file__).resolve().parents[1]
    pyproject: dict[str, Any] = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    scripts = pyproject["project"]["scripts"]
    assert scripts == {
        "carnopy": "carnopy.__main__:main",
        "carnopy-app": "carnopy.app.launcher:main",
        "carnopy-gui": "carnopy.app.launcher:main_gui",
    }
    app_root = root / "src" / "carnopy" / "app"
    for relative_path in (
        "qml/Carnopy/Main.qml",
        "qml/Carnopy/pages/DatasetPage.qml",
        "qml/Carnopy/pages/VisualizationPage.qml",
        "qml/Carnopy/pages/YamlPreviewPage.qml",
        "qml/Carnopy/components/BlockingBanner.qml",
        "qml/Carnopy/components/LineNumberedTextArea.qml",
        "qml/Carnopy/components/MappingEditor.qml",
        "qml/Carnopy/components/OperationFeedback.qml",
        "qml/Carnopy/components/PlotEditor.qml",
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
        "CLI-first thermophysical dataset generation and leakage-aware ML preparation "
        "from thermodynamic backends, with an optional Linux-first desktop GUI."
    )
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
        "fluid properties",
        "thermophysical properties",
        "dataset generation",
        "scientific computing",
        "machine learning",
        "surrogate modeling",
        "CoolProp",
    } == set(project["keywords"])
    for classifier in (
        "Environment :: Console",
        "Intended Audience :: Science/Research",
        "Operating System :: OS Independent",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
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


def test_manual_plot_workflow_uses_the_printed_run_directory_directly() -> None:
    root = Path(__file__).resolve().parents[1]
    expected_run = 'RUN_DIR="outputs/manual-test/20260621T172006Z_vapor_fraction_c8e28e9f"'
    text = (root / "README.md").read_text(encoding="utf-8")
    assert "--out outputs/manual-test" in text
    assert "Example only; replace this with the exact path printed by your run." in text
    assert expected_run in text
    assert "outputs/manual-test/outputs/manual-test" not in text


def test_readme_uses_github_supported_math_delimiters() -> None:
    root = Path(__file__).resolve().parents[1]
    text = (root / "README.md").read_text(encoding="utf-8")
    assert r"\(" not in text
    assert r"\[" not in text
    assert "$x_{\\mathrm{vap}}$" in text
    assert "```math" in text


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
    assert "/DESKTOP_ARCHITECTURE.md" in sdist_includes
    assert "/ML_PREPARATION_ROADMAP.md" in sdist_includes
    assert "/docs/agent-guides" in sdist_includes
    assert not any(path.startswith("/.github") for path in sdist_includes)
    assert "/docs" not in sdist_includes


def test_readme_documents_the_0_1_0a3_release_boundary() -> None:
    root = Path(__file__).resolve().parents[1]
    text = (root / "README.md").read_text(encoding="utf-8")
    for package in (
        "carnopy",
        "carnopy[viz]",
        "carnopy[ml]",
        "carnopy[analysis]",
        "carnopy[app]",
        "carnopy[all]",
    ):
        assert f'python -m pip install "{package}==0.1.0a3"' in text
    assert 'uv tool install "carnopy==0.1.0a3"' in text
    assert 'uv tool install "carnopy[all]==0.1.0a3"' in text
    assert "The `all` extra is the dependency union of `viz`,\n" in text
    assert "`ml`, `analysis`, and `app`" in text
    assert "Version `0.1.0a3` includes GUI-1" in text
    assert "active GUI-2 source line reports `0.1.0a4.dev0`" in text
    assert "active `0.1.0a4.dev0` application development line" in text
    assert "0.1.0a2" not in text
    assert "After `0.1.0a3` is published" not in text
    assert "not yet published" not in text
    assert "next-release" not in text
    assert "uv sync --locked --extra app --group dev" in text
    assert "uv run --locked carnopy-gui" in text
    assert "0.1.0a3.dev0" not in text
    assert "pending publisher" not in text.casefold()
    assert "Typing: typed" not in text
    assert (
        "CLI-first thermophysical dataset generation and leakage-aware ML preparation\n"
        "from thermodynamic backends, with an optional Linux-first desktop GUI."
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
    assert "highest-priority repository instruction" in agents
    for guide in (
        "DELEGATION.md",
        "DEVELOPMENT.md",
        "RELEASE.md",
        "SCIENTIFIC_CONTRACTS.md",
    ):
        assert f"docs/agent-guides/{guide}" in agents
    assert ".agents/local.md" in gitignore
