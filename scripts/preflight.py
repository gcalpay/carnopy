from __future__ import annotations

import importlib
import importlib.metadata
import os
import site
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_IMPORTS = [
    "CoolProp",
    "numpy",
    "pandas",
    "pyarrow",
    "pydantic",
    "typer",
    "yaml",
]


def main() -> int:
    print(f"Python: {sys.version.split()[0]}")
    print(f"Interpreter: {sys.executable}")
    user_site = site.getusersitepackages()
    if user_site in sys.path:
        print(f"Warning: Python user-site packages are enabled for this interpreter: {user_site}")
    for module_name in REQUIRED_IMPORTS:
        module = importlib.import_module(module_name)
        distribution = "PyYAML" if module_name == "yaml" else module_name
        version = importlib.metadata.version(distribution)
        print(f"{module_name}: {version} ({module.__file__})")

    environment = os.environ.copy()
    source_path = str(ROOT / "src")
    environment["PYTHONPATH"] = os.pathsep.join(
        filter(None, [source_path, environment.get("PYTHONPATH", "")])
    )
    commands = [
        [sys.executable, "-m", "ruff", "check", "."],
        [sys.executable, "-m", "ruff", "format", "--check", "."],
        [sys.executable, "-m", "mypy", "src/carnopy"],
        [sys.executable, "-m", "pytest"],
        [sys.executable, "-m", "carnopy", "--help"],
    ]
    for command in commands:
        print(f"+ {' '.join(command)}")
        completed = subprocess.run(
            command,
            cwd=ROOT,
            env=environment,
            check=False,
        )
        if completed.returncode != 0:
            return completed.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
