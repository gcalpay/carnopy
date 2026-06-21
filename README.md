# Carnopy

Carnopy is a CLI-first Python package for generating reproducible
thermophysical datasets from configured property backends for machine-learning,
surrogate-model, and engineering workflows.

Carnopy is not a thermodynamic property model. It orchestrates a property
backend, validates a deterministic sampling specification, preserves failed
states as diagnostics, and emits stable tabular data with provenance metadata.
Generated values are backend-derived synthetic data, not experimental data or
backend-independent ground truth.

Milestone 1 supports pure fluids with the CoolProp backend and three modes:

- `property_table`: arbitrary temperature-pressure states with inferred phase.
- `saturation_table`: saturated-liquid and saturated-vapor endpoint rows.
- `vapor_mass_fraction_table`: two-phase states at a specified vapor mass fraction.

## Development setup

Carnopy development uses standalone uv and a project-local `.venv`. After the
human operator has installed uv and generated `uv.lock`, synchronize the normal
development environment with:

```bash
uv sync --locked --extra all --group dev
```

Run commands without activating the environment:

```bash
uv run --locked carnopy --help
uv run --locked pytest
```

## Usage

Validate without evaluating thermodynamic rows:

```bash
carnopy validate configs/property_table_example.yaml
```

Generate an immutable run:

```bash
carnopy generate configs/property_table_example.yaml
```

List pure fluids available from the current backend:

```bash
carnopy fluids
```

Visualization is an optional user-facing feature. The `all` extra currently
includes every optional feature, including visualization. For repository
development it is installed by the synchronization command above.

```bash
uv sync --locked --extra all --group dev
```

Export a scientific plot from a vapor-mass-fraction run:

```bash
carnopy plot outputs/<run-directory> \
  --property mass_density \
  --kind curves \
  --show
```

The image and a traceable `.plot.json` sidecar are written under `figures/` by
default. Plotting does not modify the immutable source run.

Each run contains:

```text
dataset.csv
dataset.parquet
config.original.yaml
config.normalized.json
metadata.json
report.json
```

Input YAML may use supported engineering units. Backend calls and generated
numeric columns use SI. Original units and sampler definitions remain in
metadata.

Specific enthalpy, entropy, and internal energy depend on the selected reference
state. Carnopy resets requested fluids to CoolProp `DEF` before generation and
records that convention. Absolute values should not be compared across different
reference conventions.

Mode-limited properties such as `surface_tension` should not be requested over
broad `property_table` grids unless invalid rows are expected. Milestone 1 uses
strict row validity: failure of any requested property invalidates the complete
row, while successful values are retained for diagnosis.

See [configuration](docs/configuration.md), [data policy](docs/data-policy.md),
[visualization](docs/visualization.md), and
[architecture](docs/architecture.md) for the stable contracts.

Official CoolProp references:

- https://coolprop.org/coolprop/
- https://github.com/CoolProp/CoolProp

Not included in Milestone 1: mixtures, ORC generation, random/design-of-
experiments sampling, ML training, services, databases, or additional backends.
