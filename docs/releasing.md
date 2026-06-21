# Release process

Carnopy `0.1.0a1` is a functional alpha, not a placeholder package. The PyPI
name is claimed only after production PyPI accepts the distribution.

## Human prerequisites

1. Create a separate TestPyPI account and enable 2FA.
2. Make `gcalpay/carnopy` public.
3. Create GitHub environments:
   - `testpypi`
   - `pypi`, with required reviewers
4. Register pending Trusted Publishers on both indexes:
   - project: `carnopy`
   - owner: `gcalpay`
   - repository: `carnopy`
   - workflow: `publish.yml`
   - matching environment
5. Confirm that `carnopy` is still available immediately before release.

Case variants such as `CarnoPy` normalize to `carnopy`. Names containing a
separator, such as `carno-py`, normalize to a different project name.

## Verification

Synchronize release tools:

```bash
uv sync --locked --extra all --group dev --group release
```

Run:

```bash
uv lock --check
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy src/carnopy
uv run --locked pytest
uv run --locked python scripts/preflight.py
uv run --locked --group release python -m build
uv run --locked --group release python -m twine check dist/*
uv run --locked python scripts/check_distribution.py dist/*
uv pip check --python .venv/bin/python
```

Build cleanup is human-controlled. Use a fresh checkout or explicitly remove
stale `dist/` and `build/` before release inspection.

## Trusted publication

The human creates and pushes:

```bash
git tag -a v0.1.0a1 -m "Release carnopy 0.1.0a1"
git push origin v0.1.0a1
```

The workflow:

1. Runs quality checks and Python 3.10–3.13 tests.
2. Builds one wheel and one sdist exactly once.
3. Inspects and smoke-tests those files.
4. Writes `SHA256SUMS`.
5. Publishes the verified files to TestPyPI.
6. Downloads them through TestPyPI's JSON API and verifies their hashes.
7. Waits for human approval on the `pypi` environment.
8. Publishes the same wheel and sdist bytes to production PyPI.
9. Downloads and verifies the production files.

Only publish jobs receive `id-token: write`. No API token or `skip-existing`
setting is used.

## Immutability

- Never change and republish an uploaded version.
- Any payload change requires `0.1.0a2` or later.
- Never move a pushed release tag.
- Never delete a release to reuse its version.
- A failed TestPyPI verification blocks production.
- Rerun downstream smoke jobs without republishing when uploaded bytes are
  already correct.
