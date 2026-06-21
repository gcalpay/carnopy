# AGENTS.md

## Scope and authority

This file applies to `/home/cfd/carnopy/` and every subdirectory unless a more
specific nested `AGENTS.md` is added later.

The repository is `gcalpay/carnopy`. Canonical names are:

```text
Project: Carnopy
Repository: carnopy
Distribution: carnopy
Import package: carnopy
CLI: carnopy
```

CoolProp is the first backend dependency, not the project identity.

## Hard boundaries

- Work only inside `/home/cfd/carnopy/`.
- Do not run Git commands. The human owns Git history, branches, tags, remotes,
  pushes, and repository settings.
- Do not publish to TestPyPI or PyPI.
- Do not create or handle package-index tokens.
- Do not configure GitHub environments or Trusted Publishers.
- Do not install, upgrade, remove, or synchronize dependencies without explicit
  human approval.
- Do not create or replace Python environments.
- Do not use destructive filesystem commands without explicit approval.
- Preserve unrelated human changes.

The human owns dependency decisions, environment bootstrap, GitHub visibility,
release approval, version tags, and publication.

## Development environment

Use standalone uv 0.11.23 and the project-local environment:

```text
/home/cfd/carnopy/.venv
```

`pyproject.toml` and `uv.lock` are authoritative. Do not recreate
`requirements.txt` files.

Normal development:

```bash
uv sync --locked --extra all --group dev
```

Release-readiness tooling:

```bash
uv sync --locked --extra all --group dev --group release
```

Use locked commands:

```bash
uv lock --check
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy src/carnopy
uv run --locked pytest
uv run --locked python scripts/preflight.py
uv pip check --python .venv/bin/python
```

If a required dependency or command is unavailable, preserve the exact failure
and ask before installing or substituting anything.

## Project purpose

Carnopy generates reproducible, backend-derived synthetic thermophysical
datasets for machine-learning, surrogate-model, and engineering workflows.

Carnopy is not:

- a thermodynamic property model;
- experimental data;
- backend-independent ground truth;
- a process simulator;
- a machine-learning training framework.

The core workflow is:

```text
sampling specification
→ backend calls
→ validation and stable diagnostics
→ stable tabular schema
→ CSV/Parquet
→ metadata and report
```

## Milestone 1 contract

Milestone 1 supports:

- Python package and CLI named `carnopy`;
- CoolProp backend only;
- pure fluids only;
- YAML schema version 1;
- `property_table`;
- `saturation_table`;
- `vapor_mass_fraction_table`;
- deterministic sampling;
- CSV and Parquet;
- metadata and report JSON;
- optional Matplotlib visualization for vapor-mass-fraction tables.

Out of scope:

- mixtures;
- ORC generation;
- additional property backends;
- random, Sobol, Latin-hypercube, adaptive, or active-learning sampling;
- ML training or inference;
- GUI, web service, API server, or database;
- ThermoML, OCR, RAG, or literature mining;
- package publication by the agent.

## Public CLI

```text
carnopy --version
carnopy init MODE OUTPUT [--create-parents]
carnopy properties
carnopy fluids
carnopy validate CONFIG.yaml
carnopy generate CONFIG.yaml [--out PATH]
carnopy plot SOURCE ...
```

The documented workflow is:

```text
init → edit → optional validate → generate → inspect → optional plot
```

`generate` validates automatically. Commands remain independently scriptable;
do not add implicit chaining.

`init`:

- supports all three public modes;
- requires `.yaml` or `.yml`;
- never overwrites;
- prompts before creating missing parents;
- fails noninteractively unless `--create-parents` is supplied;
- reads templates packaged with `importlib.resources`.

## Public configuration

Every YAML configuration contains:

```yaml
schema_version: 1
backend: coolprop
mode: property_table
fluids: [...]
grid: ...
properties: [...]
```

Public samplers:

```text
explicit
linspace
stepspace
geomspace
logspace
```

`stepspace` is inclusive and requires a reachable endpoint. Public `arange` is
not supported.

Supported units:

```text
temperature: K, degC
pressure: Pa, kPa, MPa, bar
vapor_mass_fraction: "1"
```

All backend calls and generated numeric columns use SI. Preserve original units
and sampler declarations in metadata.

The row limit is 1,000,000 after sampler materialization, fluid
canonicalization, Cartesian expansion, and saturation endpoint expansion.

## Mode contracts

`property_table` requires temperature and pressure and generates their Cartesian
product for each canonical fluid.

