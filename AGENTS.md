# AGENTS.md

## Approved Milestone 1 contract

The human-approved Milestone 1 implementation contract supersedes conflicting
older examples later in this file. In particular:

- public modes are `property_table`, `saturation_table`, and
  `vapor_mass_fraction_table`;
- the CLI is `carnopy generate CONFIG.yaml`, `carnopy validate CONFIG.yaml`,
  and `carnopy fluids`;
- public sampling kinds are `explicit`, `linspace`, inclusive `stepspace`,
  `geomspace`, and `logspace`;
- YAML uses semantic variable/property names and explicit units;
- generated numeric columns use SI unit suffixes;
- saturation tables emit separate saturated-liquid and saturated-vapor rows;
- CoolProp `Q` remains an adapter detail exposed publicly as
  `vapor_mass_fraction`;
- row failures use the approved layered backend-neutral schema;
- CoolProp reference state is reset once per requested fluid to `DEF` before
  generation.
- optional Matplotlib visualization may read finalized
  `vapor_mass_fraction_table` runs, but must export figures outside immutable
  run directories and include plot-provenance sidecars.

If actual CoolProp behavior contradicts an approved public contract, stop,
preserve diagnostics, and ask the human operator before implementing a
workaround or changing thermodynamic behavior.

## Scope of this instruction file

This is the root agent instruction file for the repository.

It applies to the entire repository tree unless a more specific nested `AGENTS.md` is added later in a subdirectory.

Nested instruction files may be added later for specialized subtrees, for example `src/carnopy/backends/AGENTS.md` or `tests/AGENTS.md`, but do not create nested instruction files in the initial scaffold unless the human user explicitly requests them.

---

## Repository identity and hard boundary

You are working in this exact local repository root:

```text
/home/cfd/carnopy/
```

The Git metadata directory is located at:

```text
/home/cfd/carnopy/.git/
```

Treat `/home/cfd/carnopy/` as the repository root.

Work only inside `/home/cfd/carnopy/` and its subdirectories.

Do not modify, inspect, create, delete, or move files outside `/home/cfd/carnopy/` unless the human user explicitly asks for a specific path outside the repository.

Do not work in parent folders such as:

```text
/home/cfd/
/home/
```

Do not use the old deleted local path:

```text
/home/cfd/coolprop/
```

That path is obsolete and must not appear in generated project files.

The private GitHub repository is:

```text
gcalpay/carnopy
```

The current GitHub description is:

```text
Thermodynamic synthetic dataset generator.
```

The preferred long-form positioning is:

```text
Reproducible ML-ready thermodynamic fluid-property datasets from configurable property backends.
```

Do not change the GitHub repository description or remote settings. The human user handles GitHub settings manually.

---

## Canonical project names

Use these names consistently:

```text
Project name: Carnopy
Repository name: carnopy
PyPI distribution name: carnopy
Python import package: carnopy
CLI command name: carnopy
```

The Python source package must be:

```text
src/carnopy/
```

The package must be imported as:

```python
import carnopy
```

The command-line interface must be called as:

```bash
carnopy
```

Do not use `coolprop`, `coolprop_`, or `coolprop-` as the repository name, distribution name, import package name, module prefix, CLI command, or project identity.

CoolProp is a backend dependency and reference project, not this repository's identity.

---

## Project purpose

Carnopy is a CLI-first Python package for generating reproducible synthetic thermodynamic and thermophysical fluid-property datasets for machine-learning and surrogate-model workflows.

Carnopy is not a thermodynamic property model.

Carnopy is not a replacement for CoolProp, Thermopack, FeOs, `thermo`, REFPROP, Cantera, pycalphad, DWSIM, TESPy, IDAES, OpenFF Evaluator, or ThermoML.

Carnopy orchestrates existing property backends to produce reproducible, validated, backend-derived datasets.

The core workflow is:

```text
sampling specification
-> backend property calls
-> thermodynamic validity checks
-> stable tabular schema
-> metadata and report
-> reproducible CSV/Parquet export
```

The differentiator is dataset orchestration, not property calculation.

A simple script that sweeps temperature and pressure with `PropsSI` and writes CSV is not sufficient.

Carnopy must add the reproducibility, validation, schema, metadata, reporting, and surrogate-dataset structure that direct backend calls do not provide.

---

## Scientific positioning

Generated datasets are backend-derived synthetic data.

They are not experimental data.

They are not independent reference data.

They are not backend-independent ground truth.

They are only as valid as:

- the selected property backend
- the selected fluid model
- the backend version
- the selected input domain
- the sampling configuration
- the state validity checks
- the documented assumptions

