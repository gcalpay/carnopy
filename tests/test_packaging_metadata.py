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
    assert not any(classifier.startswith("Private ::") for classifier in project["classifiers"])
    assert "License :: OSI Approved :: MIT License" not in project["classifiers"]
