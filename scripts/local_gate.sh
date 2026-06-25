#!/usr/bin/env bash
set -euo pipefail

build_out="${1:-prerelease/local-gate}"

echo "+ uv lock --check"
uv lock --check

echo "+ uv run --locked ruff check ."
uv run --locked ruff check .

echo "+ uv run --locked ruff format --check ."
uv run --locked ruff format --check .

echo "+ uv run --locked mypy src/carnopy"
uv run --locked mypy src/carnopy

echo "+ uv run --locked pytest"
uv run --locked pytest

echo "+ uv run --locked python scripts/preflight.py"
uv run --locked python scripts/preflight.py

echo "+ uv pip check --python .venv/bin/python"
uv pip check --python .venv/bin/python

echo "+ uv run --locked --group release python -m build --outdir ${build_out}"
uv run --locked --group release python -m build --outdir "${build_out}"

echo "+ uv run --locked --group release python -m twine check ${build_out}/*"
uv run --locked --group release python -m twine check "${build_out}"/*

echo "+ uv run --locked python scripts/check_distribution.py ${build_out}/*"
uv run --locked python scripts/check_distribution.py "${build_out}"/*

echo "Local gate passed. Build artifacts: ${build_out}"
