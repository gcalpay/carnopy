# Carnopy

[![PyPI](https://img.shields.io/pypi/v/carnopy.svg)](https://pypi.org/project/carnopy/)
[![Python](https://img.shields.io/pypi/pyversions/carnopy.svg)](https://pypi.org/project/carnopy/)
[![Verify](https://github.com/gcalpay/carnopy/actions/workflows/ci.yml/badge.svg)](https://github.com/gcalpay/carnopy/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Reproducible thermophysical datasets from scientific backends with
visualization, provenance, and leakage-aware preparation for physics-informed
machine-learning and engineering workflows.

Carnopy turns an explicit YAML sampling specification into immutable CSV and
Parquet datasets, diagnostics, metadata, and optional figures. It is available
as an automation-friendly CLI, a Python library, and an optional QML desktop
workbench.

> Carnopy is alpha software. Public interfaces and generated schemas may change
> before the stable `0.1.0` release.

## Why Carnopy?

- **Reproducible inputs:** explicit fluids, backend model, samplers, units,
  properties, and output formats.
- **Traceable outputs:** normalized configuration, software and backend
  versions, reference-state context, artifact hashes, and stable identities.
- **Honest failures:** invalid thermodynamic states remain visible as row-level
  diagnostics instead of silently disappearing.
- **One scientific core:** CLI, Python, and desktop workflows use the same
  validation, generation, inspection, and rendering contracts.
- **ML-ready preparation:** deterministic leakage-aware partitions,
  transformations, diagnostics, and optional array exports without becoming a
  model-training framework.

Carnopy currently supports pure fluids through CoolProp, the HEOS, PR, and SRK
models, and three dataset modes:

| Mode | Generated states |
| --- | --- |
| `property_table` | Temperature-pressure state tables |
| `saturation_table` | Saturated-liquid and saturated-vapor endpoints |
| `vapor_mass_fraction_table` | Two-phase states over vapor mass fraction |

Carnopy is not a thermodynamic property model, experimental data,
backend-independent ground truth, or a process simulator. Generated values are
synthetic output from the selected backend and model.

## Installation

The commands below are the two primary `0.1.0a4` installation paths. They
become usable when the PyPI badge above reports `0.1.0a4`. Until then, the
latest published alpha is `0.1.0a3`, while the modern QML frontend is available
from the current `0.1.0a4.dev0` source checkout.

### Isolated desktop application

Install the QML desktop workbench in its own uv-managed environment:

```bash
uv tool install "carnopy[app]==0.1.0a4"
carnopy-gui
```

### CLI and Python library

Install the base package into your current Python environment:

```bash
python -m pip install "carnopy==0.1.0a4"
carnopy --help
```

Optional capabilities use one extra on the same requirement:

| Extra | Adds |
| --- | --- |
| `app` | QML desktop workbench and plotting runtime |
| `viz` | Matplotlib plotting without the desktop UI |
| `ml` | SafeTensors preparation exports |
| `analysis` | Optional scikit-learn preparation diagnostics |
| `all` | Exact union of all public extras |

For example, use `carnopy[viz]==0.1.0a4` instead of `carnopy==0.1.0a4` when a
CLI/library environment also needs plotting. PyArrow remains a core dependency
because Parquet is a first-class output format.

`carnopy-gui` is the canonical desktop command. `carnopy-app` launches the same
QML application as a compatibility alias for the `0.1.0a4` release.

### Try the current source

```bash
git clone https://github.com/gcalpay/carnopy.git
cd carnopy
uv sync --locked --extra app --group dev
uv run --locked carnopy-gui
```

The desktop extra requires PySide6 Essentials 6.11.1 or later within the 6.11 release line.
The private native bridge remains qualified against exactly Qt 6.11.1. Qt is an
optional third-party dependency with its own licensing terms; Carnopy remains
MIT licensed and does not ship a standalone Qt installer.

## Quick start

Create, inspect, and visualize a property-table dataset:

```bash
carnopy init property_table my-dataset.yaml
# Review or edit the generated YAML.
carnopy generate my-dataset.yaml
carnopy inspect outputs/<run>
carnopy plot outputs/<run> \
  --kind property-curves \
  --property mass_density \
  --x temperature
```

The normal command-line workflow is:

```text
init → edit → optional validate → generate/sweep → inspect → optional plot → optional prepare
```

`generate` always performs authoritative validation. The separate `validate`
command is useful for scripts and early feedback, but it does not evaluate
thermodynamic rows or authorize a later generation.

Use command-specific help for the complete current interface:

```bash
carnopy --help
carnopy init --help
carnopy generate --help
carnopy inspect --help
carnopy plot --help
```

## Desktop workflow

Start the workbench with:

```bash
carnopy-gui
```

Its workflow is:

```text
Workspace → Dataset → YAML Preview → Run → Inspect → Visualization
          → Activity and Recovery
```

- **Dataset** edits all three dataset modes and projects row counts without
  importing the scientific stack into the GUI process.
- **YAML Preview** shows the deterministic complete document. Save and Save As
  validate those exact bytes in a worker before writing.
- **Run** validates and generates an exact clean saved snapshot.
- **Inspect** presents provenance, diagnostics, logical arrays, and bounded
  order-preserving table pages.
- **Visualization** verifies recorded configured-plot evidence and supports
  explicit session rendering from inspected columns.
- **Activity and Recovery** projects private request records and removes only
  explicitly selected, rescanned staging artifacts.

Scientific generation, inspection, and Matplotlib rendering run in short-lived
workers. The QML process does not import CoolProp, NumPy, pandas, PyArrow, or
Matplotlib. PNG and SVG use hash-bound in-app previews; PDF opens only after an
explicit revalidation and user action.

To preselect a workspace:

```bash
carnopy-gui --workspace /path/to/workspace
```

Each workspace keeps YAML configurations in `configs/`, immutable generated
runs in `outputs/`, and rendered plots in `figures/`. Opening or importing a
configuration starts in that workspace's `configs/` folder.

Qt normally detects its platform integration. On WSLg, Carnopy's `auto` mode
prefers XCB when both display transports are available because native Wayland
dialogs can detach after selection. Override it only when necessary:

```bash
carnopy-gui --qt-platform xcb --workspace /path/to/workspace
```

## Configuration at a glance

Carnopy dataset configurations use YAML schema version 2:

```yaml
schema_version: 2
document_type: dataset
backend:
  name: coolprop
  model: heos
mode: property_table
fluids: [Propane, Isobutane]

grid:
  temperature:
    kind: linspace
    start: -50
    stop: 50
    num: 101
    unit: degC
  pressure:
    kind: linspace
    start: 101325
    stop: 506625
    num: 41
    unit: Pa

properties:
  - specific_enthalpy
  - mass_density

outputs:
  dataset_formats: [csv, parquet]
```

Create a concise starter or the exhaustive commented reference:

```bash
carnopy init property_table my-dataset.yaml
carnopy init property_table full-reference.yaml --full
```

Supported public samplers are `explicit`, `linspace`, `stepspace`,
`geomspace`, and `logspace`. Supported input units are:

| Coordinate | Units |
| --- | --- |
| Temperature | `K`, `degC` |
| Pressure | `Pa`, `hPa`, `kPa`, `MPa`, `bar`, `atm` |
| Vapor mass fraction | `1` |

All backend calls and generated numeric columns use SI. Carnopy preserves the
declared units and sampler definitions in provenance while normalizing the
executable scientific specification deterministically.

### Backend models

| Model | Meaning | Current limitation |
| --- | --- | --- |
| `heos` | Helmholtz-energy equations and associated models | Full current property registry, subject to fluid/state support |
| `pr` | Peng-Robinson cubic equation of state | No transport properties, surface tension, or usable triple point |
| `srk` | Soave-Redlich-Kwong cubic equation of state | No transport properties, surface tension, or usable triple point |

HEOS is the starter default, not experimental truth. PR and SRK are alternative
model assumptions, not accuracy rankings. Model selection changes scientific
identity and is recorded in rows, metadata, and reports.

## Outputs and provenance

Each immutable dataset run contains selected table files plus mandatory
provenance:

```text
outputs/<run>/
├── dataset.csv              # when requested
├── dataset.parquet          # when requested
├── config.original.yaml
├── config.normalized.json
├── config.reference.yaml
├── metadata.json
└── report.json
```

Runs are staged and then atomically renamed. Existing final or staging paths
are never overwritten. Important identities have distinct meanings:

- `spec_id`: canonical executable scientific specification;
- `generation_context_id`: specification plus software and artifact context;
- `output_request_id`: canonical dataset serialization request;
- `run_id`: one execution attempt;
- artifact hashes: exact emitted bytes;
- `visualization_request_id`: normalized visualization request.

Metadata records software and backend versions, selected model, CoolProp `DEF`
reference-state policy, canonical fluids and properties, sampling, failures,
units, constants, and artifact hashes. Failed states remain rows with stable
failure fields and preserved backend diagnostics.

## Visualization

Visualization reads emitted columns only. It never calls a thermodynamic
backend, smooths, interpolates, extrapolates, or invents states.

Supported plot kinds are property curves, sampled property heatmaps, generic
X-Y plots, and emitted-state p-v and T-s diagrams. For example:

```bash
carnopy plot outputs/<run> \
  --kind property-curves \
  --property specific_enthalpy \
  --x temperature \
  --series pressure=1bar \
  --series pressure=3bar \
  --display-unit temperature=degC \
  --display-unit specific_enthalpy=kJ/kg
```

Exact filters and series values never select a nearest neighbor. The p-v plot
derives only `specific_volume = 1 / mass_density`; the T-s plot uses emitted
temperature and specific entropy. Neither constructs a cycle, process path,
phase envelope, saturation dome, or missing branch.

Configured visualization belongs in an optional top-level `visualization:`
section and runs only after the immutable dataset is finalized. Images are
written outside the dataset run with a `.plot.json` provenance sidecar and a
`visualization-report.json`. Supported formats are PNG, SVG, and PDF.

## Model sweeps and ML preparation

Model sweeps generate ordinary immutable child runs and compare their emitted
values without extra thermodynamic evaluation during comparison:

```bash
carnopy init model_sweep sweep.yaml
carnopy sweep sweep.yaml
```

Preparation reads an existing immutable run or sweep bundle and never calls a
thermodynamic backend:

```bash
carnopy init preparation preparation.yaml
carnopy prepare outputs/<run> --config preparation.yaml --out prepared
```

Parquet remains the canonical prepared table. Optional NumPy and SafeTensors
files are derived ML-consumption exports. Leakage-aware scenarios keep an exact
thermodynamic-state hash in one partition, and transformations fit on training
data only. Optional scikit-learn baselines are disposable diagnostics; Carnopy
does not train, tune, register, or deploy production models.

Implemented behavior and reviewed research directions are separated in the
[ML preparation roadmap](https://github.com/gcalpay/carnopy/blob/main/ML_PREPARATION_ROADMAP.md).

## Python API

The public API intentionally remains narrow:

```python
from carnopy import generate_dataset, load_config, validate_config

loaded = load_config("my-dataset.yaml")
validation = validate_config("my-dataset.yaml")
result = generate_dataset(
    "my-dataset.yaml",
    output_root="outputs",
    figures_root="figures",
)
```

Public helpers also cover model sweeps, preparation, and explicit
visualization. CLI handlers and desktop controllers call the same core logic
rather than maintaining separate scientific implementations.

## Scientific limitations

- CoolProp is the only current backend; pure fluids only.
- Supported CoolProp models are HEOS, Peng-Robinson, and
  Soave-Redlich-Kwong.
- Generated data is backend output, not experimental evidence.
- Specific enthalpy, entropy, and internal energy depend on reference state.
- Carnopy resets every requested fluid to CoolProp `DEF` before generation and
  records that policy.
- Absolute reference-dependent values are not directly comparable across
  incompatible model/reference contexts.
- PR/SRK transport properties, surface tension, and triple-point temperature
  are rejected because the cubic backends do not provide the required
  capability.
- Mixtures, additional backends, ORC generation, ML training, web services,
  databases, native 3D, and standalone desktop installers are deferred.

See the official [CoolProp documentation](https://coolprop.org/coolprop/) and
[high-level API reference](https://coolprop.org/coolprop/HighLevelAPI.html) for
backend behavior.

## Future Scope

Carnopy's current contracts remain intentionally narrower than its longer-term
direction. Future work may add:

- additional thermophysical property libraries and databases;
- simulation-backend and thermodynamic-cycle-calculator adapters;
- experimental and operational data with explicit source, uncertainty,
  licensing, and validation status;
- user-supplied datasets through validated schema and provenance imports; and
- preparation outputs for training physics-informed machine-learning models,
  while model training remains outside Carnopy.

These are roadmap directions, not capabilities promised by the current alpha.
Each source type requires an explicit scientific, provenance, and validation
contract before implementation.

## Development and contribution

Carnopy uses a `src/` layout, Hatchling, standalone uv, Ruff, strict mypy, and
pytest. `pyproject.toml` and `uv.lock` are authoritative.

```bash
uv sync --locked --extra all --group dev
uv lock --check
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy src/carnopy
uv run --locked pytest
```

Read [CONTRIBUTING.md](https://github.com/gcalpay/carnopy/blob/main/.github/CONTRIBUTING.md)
before proposing a public or scientific contract change. Use
[GitHub Issues](https://github.com/gcalpay/carnopy/issues) for reproducible bugs,
scientific discrepancies, and focused feature requests. Report vulnerabilities
privately through the [security policy](https://github.com/gcalpay/carnopy/security/policy).

The implemented desktop ownership and worker boundary are documented in
[DESKTOP_ARCHITECTURE.md](https://github.com/gcalpay/carnopy/blob/main/DESKTOP_ARCHITECTURE.md).
The generated Graphify artifacts are navigation aids only and must pass the
repository freshness gate before use.

## Release status

The latest published alpha is `0.1.0a3`. The current source reports
`0.1.0a4.dev0` and contains the QML parity work planned for `0.1.0a4`. Stage 3
remains under native acceptance until a representative, non-personal-path
screenshot and the final source/distribution gates are accepted. The version
bump, tag, PyPI publication, GitHub prerelease, and citation metadata belong to
the separate human-controlled `0.1.0a4` release process.

## License

Carnopy is distributed under the [MIT License](LICENSE).