Use precise language:

Prefer:

```text
backend-generated synthetic thermophysical data
CoolProp-derived property table
validated generated state table
surrogate-model training dataset candidate
```

Avoid:

```text
ground truth
experimental data
reference database
truth table
validated against reality
```

Unless actual experimental validation is implemented later, do not imply experimental accuracy beyond the backend's own scope.

---

## External references

Use the official CoolProp documentation as the primary reference for CoolProp behavior, supported input pairs, output keys, phase handling, saturation states, reference states, and high-level API usage:

```text
https://coolprop.org/coolprop/
```

Use the CoolProp high-level API documentation for `PropsSI`, `PhaseSI`, saturation handling, phase imposition, fluid information, and partial-derivative behavior:

```text
https://coolprop.org/coolprop/HighLevelAPI.html
```

Use the official CoolProp GitHub repository as the source-code and upstream project reference:

```text
https://github.com/CoolProp/CoolProp
```

CoolProp must be treated as the first property backend, not as Carnopy's project identity.

Other projects are useful as future context only:

- Thermopack: future backend candidate for EOS and mixture work
- FeOs: future backend candidate for EOS, SAFT, and derivative-rich workflows
- teqp: future backend candidate for derivative-rich EOS work
- `thermo` / `chemicals`: future backend/reference candidate for correlations and chemical-property utilities
- DESPASITO: future SAFT-related reference
- Cantera: future reacting-system reference, not milestone 1
- pycalphad: future materials/CALPHAD reference, not milestone 1
- DWSIM / DTL: future process-simulator comparison, not milestone 1
- TESPy: future cycle/system data generation reference, not milestone 1
- OpenFF Evaluator: conceptual reference for physical-property dataset workflows, not milestone 1
- ThermoML: experimental-data standard/reference source, not milestone 1

Do not implement integrations for these future references unless the human user explicitly asks for a later milestone.

---

## Human-operator rule

The human user owns:

- Git operations
- GitHub repository settings
- dependency installation
- environment changes
- package publishing
- PyPI token handling
- release/version decisions
- project-level architectural decisions

When uncertain, stop and ask.

Prefer small, reversible changes.

Do not silently make broad architectural decisions.

Do not implement speculative features before the current milestone works.

---

## Git rule

Do not run Git commands.

The human user handles all Git operations manually, including:

```text
git status
git add
git commit
git branch
git remote
git push
git pull
git diff
git log
git init
```

Do not stage files.

Do not commit files.

Do not create branches.

Do not add or modify remotes.

Do not push.

Do not pull.

Do not inspect repository state with Git commands.

If repository state needs to be inspected, use non-Git filesystem commands only.

Allowed non-Git inspection commands include:

```bash
pwd
ls -la
find . -maxdepth 3 -type f | sort
grep -R "pattern" .
rg "pattern" .
```

Before editing files, verify that the current working directory is:

```text
/home/cfd/carnopy
```

If unexpected files already exist, summarize them before editing.

---

## Filesystem safety rule

Do not run destructive filesystem commands without explicit human approval.

Commands requiring explicit approval include, but are not limited to:

```bash
rm
rm -r
rm -rf
mv existing_path other_path
find . -delete
truncate
```

Creating new directories and files inside `/home/cfd/carnopy/` is allowed when implementing requested scaffold or features.

Overwriting an existing file is allowed only when it is part of the requested edit and the file path is clearly inside `/home/cfd/carnopy/`.

Do not modify files outside the repository root.

---

## Python environment rule

Use only the existing conda environment named:

```text
qsink
```

Use `qsink` as the development interpreter.

The project must not depend on the environment name `qsink`; it is only a local development instruction.

Do not create another virtual environment or conda environment.

Do not install, upgrade, remove, or pin packages without explicit human approval.

Before assuming a dependency is missing, first check whether it is already available in `qsink`.

Allowed inspection commands include:

```bash
which python
python --version
python -c "import CoolProp, numpy, pandas; print('ok')"
python -c "import typer, pydantic, yaml, pyarrow; print('ok')"
```

The following commands require explicit human approval before execution:

```bash
python -m pip install ...
python -m pip install -e ...
conda install ...
conda update ...
conda remove ...
```

If a dependency is missing, report the exact import or command failure and ask the human user to approve installation.

Do not create a second large Python environment if `qsink` already provides the needed packages.

---

## Package publishing and PyPI rule

Do not publish packages.

Do not run:

```bash
python -m build
twine upload dist/*
python -m twine upload dist/*
```

Do not create, request, store, print, or modify PyPI tokens.

Do not configure PyPI Trusted Publishing.

