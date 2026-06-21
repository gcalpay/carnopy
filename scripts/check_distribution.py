from __future__ import annotations

import argparse
import re
import tarfile
import zipfile
from email.message import Message
from email.parser import Parser
from pathlib import Path, PurePosixPath
from typing import Protocol

PROJECT_NAME = "carnopy"
SOURCE_VERSION_PATTERN = re.compile(r'^__version__\s*=\s*"([^"]+)"\s*$')
WHEEL_REQUIRED = {
    "carnopy/__init__.py",
    "carnopy/__main__.py",
    "carnopy/cli.py",
    "carnopy/py.typed",
    "carnopy/templates/__init__.py",
    "carnopy/templates/property_table.yaml",
    "carnopy/templates/saturation_table.yaml",
    "carnopy/templates/vapor_mass_fraction_table.yaml",
}
SDIST_REQUIRED = {
    "AGENTS.md",
    "CONTRIBUTING.md",
    "LICENSE",
    "README.md",
    "configs/property_table_example.yaml",
    "configs/saturation_table_example.yaml",
    "configs/vapor_mass_fraction_table_example.yaml",
    "docs/architecture.md",
    "docs/configuration.md",
    "docs/data-policy.md",
    "docs/visualization.md",
    "pyproject.toml",
    "scripts/check_distribution.py",
    "scripts/hash_distributions.py",
    "scripts/smoke_installed.py",
    "scripts/verify_index_release.py",
    "src/carnopy/__init__.py",
    "src/carnopy/py.typed",
    "src/carnopy/templates/property_table.yaml",
    "tests/test_cli.py",
    "uv.lock",
}
FORBIDDEN_ANYWHERE = {
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
}
FORBIDDEN_TOP_LEVEL = {
    ".venv",
    "build",
    "dist",
    "figures",
    "outputs",
}


class DistributionReader(Protocol):
    def names(self) -> set[str]: ...

    def read(self, name: str) -> bytes: ...


class WheelReader:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.archive = zipfile.ZipFile(path)

    def __enter__(self) -> WheelReader:
        return self

    def __exit__(self, *_args: object) -> None:
        self.archive.close()

    def names(self) -> set[str]:
        return set(self.archive.namelist())

    def read(self, name: str) -> bytes:
        return self.archive.read(name)


class SdistReader:
    def __init__(self, path: Path) -> None:
        self.path = path
        # The reader itself is a context manager and closes this archive in __exit__.
        self.archive = tarfile.open(path, mode="r:gz")  # noqa: SIM115

    def __enter__(self) -> SdistReader:
        return self

    def __exit__(self, *_args: object) -> None:
        self.archive.close()

    def names(self) -> set[str]:
        return {
            member.name.removeprefix("./")
            for member in self.archive.getmembers()
            if member.isfile()
        }

    def read(self, name: str) -> bytes:
        member = self.archive.getmember(name)
        stream = self.archive.extractfile(member)
        if stream is None:
            raise ValueError(f"could not read archive member {name}")
        with stream:
            return stream.read()


def source_version(path: Path) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        match = SOURCE_VERSION_PATTERN.fullmatch(line.strip())
        if match is not None:
            return match.group(1)
    raise ValueError(f"could not find __version__ in {path}")


def parse_metadata(content: bytes) -> Message:
    return Parser().parsestr(content.decode("utf-8"))


def validate_metadata(metadata: Message, expected_version: str, *, artifact: str) -> None:
    if metadata.get("Name", "").casefold() != PROJECT_NAME:
        raise ValueError(f"{artifact} metadata Name is not {PROJECT_NAME!r}")
    if metadata.get("Version") != expected_version:
        raise ValueError(
            f"{artifact} metadata version {metadata.get('Version')!r} "
            f"does not match {expected_version!r}"
        )
    if metadata.get("License-Expression") != "MIT":
        raise ValueError(f"{artifact} does not declare License-Expression: MIT")
    if "LICENSE" not in metadata.get_all("License-File", []):
        raise ValueError(f"{artifact} metadata does not record LICENSE")
    classifiers = metadata.get_all("Classifier", [])
    if "Typing :: Typed" not in classifiers:
        raise ValueError(f"{artifact} metadata does not declare Typing :: Typed")
    private = [classifier for classifier in classifiers if classifier.startswith("Private ::")]
    if private:
        raise ValueError(f"{artifact} contains forbidden private classifiers: {private}")
    urls = metadata.get_all("Project-URL", [])
    if not any(value.startswith("Repository, ") for value in urls):
        raise ValueError(f"{artifact} metadata does not contain the Repository project URL")
    if not any(value.startswith("Issues, ") for value in urls):
        raise ValueError(f"{artifact} metadata does not contain the Issues project URL")
    extras = set(metadata.get_all("Provides-Extra", []))
    if extras != {"all", "viz"}:
        raise ValueError(f"{artifact} metadata declares unexpected optional extras: {extras}")
    matplotlib_requirements = [
        requirement
        for requirement in metadata.get_all("Requires-Dist", [])
        if requirement.casefold().startswith("matplotlib")
    ]
    if len(matplotlib_requirements) != 2 or any(
        "extra ==" not in requirement for requirement in matplotlib_requirements
    ):
        raise ValueError(f"{artifact} must declare Matplotlib only through all and viz extras")


