from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, cast

CHUNK_SIZE = 1024 * 1024
USER_AGENT = "carnopy-release-verifier/1"


def load_checksums(path: Path) -> dict[str, str]:
    checksums: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        digest, separator, filename = line.partition("  ")
        if separator != "  " or len(digest) != 64 or not filename:
            raise ValueError(f"invalid SHA256SUMS line: {line!r}")
        if Path(filename).name != filename:
            raise ValueError(f"checksum filename must not contain directories: {filename!r}")
        if filename in checksums:
            raise ValueError(f"duplicate checksum filename: {filename}")
        checksums[filename] = digest
    if len(checksums) != 2:
        raise ValueError("SHA256SUMS must contain exactly one wheel and one source distribution")
    if sum(filename.endswith(".whl") for filename in checksums) != 1:
        raise ValueError("SHA256SUMS must contain exactly one wheel")
    if sum(filename.endswith(".tar.gz") for filename in checksums) != 1:
        raise ValueError("SHA256SUMS must contain exactly one .tar.gz source distribution")
    return checksums


def release_json_url(index_base: str, project: str, version: str) -> str:
    base = index_base.rstrip("/")
    return (
        f"{base}/{urllib.parse.quote(project, safe='')}/{urllib.parse.quote(version, safe='')}/json"
    )


def fetch_release(
    *,
    index_base: str,
    project: str,
    version: str,
    retries: int,
    delay_seconds: float,
) -> dict[str, Any]:
    url = release_json_url(index_base, project, version)
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.load(response)
            if not isinstance(payload, dict):
                raise ValueError("release JSON root must be an object")
            return cast(dict[str, Any], payload)
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                raise
            last_error = exc
        except urllib.error.URLError as exc:
            last_error = exc
        if attempt < retries:
            time.sleep(delay_seconds)
    raise RuntimeError(f"release did not become available at {url}: {last_error}")


def release_files(payload: dict[str, Any], checksums: dict[str, str]) -> dict[str, dict[str, Any]]:
    urls = payload.get("urls")
    if not isinstance(urls, list):
        raise ValueError("release JSON does not contain a urls list")
    selected: dict[str, dict[str, Any]] = {}
    for raw_item in urls:
        if not isinstance(raw_item, dict):
            continue
        item = cast(dict[str, Any], raw_item)
        filename = item.get("filename")
        if not isinstance(filename, str) or filename not in checksums:
            continue
        if filename in selected:
            raise ValueError(f"release JSON contains duplicate file entry for {filename}")
        selected[filename] = item
    missing = sorted(set(checksums) - set(selected))
    if missing:
        raise ValueError(f"release JSON is missing expected files: {', '.join(missing)}")
    return selected


def verify_api_digest(item: dict[str, Any], expected: str, filename: str) -> str:
    digests = item.get("digests")
    api_digest = digests.get("sha256") if isinstance(digests, dict) else None
    if not isinstance(api_digest, str):
        raise ValueError(f"release JSON does not provide a SHA-256 digest for {filename}")
    if api_digest != expected:
        raise ValueError(
            f"release JSON SHA-256 mismatch for {filename}: {api_digest} != {expected}"
        )
    url = item.get("url")
    if not isinstance(url, str) or urllib.parse.urlparse(url).scheme != "https":
        raise ValueError(f"release JSON provides an invalid download URL for {filename}")
    return url


def download_verified_file(url: str, destination: Path, expected_sha256: str) -> Path:
    if destination.exists():
        raise ValueError(f"refusing to overwrite downloaded file: {destination}")
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.part")
    digest = hashlib.sha256()
    try:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with (
            urllib.request.urlopen(request, timeout=60) as response,
            temporary.open("xb") as stream,
        ):
            while chunk := response.read(CHUNK_SIZE):
                digest.update(chunk)
                stream.write(chunk)
        actual = digest.hexdigest()
        if actual != expected_sha256:
            raise ValueError(
                f"downloaded SHA-256 mismatch for {destination.name}: {actual} != {expected_sha256}"
            )
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def download_release(
    *,
    payload: dict[str, Any],
    checksums: dict[str, str],
    output_directory: Path,
) -> list[Path]:
    output_directory.mkdir(parents=True, exist_ok=True)
    selected = release_files(payload, checksums)
    downloaded: list[Path] = []
    for filename in sorted(checksums):
        item = selected[filename]
        url = verify_api_digest(item, checksums[filename], filename)
        downloaded.append(
            download_verified_file(url, output_directory / filename, checksums[filename])
        )
    return downloaded


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download and verify one Carnopy release from a PyPI-compatible index."
    )
    parser.add_argument("--index-base", required=True)
    parser.add_argument("--project", default="carnopy")
    parser.add_argument("--version", required=True)
    parser.add_argument("--checksums", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--retries", type=int, default=18)
    parser.add_argument("--delay-seconds", type=float, default=10.0)
    arguments = parser.parse_args()
    if arguments.retries < 1:
        raise ValueError("--retries must be at least 1")
    if arguments.delay_seconds < 0:
        raise ValueError("--delay-seconds must not be negative")

    checksums = load_checksums(arguments.checksums)
    payload = fetch_release(
        index_base=arguments.index_base,
        project=arguments.project,
        version=arguments.version,
        retries=arguments.retries,
        delay_seconds=arguments.delay_seconds,
    )
    downloaded = download_release(
        payload=payload,
        checksums=checksums,
        output_directory=arguments.output_directory,
    )
    for path in downloaded:
        print(path.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