Do not upload to TestPyPI or PyPI unless the human user explicitly asks for a release/publishing task.

The package name intended for PyPI is:

```text
carnopy
```

The package should be a legitimate minimal package, not an empty placeholder.

A first release may later use:

```text
Project:        Carnopy
PyPI name:      carnopy
Distribution:  carnopy
Import package: carnopy
CLI command:   carnopy
Repo:          gcalpay/carnopy
```

PyPI names are normalized; avoid hyphen/underscore/case variants.

Keep the distribution name, import package, and CLI command aligned as `carnopy`.

Do not create a name-squatting package with no functionality.

For the initial scaffold, implement a real importable package and a real CLI entry point, even if minimal.

---

## Python packaging policy

Use a modern `pyproject.toml`-based package.

Use a `src/` layout.

The initial layout should include:

```text
.
├── AGENTS.md
├── README.md
├── LICENSE
├── .gitignore
├── pyproject.toml
├── configs/
├── src/
│   └── carnopy/
├── tests/
└── outputs/
    └── .gitkeep
```

Use Hatchling unless there is a clear technical reason not to.

A minimal build-system section is preferred:

```toml
[build-system]
requires = ["hatchling>=1.25"]
build-backend = "hatchling.build"
```

Use:

```toml
[project]
name = "carnopy"
```

Use a console script entry point:

```toml
[project.scripts]
carnopy = "carnopy.__main__:main"
```

The package should support:

```bash
python -m carnopy
carnopy --help
```

Target Python compatibility:

```toml
requires-python = ">=3.10"
```

The development interpreter is still the local `qsink` environment.

---

## Python project-structure policy

Use clear module boundaries.

Avoid circular imports.

Avoid hidden global state.

Avoid heavy side effects at import time.

Avoid giant scripts.

Avoid putting core thermodynamic logic directly in CLI functions.

Avoid putting unrelated concerns into `__init__.py`.

Avoid `from module import *`.

Prefer small, explicit modules with tested functions.

The CLI should parse user input, call package functions, and report results.

The package functions should implement configuration parsing, sampling, backend calls, validation, writing, metadata, and reporting.

---

## Runtime and development dependencies

Use Python 3.10 or newer.

Runtime dependencies for milestone 1:

```text
CoolProp
numpy
pandas
pyarrow
pydantic
typer
pyyaml
```

Development dependencies for milestone 1:

```text
pytest
ruff
mypy
```

Do not add `rich` unless the human user approves it or it is strictly required by the chosen Typer setup in the existing environment.

Do not add speculative dependencies.

Do not add machine-learning libraries in milestone 1.

Do not add SciPy solely for Sobol or Latin-hypercube sampling in milestone 1 unless the human user explicitly approves sampling extensions.

Do not add DWSIM, TESPy, IDAES, REFPROP, Thermopack, FeOs, `thermo`, Cantera, pycalphad, OpenFF Evaluator, or ThermoML dependencies in milestone 1.

---

## Current milestone: milestone 1 only

The first implementation pass must stay inside milestone 1.

Milestone 1 implements a CoolProp-first dataset generator, not a general thermodynamics ecosystem.

Implement:

1. Pure-fluid property tables
2. Saturation tables
3. Vapor-quality tables
4. YAML-driven configuration
5. Configuration validation
6. Deterministic sampling grids
7. Bulk-safe backend calls
8. Stable exported schemas
9. CSV export
10. Parquet export
11. Metadata JSON export
12. Report JSON export
13. Small, fast tests
14. A CLI based on Typer

Use CoolProp as the only thermophysical backend in milestone 1.

Do not implement ORC cycle generation in milestone 1.

Do not implement binary mixtures in milestone 1.

Do not implement random, Latin-hypercube, Sobol, adaptive, active-learning, or phase-aware sampling in milestone 1 unless the human user explicitly asks.

Do not implement train/validation/test splits in milestone 1 unless the core generator already works and the human user explicitly asks.

Do not implement normalization or standardization outputs in milestone 1 unless explicitly requested.

Do not implement machine-learning training or inference in milestone 1.

Do not implement a GUI, web app, desktop app, API server, or database in milestone 1.

The first implementation pass must stop after:

- package scaffold
- config models
- deterministic grid sampling
- CoolProp backend wrapper
- property table generator
- saturation table generator
- quality table generator
- writers
- metadata generation
- report generation
- CLI commands
- small tests

---

## Future roadmap: do not implement initially

Future milestone ideas may include:

### Sampling upgrades

- explicit value lists
- logarithmic pressure spacing
- seeded random sampling
- Latin hypercube sampling
- Sobol sampling
- stratified sampling
- phase-aware sampling
- active-learning hooks

