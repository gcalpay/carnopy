# Contributing

Carnopy uses standalone uv with the project-local `.venv` environment. The
human operator owns initial uv installation, environment creation, dependency
changes, and synchronization.

After `pyproject.toml` changes, refresh the lock file before synchronizing:

```bash
uv lock
```

For normal development:

```bash
uv sync --locked --extra all --group dev
```

Release-readiness tooling is separate from everyday development:

```bash
uv sync --locked --extra all --group dev --group release
```

Use explicit groups in documented commands even where uv currently supplies a
default group.

Run the local quality gate:

```bash
uv run --locked python scripts/preflight.py
```

Individual checks are:

```bash
uv lock --check
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy src/carnopy
uv run --locked pytest
uv pip check --python .venv/bin/python
```

Keep changes small and explicit. Public configuration names, SI dataset columns,
failure codes, and metadata fields are compatibility contracts. Tests must use
temporary output directories and must not write generated data into repository
`outputs/`.

Git operations, environment bootstrap, release decisions, publishing, and
dependency changes are owned by the human operator.

## Commit messages

Use Conventional Commit-style messages:

```text
<type>(<scope>): <summary>
```

Rules:

- Use a lowercase type and scope.
- Use imperative mood, such as `add`, `fix`, `validate`, `reject`, or `document`.
- Keep the summary concise, ideally no longer than 72 characters.
- Do not end the summary with a period.
- Do not include the repository name unless external context requires it.
- Add a body only when the reason or design tradeoff matters.

Common types:

- `feat`: user-facing or project-facing functionality
- `fix`: bug fix or incorrect behavior correction
- `test`: tests only
- `docs`: documentation only
- `refactor`: internal restructuring without behavior change
- `chore`: maintenance, cleanup, or metadata
- `ci`: CI/CD configuration
- `build`: packaging, dependencies, or build system
- `perf`: performance improvement
- `style`: formatting only, without behavior changes

Recommended Carnopy scopes:

```text
dataset
schema
sampler
coolprop
cli
validation
metadata
tests
docs
ci
packaging
```

Examples:

```text
feat(dataset): add milestone 1 dataset generator
fix(validation): reject duplicate canonical fluids
test(sampler): cover descending stepspace ranges
docs(docs): document generated artifact identities
build(packaging): declare parquet runtime dependency
```
