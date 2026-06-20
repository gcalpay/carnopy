# Contributing

Use the existing `qsink` environment for local development. Do not install or
upgrade dependencies without human approval.

Run the local quality gate:

```bash
PYTHONPATH=src python scripts/preflight.py
```

Individual checks are:

```bash
python -m ruff check .
python -m ruff format --check .
python -m mypy src/carnopy
python -m pytest
```

Keep changes small and explicit. Public configuration names, SI dataset columns,
failure codes, and metadata fields are compatibility contracts. Tests must use
temporary output directories and must not write generated data into repository
`outputs/`.

Git operations, release decisions, publishing, and dependency changes are owned
by the human operator.

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