### ML-ready dataset additions

- optional train/validation/test split metadata
- optional split column
- normalization statistics
- feature/target schema descriptors
- train-time leakage checks
- duplicate-state checks
- out-of-domain markers

### ORC-state dataset mode

A future ORC-state dataset mode may generate thermodynamically constrained state tables for ORC surrogate-model training.

The likely downstream ORC surrogate context includes:

- waste-heat source temperatures roughly in the low- and medium-temperature range, often about 60-120 °C
- source/sink temperature and mass-flow inputs
- sink temperature constraints such as water or seawater cooling
- pinch, superheat, subcooling, pressure, and vapor-quality constraints
- pure working-fluid candidates first
- later binary mixtures and mixture-composition sweeps
- hydrocarbons such as propane, isobutane, n-butane, isopentane, n-pentane, and cyclopentane
- avoidance of fluorinated working fluids where regulatory constraints make them undesirable
- subcritical ORC first
- condenser pressure preferably not in deep vacuum
- role-specific state constraints such as pump-inlet liquid and turbine-inlet vapor

Do not implement ORC mode in milestone 1.

When implemented later, ORC mode should be a dataset generator, not a full process simulator.

Future ORC state constraints may include:

```text
pump inlet: liquid or subcooled liquid
pump outlet: compressed liquid
evaporator outlet: saturated vapor or superheated vapor
turbine inlet: dry vapor or superheated vapor
turbine outlet: acceptable vapor quality above configured minimum
condenser outlet: saturated liquid or subcooled liquid
```

### Backend expansion

Future backend candidates may include:

- ThermopackBackend
- FeOsBackend
- TeqpBackend
- ThermoBackend
- DWSIM comparison backend
- TESPy cycle-data integration

Do not implement these in milestone 1.

### Experimental/literature data workflows

Future work may include comparison to experimental data, ThermoML ingestion, or literature-mined datasets.

Do not implement:

- OCR
- RAG
- LLM extraction
- PDF parsing
- literature mining
- ThermoML ingestion
- experimental database curation

in milestone 1.

Thermodynamic literature extraction is a separate problem involving source reliability, symbol encoding, table extraction, unit inconsistencies, evidence tracing, and validation. It does not belong in the first Carnopy implementation.

---

## Non-triviality requirement

Carnopy must not devolve into:

```text
for T in range:
    for p in range:
        PropsSI(...)
write CSV
```

That is a simple CoolProp wrapper and is not enough.

Carnopy should provide at least:

- explicit sampling specification
- deterministic generated input states
- backend abstraction boundary
- safe property evaluation
- phase and domain validation
- stable output schema
- explicit units
- valid/invalid row markers
- stable failure reasons
- metadata for reproducibility
- report for dataset quality inspection
- CSV and Parquet exports
- copied config file in output directory
- small tests proving the pipeline works

This is the core value proposition.

---

## Backend abstraction policy

Implement only CoolProp in milestone 1.

However, do not hardwire CoolProp assumptions into every module.

Use a thin internal backend boundary so future backends are not blocked.

The first backend module should be:

```text
src/carnopy/backends/coolprop_backend.py
```

A minimal backend boundary may expose:

```text
backend name
backend version
list fluids
get fluid metadata / limits where practical
property call
phase call
safe property call
safe phase call
```

Do not create an over-engineered plugin architecture in milestone 1.

Do not hide CoolProp behavior behind excessive abstraction.

Backend-specific failure messages may be normalized into Carnopy's stable failure reasons, but the original backend error text may be stored in an optional diagnostic field or report.

---

## Suggested initial structure

Use this as the initial structure unless there is a clear technical reason to deviate:

```text
.
├── AGENTS.md
├── README.md
├── LICENSE
├── .gitignore
├── pyproject.toml
├── configs/
│   ├── property_table_example.yaml
│   ├── saturation_table_example.yaml
│   └── quality_table_example.yaml
├── src/
│   └── carnopy/
│       ├── __init__.py
│       ├── __main__.py
│       ├── cli.py
│       ├── backends/
│       │   ├── __init__.py
│       │   └── coolprop_backend.py
│       ├── config/
│       │   ├── __init__.py
│       │   └── models.py
│       ├── properties/
│       │   ├── __init__.py
│       │   ├── keys.py
│       │   ├── property_tables.py
│       │   ├── saturation_tables.py
│       │   └── quality_tables.py
│       ├── sampling/
│       │   ├── __init__.py
│       │   ├── grids.py
│       │   └── ranges.py
│       ├── validation/
│       │   ├── __init__.py
│       │   └── phases.py
│       ├── outputs/
│       │   ├── __init__.py
│       │   ├── metadata.py
│       │   ├── reports.py
│       │   └── writers.py
│       └── utils/
│           ├── __init__.py
│           └── units.py
├── tests/
├── examples/
└── outputs/
    └── .gitkeep
```

