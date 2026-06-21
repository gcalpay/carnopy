from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def write_checksums(artifacts: list[Path], output: Path) -> Path:
    if output.exists():
        raise ValueError(f"refusing to overwrite checksum file: {output}")
    if not artifacts:
        raise ValueError("at least one distribution artifact is required")
    filenames = [path.name for path in artifacts]
    if len(set(filenames)) != len(filenames):
        raise ValueError("distribution artifact filenames must be unique")
    lines = [f"{sha256_file(path)}  {path.name}" for path in sorted(artifacts)]
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description="Write SHA-256 checksums for distributions.")
    parser.add_argument("artifacts", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, default=Path("SHA256SUMS"))
    arguments = parser.parse_args()
    output = write_checksums(arguments.artifacts, arguments.output)
    print(f"Wrote checksums: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
