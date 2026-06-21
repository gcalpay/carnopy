from __future__ import annotations

import hashlib
import importlib.util
import io
import urllib.request
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str) -> ModuleType:
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"carnopy_test_{name}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load test script {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


check_distribution = load_script("check_distribution")
hash_distributions = load_script("hash_distributions")
verify_index_release = load_script("verify_index_release")


def test_distribution_checksums_are_deterministic_and_non_overwriting(tmp_path: Path) -> None:
    wheel = tmp_path / "carnopy-0.1.0a1-py3-none-any.whl"
    sdist = tmp_path / "carnopy-0.1.0a1.tar.gz"
    wheel.write_bytes(b"wheel")
    sdist.write_bytes(b"sdist")
    output = tmp_path / "SHA256SUMS"
    hash_distributions.write_checksums([sdist, wheel], output)
    assert output.read_text(encoding="utf-8").splitlines() == [
        f"{hashlib.sha256(wheel.read_bytes()).hexdigest()}  {wheel.name}",
        f"{hashlib.sha256(sdist.read_bytes()).hexdigest()}  {sdist.name}",
    ]
    with pytest.raises(ValueError, match="refusing to overwrite"):
        hash_distributions.write_checksums([wheel, sdist], output)


def test_release_downloader_uses_api_urls_and_verifies_hashes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    files = {
        "carnopy-0.1.0a1-py3-none-any.whl": b"wheel-content",
        "carnopy-0.1.0a1.tar.gz": b"sdist-content",
    }
    checksums_path = tmp_path / "SHA256SUMS"
    checksums_path.write_text(
        "".join(
            f"{hashlib.sha256(content).hexdigest()}  {filename}\n"
            for filename, content in files.items()
        ),
        encoding="utf-8",
    )
    checksums = verify_index_release.load_checksums(checksums_path)
    urls = {filename: f"https://files.example.invalid/releases/{filename}" for filename in files}
    payload = {
        "urls": [
            {
                "filename": filename,
                "url": urls[filename],
                "digests": {"sha256": checksums[filename]},
            }
            for filename in files
        ]
    }

    def fake_urlopen(request: urllib.request.Request, timeout: int) -> io.BytesIO:
        del timeout
        url = request.full_url
        filename = url.rsplit("/", 1)[-1]
        return io.BytesIO(files[filename])

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    output = tmp_path / "downloaded"
    downloaded = verify_index_release.download_release(
        payload=payload,
        checksums=checksums,
        output_directory=output,
    )
    assert {path.name: path.read_bytes() for path in downloaded} == files


def test_distribution_path_filters_and_source_version() -> None:
    assert check_distribution.source_version(ROOT / "src/carnopy/_version.py") == "0.1.0a1"
    invalid = check_distribution.forbidden_paths(
        {
            "carnopy-0.1.0a1/scratch.ipynb",
            "carnopy-0.1.0a1/src/carnopy/__pycache__/module.pyc",
            "carnopy-0.1.0a1/src/carnopy/__init__.py",
        },
        strip_root=True,
    )
    assert invalid == [
        "carnopy-0.1.0a1/scratch.ipynb",
        "carnopy-0.1.0a1/src/carnopy/__pycache__/module.pyc",
    ]