This structure is guidance, not a reason to create dead placeholder files.

Every created Python file should have a purpose.

Do not create empty modules unless they are needed for package structure.

---

## Initial files to create

For the first scaffold, create:

```text
AGENTS.md
README.md
LICENSE
.gitignore
pyproject.toml
configs/property_table_example.yaml
configs/saturation_table_example.yaml
configs/quality_table_example.yaml
src/carnopy/__init__.py
src/carnopy/__main__.py
src/carnopy/cli.py
src/carnopy/backends/coolprop_backend.py
src/carnopy/config/models.py
src/carnopy/properties/keys.py
src/carnopy/properties/property_tables.py
src/carnopy/properties/saturation_tables.py
src/carnopy/properties/quality_tables.py
src/carnopy/sampling/grids.py
src/carnopy/sampling/ranges.py
src/carnopy/validation/phases.py
src/carnopy/outputs/metadata.py
src/carnopy/outputs/reports.py
src/carnopy/outputs/writers.py
src/carnopy/utils/units.py
tests/
outputs/.gitkeep
```

Do not create generated datasets during scaffolding except tiny temporary outputs inside test temporary directories.

Do not commit generated outputs.

Do not create speculative CI files unless the human user asks.

Do not create GitHub Actions workflows in milestone 1 unless explicitly requested.

---

## Internal units

Use SI units internally:

```text
temperature: K
pressure: Pa
specific enthalpy: J/kg
specific entropy: J/kg/K
specific internal energy: J/kg
density: kg/m^3
specific heat capacity: J/kg/K
dynamic viscosity: Pa*s
thermal conductivity: W/m/K
speed of sound: m/s
surface tension: N/m
molar mass: kg/mol
```

Config files may accept common engineering units such as:

```text
°C
bar
kPa
MPa
```

but all backend calls must use SI units.

Exported column names must include units where practical.

Examples:

```text
T_K
T_C
p_Pa
p_bar
h_J_kg
s_J_kgK
u_J_kg
rho_kg_m3
cp_J_kgK
cv_J_kgK
viscosity_Pa_s
conductivity_W_mK
speed_sound_m_s
surface_tension_N_m
molar_mass_kg_mol
```

Avoid ambiguous exported column names such as:

```text
T
p
h
s
rho
mu
k
```

Internal local variables may use compact thermodynamic notation when the surrounding code is clear.

---

## Thermodynamic cautions

### Enthalpy and entropy

Enthalpy and entropy have reference-state offsets.

Store absolute values for reproducibility, but use differences for energy balances.

Do not compare absolute enthalpy or entropy values across different backends unless reference states are explicitly aligned and documented.

### Vapor quality Q

CoolProp vapor quality `Q` is meaningful for saturated and two-phase states.

Use:

```text
Q = 0      saturated liquid
0 < Q < 1 two-phase mixture
Q = 1      saturated vapor
```

Do not treat `Q` as a universal vapor fraction outside the two-phase region.

For superheated vapor, `Q` is not the correct criterion.

For subcooled liquid, `Q` is not the correct criterion.

Use phase detection and saturation comparisons for phase validation.

### Phase boundaries

Expect numerical and physical difficulty near saturation boundaries, critical points, and outside the fluid model's valid range.

Do not silently drop these cases.

Represent generated failures using `valid = false` and stable `failure_reason` values where practical.

### Backend disagreement

Future backends may disagree due to different equations of state, correlations, reference states, binary-interaction parameters, or transport models.

Do not treat backend disagreement as a Carnopy bug unless the input, units, and backend assumptions have been checked.

---

## Configuration validation policy

Invalid configuration values must fail fast before dataset generation.

Examples of invalid configuration values:

- missing mode
- unsupported mode
- unsupported backend
- unsupported input pair
- missing fluids
- unsupported fluid names
- unsupported property keys
- negative or zero pressure
- physically impossible temperature below 0 K
- zero or negative number of grid points
- vapor quality `Q` outside `[0, 1]`
- missing required range definitions for the selected mode
- invalid split fractions if split functionality is later added

Thermodynamically invalid generated states should become invalid rows with stable failure reasons whenever practical.

Examples of thermodynamically invalid generated states:

- CoolProp fails at a generated `T,p` point
- saturation calculation is requested above the critical temperature
- generated state is outside the valid fluid domain
- phase detection fails
- selected transport property is unavailable for the generated state