`saturation_table` requires exactly one of temperature or pressure and emits
separate saturated-liquid and saturated-vapor rows.

`vapor_mass_fraction_table` requires vapor mass fraction plus exactly one of
temperature or pressure. Public `vapor_mass_fraction` maps to CoolProp `Q` only
inside the adapter.

## Scientific behavior

Use official CoolProp documentation as the authority:

- https://coolprop.org/coolprop/
- https://coolprop.org/coolprop/HighLevelAPI.html
- https://github.com/CoolProp/CoolProp

Reset every requested canonical fluid to CoolProp `DEF` once after validation
and before row evaluation. Do not change reference state during generation.

Specific enthalpy, entropy, and internal energy are reference-state dependent.
Absolute values are not directly comparable across different reference
conventions.

If actual CoolProp behavior contradicts an approved contract:

1. Stop before implementing a workaround.
2. Preserve fluid, normalized inputs, property, mode, CoolProp version,
   exception type/message, and observed result.
3. Explain the contradiction.
4. Ask the human operator to decide.

Do not silently change input pairs, phase rules, numerical methods, schemas, or
backend behavior.

## Rows and failures

Rows include:

```text
run_id
case_id
mode
fluid
backend
backend_version
phase
backend_phase
valid
failure_layer
failure_code
failure_message
failure_property
backend_error_type
backend_error_message
```

`case_id` is zero-based and assigned after deterministic final ordering.

Milestone 1 uses strict row validity. Any required coordinate, phase, or
requested-property failure invalidates the row. Successful values may remain;
failed values remain null.

Do not infer stable failure categories by parsing backend messages. Preserve raw
backend diagnostics separately.

## Provenance and immutable artifacts

Identity meanings:

- `spec_id`: canonical executable scientific specification;
- `generation_context_id`: artifact-generation context;
- `run_id`: one UUID4 generation attempt;
- artifact hashes: exact emitted bytes.

Generation writes immutable run directories containing:

```text
dataset.csv
dataset.parquet
config.original.yaml
config.normalized.json
metadata.json
report.json
```

Human-facing run-directory names use:

```text
<UTC-second>_<mode-slug>_<eight-character-run-prefix>
```

The name is a locator, not dataset identity. Full `run_id`, `spec_id`,
generation context, and artifact hashes remain in metadata.

Tests use temporary directories. Do not commit generated datasets or figures.

Visualization:

- reads only `vapor_mass_fraction_table`;
- prefers Parquet in run directories;
- verifies recorded source hashes;
- plots only valid values;
- preserves invalid contour cells as gaps;
- writes outside immutable run directories;
- writes an image plus `.plot.json`;
- refuses existing image or sidecar paths;
- finalizes with exclusive same-filesystem hard links;
- is no-overwrite-safe but not fully two-file crash-atomic.

## Packaging and release readiness

Use a `src/` layout and Hatchling:

```toml
[build-system]
requires = ["hatchling>=1.27.0"]
build-backend = "hatchling.build"
```

Matplotlib remains optional through `viz`; `all` must contain every user-facing
optional dependency. PyArrow remains core.

The first intended public version is `0.1.0a1`. Publication uses one verified
wheel and sdist, uploaded byte-identically to TestPyPI and PyPI through
GitHub OIDC Trusted Publishing. The human performs all publication steps.

Never rebuild changed payloads under an uploaded version. Any payload change
requires a new version.

## Code quality

- Prefer direct, explicit implementations.
- Keep CLI functions thin.
- Keep scientific logic out of `cli.py`.
- Avoid heavy imports and side effects at module import time.
- Root and subcommand help must not import CoolProp, NumPy, pandas, PyArrow, or
  Matplotlib.
- Keep module boundaries focused; avoid monolithic files and speculative
  frameworks.
- Use `apply_patch` for edits.
- Use `rg` for text and file searches.
- Use strict mypy for `src/carnopy`.
- Add focused regression tests for every behavior change.
- Do not use brittle golden thermodynamic datasets or pixel-perfect plots.

## Commit-message guidance

The human uses:

```text
<type>(<scope>): <imperative summary>
```

Common types: `feat`, `fix`, `test`, `docs`, `refactor`, `chore`, `ci`,
`build`, `perf`, and `style`.

Common scopes: `dataset`, `schema`, `sampler`, `coolprop`, `cli`,
`validation`, `metadata`, `tests`, `docs`, `ci`, and `packaging`.
