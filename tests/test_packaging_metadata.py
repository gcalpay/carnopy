from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised on Python 3.10
    import tomli as tomllib


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


def test_desktop_extra_and_launcher_are_declared() -> None:
    root = Path(__file__).resolve().parents[1]
    pyproject: dict[str, Any] = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["optional-dependencies"]["app"] == [
        "PySide6-Essentials>=6.8.3,<7",
        "matplotlib>=3.8",
    ]
    assert pyproject["project"]["scripts"]["carnopy-app"] == "carnopy.app.launcher:main"


def test_alpha_metadata_uses_modern_license_and_release_urls() -> None:
    root = Path(__file__).resolve().parents[1]
    pyproject: dict[str, Any] = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["build-system"] == {
        "requires": ["hatchling>=1.27.0"],
        "build-backend": "hatchling.build",
    }
    project = pyproject["project"]
    assert project["description"] == (
        "Synthetic thermophysical property dataset generation from thermodynamic "
        "databases and simulation backends for physics-informed ML surrogate models."
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
    assert "Programming Language :: Python :: 3.13" in project["classifiers"]
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
    community = root / ".github"
    for name in ("CONTRIBUTING.md", "CODE_OF_CONDUCT.md", "SECURITY.md"):
        assert (community / name).is_file()
    assert not list((root / "docs").glob("*.md"))

    pyproject: dict[str, Any] = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    sdist_includes = set(pyproject["tool"]["hatch"]["build"]["targets"]["sdist"]["include"])
    assert "/README.md" in sdist_includes
    assert "/AGENTS.md" in sdist_includes
    assert not any(path.startswith("/.github") for path in sdist_includes)
    assert "/docs" not in sdist_includes


def test_readme_describes_current_alpha_without_stale_first_release_wording() -> None:
    root = Path(__file__).resolve().parents[1]
    text = (root / "README.md").read_text(encoding="utf-8")
    assert 'python -m pip install "carnopy==0.1.0a2"' in text
    assert 'uv tool install "carnopy[all]==0.1.0a2"' in text
    assert "After `0.1.0a1` is published" not in text
    assert "pending publisher" not in text.casefold()
    assert "Typing: typed" not in text
    assert (
        "Synthetic thermophysical property dataset generation from thermodynamic\n"
        "databases and simulation backends for physics-informed ML surrogate models."
    ) in text


def test_github_community_files_cover_public_reporting_paths() -> None:
    root = Path(__file__).resolve().parents[1]
    github = root / ".github"
    assert (github / "pull_request_template.md").is_file()
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
    assert ".agents/local.md" in gitignore