Do not mix these concepts.

Bad user configuration should fail before dataset generation.

Bad generated thermodynamic states should be recorded as invalid dataset rows whenever practical.

---

## Stable failure-reason taxonomy

Use stable snake_case failure reasons.

Initial allowed values:

```text
none
config_validation_failed
unsupported_mode
unsupported_backend
unsupported_input_pair
unsupported_property_key
unsupported_fluid
coolprop_property_call_failed
coolprop_phase_call_failed
outside_fluid_domain
outside_saturation_domain
above_critical_temperature
below_triple_temperature
invalid_quality
invalid_pressure
invalid_temperature
transport_property_unavailable
phase_validation_failed
writer_failed
metadata_failed
report_failed
unknown_error
```

Do not create ad-hoc failure strings unless a new recurring error category is clearly needed.

For valid rows, use:

```text
valid = true
failure_reason = none
```

For invalid rows, use:

```text
valid = false
failure_reason = <stable_failure_reason>
```

Do not silently replace failed thermodynamic values with zeros.

Use null/NaN for unavailable numerical values.

---

## Sampling policy

Sampling is a first-class part of Carnopy.

Milestone 1 should support deterministic sampling only.

Required milestone-1 sampling types:

```text
linear range
explicit value list if simple to implement
```

Optional milestone-1 sampling type if straightforward:

```text
logarithmic pressure range
```

Do not implement random, Latin-hypercube, Sobol, adaptive, active-learning, or phase-aware sampling in milestone 1 unless explicitly requested.

Every generated dataset must record the sampling specification in copied config and metadata.

Sampling order should be deterministic.

Row ordering should be stable for the same config, backend version, and package version.

---

## Dataset modes for milestone 1

Implement three dataset modes in milestone 1:

1. Property table
2. Saturation table
3. Vapor-quality table

---

## 1. Property table mode

Generate property tables from input pairs.

Start with `T,p`.

Example config concept:

```yaml
mode: property_table
backend: CoolProp
input_pair: TP

fluids:
  - Propane
  - Isobutane
  - n-Butane
  - Isopentane
  - n-Pentane
  - Cyclopentane

ranges:
  T_C:
    start: 20
    stop: 140
    points: 25
  p_bar:
    start: 1
    stop: 30
    points: 20

outputs:
  - Phase
  - HMASS
  - SMASS
  - UMASS
  - DMASS
  - CPMASS
  - CVMASS
  - VISCOSITY
  - CONDUCTIVITY
  - PRANDTL
```

Each row should include at least:

```text
case_id
source_kind
fluid
backend
backend_version
input_pair
T_K
T_C
p_Pa
p_bar
phase
valid
failure_reason
selected output properties
```

Use:

```text
source_kind = backend_generated
```

Failed CoolProp calls must not crash full dataset generation.

Failed property calls should become invalid rows with stable `failure_reason` values.

Phase-boundary or invalid-domain failures in `T,p` tables should be invalid rows, not unhandled exceptions.

---

## 2. Saturation table mode

Generate saturated liquid and saturated vapor property tables.

Start with temperature-based saturation tables.

Use:

```text
Q = 0 for saturated liquid
Q = 1 for saturated vapor
```

Each row should include at least:

```text
case_id
source_kind
fluid
backend
backend_version
T_sat_K
T_sat_C
p_sat_Pa
p_sat_bar
h_liq_J_kg
h_vap_J_kg
s_liq_J_kgK
s_vap_J_kgK
rho_liq_kg_m3
rho_vap_kg_m3
latent_heat_J_kg
valid
failure_reason
```

Do not calculate saturation points above the critical temperature or outside CoolProp's valid domain without marking them invalid.

Invalid saturation points should become invalid rows, not uncaught exceptions.

---

## 3. Vapor-quality table mode

Generate vapor-quality tables from `T,Q` first.

Later add `p,Q`.

Example config concept:

```yaml
mode: quality_table
backend: CoolProp
input_pair: TQ

fluids:
  - Propane
  - Isobutane
  - n-Butane
  - Isopentane
  - n-Pentane
  - Cyclopentane

ranges:
  T_C:
    start: 20
    stop: 120
    points: 51
  Q:
    start: 0.8
    stop: 1.0
    points: 21

outputs:
  - P
  - HMASS
  - SMASS
  - DMASS
  - CPMASS
  - VISCOSITY
  - CONDUCTIVITY
```

This means two-phase states from 80% vapor quality to saturated vapor.

It does not mean arbitrary superheated gas states.

Each row should include at least:

