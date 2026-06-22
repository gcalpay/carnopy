from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ACTION_REFERENCE = re.compile(r"uses:\s+([^@\s]+)@([0-9a-f]{40})")


def workflow_text(name: str) -> str:
    return (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")


def test_third_party_actions_are_pinned_to_full_commit_shas() -> None:
    for name in ("ci.yml", "publish.yml"):
        text = workflow_text(name)
        references = ACTION_REFERENCE.findall(text)
        assert references
        assert text.count("uses:") == len(references)


def test_publish_workflow_builds_once_and_scopes_oidc_to_publish_jobs() -> None:
    text = workflow_text("publish.yml")
    assert text.count("python -m build") == 1
    assert text.count("id-token: write") == 1
    assert "skip-existing" not in text
    assert 'tags:\n      - "v*"' in text
    assert "candidate-distributions" in text
    assert "verified-distributions" in text


def test_publish_smoke_install_uses_only_production_pypi() -> None:
    text = workflow_text("publish.yml")
    assert "--extra-index-url" not in text
    assert text.count("--index-url https://pypi.org/simple/") >= 1
    assert "test.pypi.org" not in text
    assert "https://pypi.org/pypi" in text
    direct_publish = (
        "publish-pypi:\n    name: Approve and publish to PyPI\n    needs:\n      - inspect"
    )
    assert direct_publish in text


def test_ci_matrix_covers_supported_python_versions() -> None:
    text = workflow_text("ci.yml")
    for version in ("3.10", "3.11", "3.12", "3.13"):
        assert f'- "{version}"' in text
