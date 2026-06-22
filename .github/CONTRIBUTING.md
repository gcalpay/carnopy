# Contributing to Carnopy

Thank you for considering a contribution to Carnopy.

Carnopy generates reproducible, backend-derived thermophysical datasets. Changes
to scientific interpretation, public configuration, schemas, provenance, or
failure semantics require more review than ordinary implementation changes.

## Before opening a pull request

Open an issue before implementing:

- new scientific behavior or property backends;
- changes to public YAML, CLI, Python, dataset, metadata, or report contracts;
- changes to units, sampling, phase interpretation, or reference-state policy;
- large refactors or new dependencies.

Small fixes to documentation, tests, and clearly incorrect behavior may go
directly to a pull request.

Read [AGENTS.md](../AGENTS.md) before changing code. It records the architecture,
scientific invariants, compatibility boundaries, and release safeguards.

## Development setup

Carnopy uses [uv](https://docs.astral.sh/uv/), a project-local environment, and
the committed lock file:

```bash
uv sync --locked --extra all --group dev
```

Release-maintainer tooling is separate:

```bash
uv sync --locked --extra all --group dev --group release
```

Do not introduce `requirements.txt` files. `pyproject.toml` and `uv.lock` are
authoritative.

## Quality checks

Run:

```bash
uv lock --check
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy src/carnopy
uv run --locked pytest
uv run --locked python scripts/preflight.py
uv pip check --python .venv/bin/python
```

Add a focused regression test for every changed contract or corrected failure
mode. Prefer parametrization over duplicating equivalent cases. Scientific
regressions should use defensible references and tolerances rather than brittle
full-table snapshots.

Tests must use temporary directories. Do not commit generated datasets, figures,
caches, virtual environments, or build artifacts.

## Pull requests

Keep pull requests focused and explain:

- the problem and intended outcome;
- public compatibility impact;
- scientific assumptions and references;
- tests and documentation added;
- dependency or packaging changes.

Use Conventional Commit summaries:

```text
<type>(<scope>): <imperative summary>
```

Examples:

```text
fix(validation): reject duplicate canonical fluids
docs(project): clarify visualization provenance
test(sampler): cover descending stepspace ranges
```

Submitting a contribution means agreeing to the
[Code of Conduct](CODE_OF_CONDUCT.md).