```text
case_id
source_kind
fluid
backend
backend_version
T_K
T_C
Q
p_Pa
p_bar
phase
valid
failure_reason
selected output properties
```

Validate that `Q` is between 0 and 1 during configuration validation.

If `Q` is outside `[0, 1]`, reject the configuration before dataset generation.

---

## CoolProp backend wrapper

Implement a thin CoolProp wrapper.

It should expose functions similar to:

```text
get_coolprop_version()
list_fluids()
props_si(...)
phase_si(...)
get_fluid_metadata(fluid)
safe_props_si(...)
safe_phase_si(...)
```

`safe_props_si` and `safe_phase_si` must not crash a full generation run.

Return structured information such as:

```python
{
    "valid": True,
    "value": 123.4,
    "failure_reason": "none",
}
```

or:

```python
{
    "valid": False,
    "value": None,
    "failure_reason": "coolprop_property_call_failed",
}
```

Keep the wrapper thin.

Do not hide CoolProp behavior behind excessive abstraction.

Do not silently replace failed values with zeros.

Use `None`/`NaN` plus `valid = false` and `failure_reason`.

---

## Property keys

Define curated CoolProp output keys with friendly exported column names and units.

Include at least:

```text
T
P
Q
Phase
HMASS
SMASS
UMASS
DMASS
CPMASS
CVMASS
VISCOSITY
CONDUCTIVITY
PRANDTL
SPEED_OF_SOUND
MOLARMASS
TCRIT
PCRIT
TTRIPLE
SURFACE_TENSION
```

Support curated keys by default.

Unsupported property keys in configuration should fail during config validation.

An advanced arbitrary-key mode may be added later, but default behavior should use curated keys to avoid unclear or unsupported outputs.

---

## Dataset schema stability

Column names are part of the public dataset contract.

Do not rename exported columns casually.

Avoid generating different schemas for different fluids in the same dataset.

For a given mode and config, the output schema should be stable even if some rows are invalid.

If a property column is unavailable for a row, keep the column and use null/NaN with:

```text
valid = false
failure_reason = <stable_failure_reason>
```

Rows should include provenance columns such as:

```text
source_kind
backend
backend_version
```

---

## Output handling

Generated datasets should be written to timestamped output directories.

Example:

```text
outputs/2026-06-15_153000_property_table/
```

Each full generation should produce:

```text
dataset.parquet
dataset.csv
metadata.json
report.json
config.yaml
```

Do not overwrite existing output directories.

Do not commit generated datasets.

`.gitignore` must ignore generated dataset outputs while keeping `outputs/.gitkeep`.

Generated datasets are disposable artifacts.

Do not design code that depends on previously generated output directories.

Tests must use temporary directories, not the repository `outputs/` directory.

---

## Metadata requirements

Metadata JSON should include at least:

```text
dataset_id
mode
created_at_utc
carnopy_version
source_kind
backend
backend_version
config_hash_sha256
row_count
valid_row_count
invalid_row_count
failure_reason_counts
fluids
input_pair
sampling
unit_system_internal
unit_columns_exported
output_files
```

Metadata is mandatory.

Generated datasets without metadata are incomplete.

---

## Report requirements

Each run should also produce `report.json`.

The report should summarize dataset quality and diagnostics.

Include at least:

```text
row_count
valid_row_count
invalid_row_count
failure_reason_counts
phase_counts
fluid_counts
min_max_by_numeric_column
duplicate_input_state_count
output_directory
```

The report is not a replacement for metadata.

Metadata describes provenance and reproducibility.

The report describes generated dataset quality and diagnostics.

---

## Optional ML-ready additions for later

Do not implement these in milestone 1 unless explicitly requested.

Future optional config may include:

```yaml
splits:
  enabled: true
  method: random
  train: 0.7
  validation: 0.15
  test: 0.15
  seed: 1234
```

Future optional outputs may include:

```text
split column
normalization statistics
feature schema
target schema
train/validation/test counts
```

Do not force ML split columns into every dataset.

Keep the core generator clean.

---

## CLI requirements

Use Typer.

Implement these commands for milestone 1:

```bash
carnopy fluids list
carnopy props generate --config configs/property_table_example.yaml
carnopy saturation generate --config configs/saturation_table_example.yaml
carnopy quality generate --config configs/quality_table_example.yaml
```

Also support:

```bash
python -m carnopy --help
```

Each generate command should print:

```text
mode
number of rows
valid rows
invalid rows
top failure reasons
output directory
```

The CLI should be the primary user interface for milestone 1.

The CLI should be suitable for reproducible local dataset generation.

Do not put thermodynamic calculation logic directly in CLI functions.