def forbidden_paths(names: set[str], *, strip_root: bool) -> list[str]:
    invalid: list[str] = []
    for name in names:
        path = PurePosixPath(name)
        parts = path.parts[1:] if strip_root and path.parts else path.parts
        if (
            any(part.endswith(".ipynb") for part in parts)
            or (parts and parts[0] in FORBIDDEN_TOP_LEVEL)
            or any(part in FORBIDDEN_ANYWHERE for part in parts)
        ):
            invalid.append(name)
        if any(part.endswith((".pyc", ".pyo")) for part in parts):
            invalid.append(name)
    return sorted(set(invalid))


def inspect_wheel(path: Path, expected_version: str) -> None:
    with WheelReader(path) as reader:
        names = reader.names()
        missing = sorted(WHEEL_REQUIRED - names)
        if missing:
            raise ValueError(f"wheel is missing required files: {', '.join(missing)}")
        invalid = forbidden_paths(names, strip_root=False)
        if invalid:
            raise ValueError(f"wheel contains forbidden files: {', '.join(invalid)}")
        if any(name.startswith("tests/") for name in names):
            raise ValueError("wheel must not contain tests")

        metadata_names = [name for name in names if name.endswith(".dist-info/METADATA")]
        entry_point_names = [name for name in names if name.endswith(".dist-info/entry_points.txt")]
        license_names = [name for name in names if name.endswith(".dist-info/licenses/LICENSE")]
        if len(metadata_names) != 1 or len(entry_point_names) != 1 or len(license_names) != 1:
            raise ValueError("wheel dist-info metadata, entry point, or license layout is invalid")
        validate_metadata(
            parse_metadata(reader.read(metadata_names[0])),
            expected_version,
            artifact="wheel",
        )
        entry_points = reader.read(entry_point_names[0]).decode("utf-8")
        if "carnopy = carnopy.__main__:main" not in entry_points:
            raise ValueError("wheel does not contain the carnopy console entry point")


def inspect_sdist(path: Path, expected_version: str) -> None:
    with SdistReader(path) as reader:
        names = reader.names()
        roots = {PurePosixPath(name).parts[0] for name in names if PurePosixPath(name).parts}
        if len(roots) != 1:
            raise ValueError(
                f"sdist must contain exactly one root directory, found {sorted(roots)}"
            )
        root = next(iter(roots))
        relative = {
            PurePosixPath(name).relative_to(root).as_posix() for name in names if name != root
        }
        missing = sorted(SDIST_REQUIRED - relative)
        if missing:
            raise ValueError(f"sdist is missing required files: {', '.join(missing)}")
        invalid = forbidden_paths(names, strip_root=True)
        if invalid:
            raise ValueError(f"sdist contains forbidden files: {', '.join(invalid)}")

        metadata_name = f"{root}/PKG-INFO"
        if metadata_name not in names:
            raise ValueError("sdist does not contain PKG-INFO")
        validate_metadata(
            parse_metadata(reader.read(metadata_name)),
            expected_version,
            artifact="sdist",
        )
        template_pairs = {
            "property_table": "property_table_example",
            "saturation_table": "saturation_table_example",
            "vapor_mass_fraction_table": "vapor_mass_fraction_table_example",
        }
        for template, example in template_pairs.items():
            packaged = reader.read(f"{root}/src/carnopy/templates/{template}.yaml")
            repository = reader.read(f"{root}/configs/{example}.yaml")
            if packaged != repository:
                raise ValueError(f"sdist template {template!r} differs from its repository example")


def distribution_paths(paths: list[Path]) -> tuple[Path, Path]:
    wheels = [path for path in paths if path.suffix == ".whl"]
    sdists = [path for path in paths if path.name.endswith(".tar.gz")]
    if len(wheels) != 1 or len(sdists) != 1 or len(paths) != 2:
        raise ValueError("expected exactly one wheel and one .tar.gz source distribution")
    return wheels[0], sdists[0]


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect Carnopy wheel and sdist contents.")
    parser.add_argument("artifacts", nargs="+", type=Path)
    parser.add_argument("--expected-version")
    parser.add_argument(
        "--source-version-file",
        type=Path,
        default=Path("src/carnopy/_version.py"),
    )
    arguments = parser.parse_args()

    expected_version = arguments.expected_version or source_version(arguments.source_version_file)
    actual_source_version = source_version(arguments.source_version_file)
    if expected_version != actual_source_version:
        raise ValueError(
            f"expected version {expected_version!r} does not match source "
            f"version {actual_source_version!r}"
        )
    wheel, sdist = distribution_paths(arguments.artifacts)
    inspect_wheel(wheel, expected_version)
    inspect_sdist(sdist, expected_version)
    print(f"Verified wheel: {wheel}")
    print(f"Verified sdist: {sdist}")
    print(f"Version: {expected_version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
