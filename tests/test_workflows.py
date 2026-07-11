from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ACTION_REFERENCE = re.compile(r"uses:\s+([^@\s]+)@([0-9a-f]{40})")
WORKFLOW_NAMES = (
    "ci.yml",
    "codeql.yml",
    "portability.yml",
    "publish.yml",
    "security.yml",
)


def workflow_text(name: str) -> str:
    return (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")


def workflow_job(text: str, name: str) -> str:
    match = re.search(rf"(?ms)^  {re.escape(name)}:\n.*?(?=^  [a-z][\w-]*:\n|\Z)", text)
    assert match is not None
    return match.group()


def test_third_party_actions_are_pinned_to_full_commit_shas() -> None:
    for name in WORKFLOW_NAMES:
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


def test_core_and_desktop_dependencies_are_isolated() -> None:
    for name in ("ci.yml", "publish.yml"):
        text = workflow_text(name)
        quality_job = workflow_job(text, "quality")
        tests_job = workflow_job(text, "tests")
        app_job = workflow_job(text, "app")
        assert "--extra viz --extra ml --group dev" in quality_job
        assert "--extra all" not in quality_job
        assert "--extra app" not in quality_job
        assert "libegl1" not in quality_job
        assert "scripts/preflight.py" not in quality_job
        assert "mypy src/carnopy --exclude '^src/carnopy/app/'" in quality_job
        assert "--extra viz --extra ml" in tests_job
        assert "--extra analysis" in tests_job
        assert "--no-default-groups --group test pytest" in tests_job
        assert "--ignore-glob=tests/test_app_*.py" in tests_job
        assert "libegl1" not in tests_job
        assert "--extra app --no-default-groups --group test --group type" in app_job
        assert "uv run --locked --extra app --no-default-groups --group type" in app_job
        assert "uv run --locked --extra app --no-default-groups --group test" in app_job
        assert "mypy src/carnopy/app" in app_job
        assert "tests/test_app_*.py" in app_job
        assert "sudo apt-get install --yes --no-install-recommends libegl1" in app_job
        assert "QT_QPA_PLATFORM: offscreen" in text
        assert "--with-app" in text
    assert workflow_text("ci.yml").count("libegl1") == 2
    assert workflow_text("publish.yml").count("libegl1") == 3


def test_distribution_checks_install_qt_only_after_core_smokes() -> None:
    jobs = {
        "ci.yml": workflow_job(workflow_text("ci.yml"), "distribution"),
        "publish.yml": workflow_job(workflow_text("publish.yml"), "inspect"),
    }
    for job in jobs.values():
        assert "--extra all --group dev" not in job
        assert job.count("sudo apt-get install --yes --no-install-recommends libegl1") == 1
        assert job.index("Smoke-test wheel with ML extra") < job.index("Smoke-test sdist")
        assert job.index("Smoke-test sdist") < job.index("Smoke-test wheel with analysis extra")
        assert job.index("Smoke-test wheel with analysis extra") < job.index(
            "Install Qt runtime dependency"
        )
        assert job.index("Install Qt runtime dependency") < job.index(
            "Smoke-test wheel with app extra"
        )
        assert job.index("Smoke-test wheel with app extra") < job.index(
            "Smoke-test wheel with all extras"
        )


def test_dependency_review_is_pull_request_only() -> None:
    text = workflow_text("ci.yml")
    job = workflow_job(text, "dependency-review")
    assert "if: github.event_name == 'pull_request'" in job
    assert "actions/dependency-review-action@" in job


def test_codeql_security_and_portability_workflows_are_explicit() -> None:
    codeql = workflow_text("codeql.yml")
    assert "schedule:" in codeql
    assert "workflow_dispatch:" in codeql
    assert codeql.count("github/codeql-action/init@") == 1
    assert codeql.count("github/codeql-action/analyze@") == 1

    security = workflow_text("security.yml")
    for profile in ("base", "viz", "ml", "analysis", "app", "all"):
        assert f"          - {profile}" in security
    assert "pypa/gh-action-pip-audit@" in security
    assert "--no-emit-project" in security
    assert "require-hashes: true" in security

    portability = workflow_text("portability.yml")
    for runner in ("ubuntu-latest", "windows-latest", "macos-latest"):
        assert f"          - {runner}" in portability
    assert "--ignore-glob=tests/test_app_*.py" in portability
    assert "--extra app" not in portability
    assert "--extra analysis" in portability
    assert "libegl1" not in portability