---

## README requirements

Create a concise practical README.

The README should explain:

- what Carnopy is
- what Carnopy is not
- why it is more than a thin `PropsSI` wrapper
- that CoolProp is the first backend
- that CoolProp is a dependency/reference, not Carnopy's identity
- what dataset modes exist
- how units are handled
- what `Q` means and does not mean
- how to install in editable mode after human-approved dependency setup
- how to run the CLI
- what files are generated
- what metadata and report files mean
- what is not implemented yet
- how this can later support ORC surrogate-model datasets

Use this positioning language or close equivalent:

```text
Carnopy is not a thermodynamic property model. It orchestrates existing property backends to generate reproducible, validated, ML-ready thermodynamic fluid-property datasets for surrogate-model training and engineering analysis.

The first backend is CoolProp. Future backends may include Thermopack, FeOs, or other property/EOS libraries. Generated datasets are backend-derived synthetic data, not experimental data or backend-independent ground truth.
```

Keep the README concise.

Do not write a theoretical thermodynamics tutorial.

Do not overpromise advanced ORC, mixture, or ML functionality before it exists.

Use short examples showing:

- installation
- one config
- one CLI command
- expected output files

Mention official CoolProp references:

```text
https://coolprop.org/coolprop/
https://github.com/CoolProp/CoolProp
```

---

## LICENSE

Create an MIT license.

Use this copyright holder:

```text
Göran Cem Alpay
```

---

## .gitignore policy

Create a minimal `.gitignore`.

Do not add speculative ignore patterns for tools or artifacts that the project does not use yet.

Only ignore artifacts expected from the current project setup:

```gitignore
# Python bytecode/cache
__pycache__/
*.py[cod]

# Test/lint/type-check caches
.pytest_cache/
.ruff_cache/
.mypy_cache/

# Virtual environments
.venv/
venv/

# Build/package artifacts
build/
dist/
*.egg-info/

# Generated datasets
outputs/*
!outputs/.gitkeep

# Local environment files
.env
.env.*
```

Do not globally ignore `*.csv`, `*.parquet`, `*.db`, or `*.sqlite` unless the project actually starts generating those outside the ignored output directory.

Do not ignore `.vscode/` unless local workspace settings are created and confirmed to be machine-specific.

Keep `.gitignore` short and justified.

Add new patterns only when the project actually creates those artifacts.

---

## Tests

Create basic tests for:

- unit conversion helpers
- config validation accepts valid example configs
- config validation rejects invalid `Q` outside `[0, 1]`
- config validation rejects unsupported property keys
- CoolProp wrapper works for Propane
- fluid list is non-empty
- property table generator returns rows
- saturation table generator returns rows
- quality table generator returns rows for valid `Q`
- generated rows include required provenance columns
- writers create output files for a tiny dataset in a temporary directory
- metadata contains required fields
- report contains required fields

Tests should be small and fast.

Tests may require CoolProp to be installed because CoolProp is a core runtime dependency.

Do not skip all CoolProp tests by default.

Do not make tests depend on large generated datasets.

Do not add slow integration tests in milestone 1.

Do not write tests that create output in the repository `outputs/` directory.

Use pytest temporary directories for writer tests.

---

## Development commands

After implementation, non-Git development commands may be run if they do not install or modify environments without approval.

Allowed inspection/test commands include:

```bash
python --version
python -c "import CoolProp, numpy, pandas; print('ok')"
python -c "import typer, pydantic, yaml, pyarrow; print('ok')"
ruff check .
pytest
rg "coolprop_syndata|coolprop-datagen|coolprop_datagen|coolprop-syndata" .
```

The following command requires human approval first because it installs the local project into the active environment:

```bash
python -m pip install -e ".[dev]"
```

If installation or tests fail, report the exact error and stop guessing.

Do not run Git commands.

---

## Quality bar

The generated software should be useful for engineering dataset generation, not just a demo.

Prefer:

```text
small tested functions
stable schemas
explicit units
validated configs
config-driven runs
deterministic sampling
clear failure reasons
metadata for reproducibility
reporting for dataset diagnostics
small fast tests
```

Avoid:

```text
giant scripts
silent exception handling
unclear units
hardcoded paths
unvalidated configs
unlabeled assumptions
dead placeholder files
speculative dependencies
speculative ignore patterns
dirty end-of-pipe cleanup
```

---

## Final response after implementation

After implementation, summarize:

- files created or modified
- non-Git commands run
- whether tests passed
- any failures
- any dependency or environment issues
- whether any package installation was needed but not performed
- output directory behavior
- next recommended human Git steps, without running them
