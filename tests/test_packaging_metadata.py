from __future__ import annotations

from pathlib import Path
from typing import Any

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


def test_alpha_metadata_uses_modern_license_and_release_urls() -> None:
    root = Path(__file__).resolve().parents[1]
    pyproject: dict[str, Any] = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["build-system"] == {
        "requires": ["hatchling>=1.27.0"],
        "build-backend": "hatchling.build",
    }
    project = pyproject["project"]
    assert project["license"] == "MIT"
    assert project["license-files"] == ["LICENSE"]
    assert project["urls"] == {
        "Repository": "https://github.com/gcalpay/carnopy",
        "Issues": "https://github.com/gcalpay/carnopy/issues",
    }
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


def test_public_markdown_is_consolidated() -> None:
    root = Path(__file__).resolve().parents[1]
    assert (root / "README.md").is_file()
    assert (root / "AGENTS.md").is_file()
    assert not (root / "CONTRIBUTING.md").exists()
    assert not list((root / "docs").glob("*.md"))

    pyproject: dict[str, Any] = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    sdist_includes = set(pyproject["tool"]["hatch"]["build"]["targets"]["sdist"]["include"])
    assert "/README.md" in sdist_includes
    assert "/AGENTS.md" in sdist_includes
    assert "/CONTRIBUTING.md" not in sdist_includes
    assert "/docs" not in sdist_includes


def test_public_agents_bootstraps_ignored_local_policy() -> None:
    root = Path(__file__).resolve().parents[1]
    agents = (root / "AGENTS.md").read_text(encoding="utf-8")
    gitignore = (root / ".gitignore").read_text(encoding="utf-8")
    assert "<repository-root>/.agents/local.md" in agents
    assert "highest-priority repository instruction" in agents
    assert ".agents/local.md" in gitignore
