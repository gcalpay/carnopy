# Carnopy

> Alpha software: public interfaces and generated schemas may still change
> before the stable `0.1.0` release.

Carnopy is a CLI-first Python package for generating reproducible,
backend-derived thermophysical datasets for machine-learning, surrogate-model,
and engineering workflows.

Carnopy is not a thermodynamic property model. It orchestrates configured
property backends, validates deterministic sampling, preserves failed states as
diagnostics, and emits stable tabular data with provenance. Generated values are
synthetic backend output, not experimental data or backend-independent ground
truth.

Milestone 1 supports pure fluids through CoolProp and three modes:

- `property_table`: temperature-pressure state tables;
- `saturation_table`: saturated-liquid and saturated-vapor endpoint rows;
- `vapor_mass_fraction_table`: two-phase states over vapor mass fraction.

## Install the alpha

After `0.1.0a1` is published:

```bash
python -m pip install "carnopy==0.1.0a1"
python -m pip install "carnopy[all]==0.1.0a1"
```

For an isolated CLI:

```bash
uv tool install "carnopy==0.1.0a1"
uv tool install "carnopy[all]==0.1.0a1"
```

The base package supports dataset generation. The `all` extra additionally
installs optional scientific plotting.

## CLI workflow

```text
init → edit → optional validate → generate → inspect → optional plot
```

Create a commented starter configuration:

```bash
carnopy init property_table my-dataset.yaml
```

Available modes:

```text
property_table
saturation_table
vapor_mass_fraction_table
```

Discover fluids and semantic properties:

```bash
carnopy fluids
carnopy properties
```

Edit the YAML, optionally validate it, then generate an immutable run:

```bash
carnopy validate my-dataset.yaml
carnopy generate my-dataset.yaml
```

`generate` performs validation automatically. The separate `validate` command
is useful for scripts and early feedback but is not a required extra step.

To choose a different output root:

```bash
carnopy generate \
  configs/cyclopentane_vapor_fraction_pressure.yaml \
  --out outputs/manual-test
```

The generated run is created directly under that root. Copy the exact path
printed after `Output directory:`; do not prepend `outputs/manual-test` again:

```bash
# Example only; replace this with the exact path printed by your run.
RUN_DIR="outputs/manual-test/20260621T172006Z_vapor_fraction_c8e28e9f"
```

Run names use the UTC creation time, a short mode label, and the first eight
hexadecimal characters of the unique `run_id`. Full identities and hashes
remain in `metadata.json`.

Inspect:

```text
outputs/<run>/
├── dataset.csv
├── dataset.parquet
├── config.original.yaml
├── config.normalized.json
├── metadata.json
└── report.json
```

Export sampled property curves from a vapor-mass-fraction run:

```bash
carnopy plot "$RUN_DIR" \
  --kind property-curves \
  --property mass_density \
  --show
```

For `property_table`, choose the x-axis explicitly:

```bash
carnopy plot outputs/<property-run> \
  --kind property-curves \
  --property mass_density \
  --x temperature
```

Create a non-interpolated sampled property map:

```bash
carnopy plot "$RUN_DIR" \
  --kind property-heatmap \
  --property mass_density
```

The image and `.plot.json` provenance sidecar are written under `figures/` by
default. Plotting never calls CoolProp, interpolates states, or modifies the
source run.

Run:

```bash
carnopy --help
carnopy generate --help
carnopy plot --help
```

for complete command-specific guidance.

## Python API

```python
from carnopy import generate_dataset, load_config, validate_config

validation = validate_config("my-dataset.yaml")
result = generate_dataset("my-dataset.yaml")
```

Optional visualization:

```python
from carnopy.visualization import plot_property_heatmap

result = plot_property_heatmap(
    "outputs/manual-test/20260621T172006Z_vapor_fraction_c8e28e9f",
    property_name="mass_density",
)
```

The returned figure has already been exported. Modifying it does not update the
image or provenance sidecar.

## Scientific limitations

- Backend calls and generated numeric columns use SI.
- Original declared units and sampling definitions remain in metadata.
- Specific enthalpy, entropy, and internal energy depend on reference state.
- Carnopy initializes requested fluids with CoolProp `DEF` and records it.
- Milestone 1 uses strict row validity.
- Mode-limited properties such as `surface_tension` can invalidate otherwise
  useful rows when requested outside their supported region.
- Mixtures, additional backends, ORC generation, and ML training are deferred.

See:

- [Configuration](docs/configuration.md)
- [Architecture](docs/architecture.md)
- [Data and provenance](docs/data-policy.md)
- [Visualization](docs/visualization.md)
- [Release process](docs/releasing.md)
- [Contributing](CONTRIBUTING.md)

Official CoolProp references:

- https://coolprop.org/coolprop/
- https://github.com/CoolProp/CoolProp
