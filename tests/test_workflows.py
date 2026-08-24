from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
ACTION_REFERENCE = re.compile(r"uses:\s+([^@\s]+)@([0-9a-f]{40})")
WORKFLOW_NAMES = (
    "ci.yml",
    "codeql.yml",
    "native-qualification.yml",
    "portability.yml",
    "publish.yml",
    "security.yml",
)


def workflow_text(name: str) -> str:
    return (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")


def dependabot_config() -> dict[str, object]:
    document = yaml.safe_load((ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return document


def workflow_job(text: str, name: str) -> str:
    match = re.search(rf"(?ms)^  {re.escape(name)}:\n.*?(?=^  [a-z][\w-]*:\n|\Z)", text)
    assert match is not None
    return match.group()


def workflow_step(job: str, name: str) -> str:
    match = re.search(rf"(?ms)^      - name: {re.escape(name)}\n.*?(?=^      - name: |\Z)", job)
    assert match is not None
    return match.group()


def workflow_folded_env_values(job: str, name: str) -> tuple[str, ...]:
    match = re.search(
        rf"(?m)^      {re.escape(name)}: >-\n(?P<values>(?:^        [^\n]+\n)+)",
        job,
    )
    assert match is not None
    return tuple(match.group("values").split())


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


def test_test_matrices_cover_supported_python_versions() -> None:
    for name in ("ci.yml", "publish.yml"):
        tests_job = workflow_job(workflow_text(name), "tests")
        for version in ("3.11", "3.12", "3.13", "3.14"):
            assert f'- "{version}"' in tests_job
        assert '- "3.10"' not in tests_job


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
        if name == "ci.yml":
            assert "timeout-minutes: 25" in app_job
            assert app_job.count("timeout --signal=TERM --kill-after=30s 10m") == 2
            assert app_job.count("-o faulthandler_timeout=120") == 2
            assert "tests/test_app_[a-p]*.py" in app_job
            assert "tests/test_app_[q-z]*.py" in app_job
        else:
            assert "tests/test_app_*.py" in app_job
        assert "sudo apt-get install --yes --no-install-recommends libegl1" in app_job
        assert "QT_QPA_PLATFORM: offscreen" in text
        assert "--with-app" in text


def test_desktop_jobs_verify_the_qt_6_11_runtime_baseline() -> None:
    for name in ("ci.yml", "publish.yml"):
        app_job = workflow_job(workflow_text(name), "app")
        step = workflow_step(app_job, "Verify Qt runtime baseline")
        assert "from PySide6.QtCore import qVersion" in step
        assert "(6, 11, 1) <= version < (6, 12)" in step


def test_desktop_jobs_run_the_non_writing_qml_gate() -> None:
    for name in ("ci.yml", "publish.yml"):
        app_job = workflow_job(workflow_text(name), "app")
        step = workflow_step(app_job, "Check QML sources")
        assert "python scripts/check_qml.py" in step
        assert "qmlformat --inplace" not in app_job
        assert app_job.index("Check QML sources") < app_job.index("Run strict desktop mypy")


def test_installed_qml_smoke_covers_three_platforms_without_native_dialogs() -> None:
    downstream = {
        "ci.yml": "distribution",
        "publish.yml": "inspect",
    }
    for name, downstream_name in downstream.items():
        text = workflow_text(name)
        job = workflow_job(text, "qml-smoke")
        for runner in ("ubuntu-latest", "windows-latest", "macos-latest"):
            assert f"          - {runner}" in job
        assert 'python-version: "3.12"' in job
        if name == "ci.yml":
            assert "uv build --wheel --out-dir qml-smoke-dist" in job
        else:
            assert "- build" in job
            assert "actions/download-artifact@" in job
            assert "name: candidate-distributions" in job
        assert '"carnopy[app] @ ${WHEEL_URI}"' in job
        assert 'SMOKE_BIN="$(dirname "$SMOKE_PYTHON")"' in job
        assert 'GUI_LAUNCHER="$SMOKE_BIN/carnopy-gui"' in job
        assert 'APP_LAUNCHER="$SMOKE_BIN/carnopy-app"' in job
        assert 'GUI_LAUNCHER="$GUI_LAUNCHER.exe"' in job
        assert 'APP_LAUNCHER="$APP_LAUNCHER.exe"' in job
        assert '"$GUI_LAUNCHER" --smoke-test' in job
        assert '"$APP_LAUNCHER" --smoke-test' in job
        assert "-m carnopy.app.qml_launcher --smoke-test" not in job
        assert "QT_QPA_PLATFORM=offscreen" in job
        assert "FileDialog" not in job
        assert "FolderDialog" not in job
        assert "if: runner.os == 'Linux'" in job
        assert "sudo apt-get install --yes --no-install-recommends libegl1" in job
        downstream_job = workflow_job(text, downstream_name)
        assert "- qml-smoke" in downstream_job


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


def test_qml_native_qualification_is_manual_and_nonpublishing() -> None:
    text = workflow_text("native-qualification.yml")
    job = workflow_job(text, "qml-native-qualification")
    probe_step = workflow_step(job, "Probe clean Qt Quick runtime")
    build_step = workflow_step(job, "Build Carnopy and native bridge wheels")
    inspect_step = workflow_step(job, "Check and inspect wheels")
    payload_step = workflow_step(job, "Stage isolated qualification payload")
    runtime_step = workflow_step(job, "Run qualification in fresh runtime container")
    assert "workflow_dispatch:" in text
    assert "if:" not in job
    assert "github.ref" not in job
    assert "runs-on: ubuntu-24.04" in job
    assert 'python-version: "3.12"' in job
    assert 'version: "0.11.23"' in job
    assert "aqtinstall==3.3.0" in job
    assert "linux desktop 6.11.1 linux_gcc_64" in job
    assert job.index("Probe clean Qt Quick runtime") < job.index(
        "Build Carnopy and native bridge wheels"
    )
    assert "timeout --foreground --signal=TERM --kill-after=15s 600s" in probe_step
    assert "docker run --rm" in probe_step
    assert "ubuntu:24.04" in probe_step
    assert "PySide6-Essentials==6.11.1" in probe_step
    assert "/qualification/qualification.py smoke-qt-runtime" in probe_step
    assert '--mount "type=bind,src=${PROBE},dst=/qualification,readonly"' in probe_step
    assert "native/carnopy-vtk-bridge/tests/qualification.py" in probe_step
    assert "uv build --wheel" in build_step
    assert "native/carnopy-vtk-bridge" in build_step
    assert "docker" not in build_step
    assert "python -I native/carnopy-vtk-bridge/tests/qualification.py" in inspect_step

    assert 'PAYLOAD="$RUNNER_TEMP/qml-native-payload"' in payload_step
    assert 'mkdir "$PAYLOAD"' in payload_step
    assert 'cp "$ROOT_WHEEL" "$PAYLOAD/"' in payload_step
    assert 'cp "$BRIDGE_WHEEL" "$PAYLOAD/"' in payload_step
    assert 'cp native/carnopy-vtk-bridge/tests/qualification.py "$PAYLOAD/"' in payload_step
    assert 'wc -l)" -eq 3' in payload_step

    assert "timeout --foreground --signal=TERM --kill-after=15s 600s" in runtime_step
    assert "docker run --rm" in runtime_step
    assert "ubuntu:24.04" in runtime_step
    assert runtime_step.count("--mount ") == 1
    assert '--mount "type=bind,src=${PAYLOAD},dst=/qualification,readonly"' in runtime_step
    assert "--volume" not in runtime_step
    assert "GITHUB_WORKSPACE" not in runtime_step
    assert "root-wheel" not in runtime_step
    assert "bridge-wheel" not in runtime_step
    assert "native/carnopy-vtk-bridge" not in runtime_step
    assert "uv build" not in runtime_step

    runtime_packages = workflow_folded_env_values(job, "CARNOPY_QT_RUNTIME_PACKAGES")
    assert len(runtime_packages) == len(set(runtime_packages))
    for package in (
        "binutils",
        "libdbus-1-3",
        "libegl1",
        "libgl1-mesa-dri",
        "libgssapi-krb5-2",
        "mesa-utils",
        "python3.12",
        "python3.12-venv",
        "xauth",
        "xvfb",
    ):
        assert package in runtime_packages
    for step in (probe_step, runtime_step):
        assert "--env CARNOPY_QT_RUNTIME_PACKAGES" in step
        assert 'read -r -a runtime_packages <<< "$CARNOPY_QT_RUNTIME_PACKAGES"' in step
        assert '"${runtime_packages[@]}"' in step

    assert "python3.12 -m venv /opt/carnopy-runtime" in runtime_step
    assert runtime_step.count('"$VENV/bin/python" -I') == 3
    assert '"carnopy[app] @ file://${ROOT_WHEEL}"' in runtime_step
    assert '"$BRIDGE_WHEEL"' in runtime_step
    for variable in (
        "CMAKE_ARGS",
        "CMAKE_BUILD_PARALLEL_LEVEL",
        "CMAKE_GENERATOR",
        "CMAKE_PREFIX_PATH",
        "LD_LIBRARY_PATH",
        "PYTHONHOME",
        "PYTHONPATH",
        "QML2_IMPORT_PATH",
        "QML_IMPORT_PATH",
        "QTDIR",
        "QT_PLUGIN_PATH",
        "Qt6_DIR",
    ):
        assert re.search(rf"^\s+{re.escape(variable)}(?: \\)?$", runtime_step, re.MULTILINE)
    assert "LIBGL_ALWAYS_SOFTWARE=1" in runtime_step
    assert "QSG_RHI_BACKEND=opengl" in runtime_step
    assert "QT_OPENGL=software" in runtime_step
    assert "QT_QPA_PLATFORM=xcb" in runtime_step
    assert "glxinfo -B" in runtime_step
    assert "llvmpipe|softpipe|software rasterizer" in runtime_step
    assert "xvfb-run --auto-servernum" in runtime_step

    for forbidden in (
        "actions/upload-artifact",
        "id-token: write",
        "environment:",
        "gh release",
        "pypa/gh-action-pypi-publish",
        "twine upload",
        "pgrep",
    ):
        assert forbidden not in job
    assert "--extra 3d" not in job


def test_codeql_security_and_portability_workflows_are_explicit() -> None:
    codeql = workflow_text("codeql.yml")
    assert "schedule:" in codeql
    assert "workflow_dispatch:" in codeql
    assert codeql.count("github/codeql-action/init@") == 1
    assert codeql.count("github/codeql-action/analyze@") == 1

    security = workflow_text("security.yml")
    audit = workflow_job(security, "audit")
    assert "pull_request:\n    branches:\n      - main" in security
    assert 'cron: "29 4 * * 1"' in security
    assert "workflow_dispatch:" in security
    assert "name: Audit all dependencies" in audit
    assert "matrix:" not in audit
    assert "--extra all" in audit
    assert "PROFILE" not in audit
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


def test_dependabot_uses_safe_weekly_update_groups() -> None:
    config = dependabot_config()
    assert config["version"] == 2
    updates = config["updates"]
    assert isinstance(updates, list)
    by_ecosystem = {update["package-ecosystem"]: update for update in updates}
    assert set(by_ecosystem) == {"uv", "github-actions"}

    for update in by_ecosystem.values():
        assert update["directory"] == "/"
        assert update["schedule"] == {
            "interval": "weekly",
            "day": "monday",
            "time": "04:29",
            "timezone": "Etc/UTC",
        }
        assert update["open-pull-requests-limit"] == 5

    uv = by_ecosystem["uv"]
    assert uv["exclude-paths"] == ["native/carnopy-vtk-bridge/**"]
    assert uv["groups"] == {
        "patch-updates": {
            "applies-to": "version-updates",
            "patterns": ["*"],
            "update-types": ["patch"],
        }
    }

    actions = by_ecosystem["github-actions"]
    assert actions["groups"] == {
        "minor-and-patch-updates": {
            "applies-to": "version-updates",
            "patterns": ["*"],
            "update-types": ["minor", "patch"],
        }
    }

    text = (ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8")
    assert "security-updates" not in text
    assert "auto-merge" not in text
    assert "auto-approve" not in text
