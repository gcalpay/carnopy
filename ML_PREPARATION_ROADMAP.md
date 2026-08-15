# Carnopy ML preparation roadmap

## Purpose

Carnopy prepares reproducible, backend-derived thermophysical datasets for
external machine-learning and surrogate-model workflows. It is not a training
or deployment framework. An optional diagnostic layer may fit disposable
baseline estimators to measure prepared-dataset learnability, but it never
persists, tunes, registers, or deploys them.

This document separates implemented preparation behavior from possible future
work. Future entries are design directions, not public API commitments. Each
requires its own reviewed plan before implementation.

## Implemented foundation

`carnopy prepare` currently provides:

- backend-free preparation from one immutable dataset run or model-sweep
  bundle;
- a user-facing Parquet table separated from provenance, source diagnostics,
  and row exclusions;
- deterministic row identity, ordering, hashes, and preparation identities;
- explicit numeric features, targets, auxiliary fields, and one-hot categorical
  features;
- `specific_volume`, `reduced_temperature`, `reduced_pressure`, and
  `compressibility_factor` through a curated derived-feature registry;
- `unsplit`, deterministic `shuffle`, user-binned `stratified_hash`,
  `coordinate_block`, `range_holdout`,
  `leave_fluid_out`, `phase_holdout`, and `model_holdout` scenarios;
- ordered `log10`, `standard`, `minmax`, and median/IQR `robust`
  transformations, with fitted
  parameters learned from the training partition only;
- explicit reference-state compatibility checks for absolute specific
  enthalpy, entropy, and internal energy;
- optional `.npy`, `.npz`, and SafeTensors exports with recorded column order,
  units, shapes, dtypes, hashes, vocabularies, and conversion-error summaries;
  and
- machine-readable manifests, diagnostics, scenario reports, and a dataset
  card.

Parquet remains canonical. Array and tensor files are derived consumption
formats. The current implementation does not export pickled arrays, `.pt`, or
`.pth` files and does not require PyTorch. Scikit-learn is isolated in the
optional `analysis` extra; the base and `ml` installations remain independent
of it.

Categorical auxiliary arrays may use deterministic integer codes only when
auxiliary export is explicitly enabled. The manifest records the original
column, vocabulary, code order, missing-value code, dtype, and output-array
name.

## Desktop exposure checkpoint

GUI-2 Stage 4 established worker-authoritative, revision-bound Preparation
planning and execution without adding a visible editor. Stage 5 is now
implemented through Unit 21A:

- Inspect derives typed Preparation eligibility and capability projections
  from verified dataset-run or model-sweep metadata;
- the Preparation workflow explicitly binds a copied inspection path,
  revision, descriptor, and profile, so ordinary inspection of another
  artifact cannot silently change scientific execution context;
- source context remains outside portable Preparation YAML and source changes
  never rewrite selected configuration;
- Python-owned drafts expose the complete current features, categoricals,
  targets, auxiliary fields, source policy, outputs, matrix settings, baseline
  settings, all eight scenario kinds, and ordered transformations;
- planning and execution consume an exact saved Preparation snapshot plus the
  explicit binding, and finalized results retain current, stale, or unrelated
  identity independently of page lifetime; and
- the packaged Preparation page and scenario editor are enabled through normal
  navigation, guarded Workspace creation, global document commands, source
  actions, and typed workflow context state; and
- finalized `data/quality_flags.parquet` is available through the same
  containment-checked, hash-verified, revision-bound, and bounded table-preview
  path as other Preparation tables, while corruption remains a reported quality
  issue rather than hiding the main bundle; and
- a Qt-independent audit projection validates and deterministically flattens
  finalized scenario, partition, duplicate-state, structured-grid, matrix,
  correlation, singular-value, and baseline evidence into typed row contracts,
  with explicit missing-value state and no inferred leakage claims when verified
  scenario-detail evidence is absent; and
- the worker supplies those scenario details only after bundle containment,
  recorded-hash, exact-byte, name, kind, and partition checks, while their file
  identities contribute to the inspection revision; the inspection controller
  validates the full projection before publishing its focused typed models and
  clears them when inspection becomes stale; and
- a reusable packaged audit component presents those exact models in bounded,
  contextual, responsive quality/scenario, matrix, and baseline sections and is
  directly tested with populated and unavailable evidence. Its normal Inspect
  integration remains the separate Unit 21B boundary.

This is desktop exposure of the implemented preparation contract, not new
preparation science. Integrated audit presentation, lifecycle hardening,
packaged qualification, and native acceptance remain later Stage 5 work.

## Reviewed future direction — Optional PyTorch dataset export

The product sequence now prioritizes desktop workflow depth and then source
breadth. This bounded PyTorch consumption format remains reviewed but planned
and unscheduled; it is not part of the current public interface.

The reviewed boundary is:

- configuration uses one `pytorch` format token under `outputs.arrays`;
- one `.pt` artifact contains a plain dictionary of CPU tensors for features,
  targets, and explicitly requested numeric or categorical auxiliary arrays;
- `.pth` is not a second format and is not emitted as a duplicate;
- custom Python objects, datasets, models, optimizers, predictions, and
  checkpoints are forbidden from the artifact;
- column order, units, dtype conversions, shapes, vocabularies, PyTorch
  version, and artifact hash remain recorded in the existing manifest;
- documented loading uses `map_location="cpu"` and restricted
  `weights_only=True` behavior;
- PyTorch is isolated in a dedicated optional dependency extra, while the base
  and existing `ml` installations remain independent; and
- Parquet remains canonical and SafeTensors remains the safer
  framework-neutral tensor format.

The implementation stage must qualify the optional dependency across Carnopy's
supported Python and platform matrix before changing packaging or public
templates. It must not narrow the supported base-install matrix merely to add
this derived format.

## Durable preparation rules

- Split assignment precedes every fitted transformation.
- Validation and test rows never influence training statistics.
- Raw canonical SI values remain available in Parquet.
- Preparation never calls a thermodynamic backend to fill missing information.
- Source rows are excluded only when the requested representation cannot be
  produced or an explicit future policy requests exclusion.
- Quality warnings must remain auditable and distinguish data-contract failures,
  backend diagnostics, and statistical candidates.
- Derived fields require a reviewed formula, dependencies, unit,
  reference-state classification, and array-export policy.
- Do not introduce undocumented integer fluid IDs or arbitrary user
  expressions. Any categorical integer coding must be explicitly requested and
  recorded in the manifest.

## Implemented in `0.1.0a3` — Advisory quality reports

Preparation bundles now include advisory quality diagnostics without training a
model:

- `quality_report.json`;
- `data/quality_flags.parquet`;
- manifest `quality_artifacts` entries and artifact hashes;
- eligible/excluded row counts;
- scenario and partition counts;
- distributions by fluid, phase, and backend model when those columns exist;
- finite, missing, range, quantile, median, IQR, raw MAD, skewness, and excess
  kurtosis summaries for selected features, targets, and numeric auxiliary
  fields, with estimator definitions recorded in the report;
- per-partition target summaries;
- duplicate thermodynamic-state candidates grouped from state columns, not
  target values; and
- provenance-backed exact eligible property-table grid diagnostics covering
  missing and repeated cells within observed coordinate levels, coordinate
  spacing, and adjacent phase-transition edges;
- exact-state split leakage prevention and audit summaries;
- user-declared categorical/numeric-bin stratified hash scenarios;
- opt-in feature-matrix singular values, numerical/effective rank,
  conditioning, constants, near-constants, feature correlations, and separate
  feature-target correlations; and
- optional train-fitted scikit-learn dummy, ridge, and histogram-gradient
  boosting baseline metrics on validation/test partitions.

Quality flags are advisory by default. A statistical or structural warning is a
candidate for review, not proof of thermodynamic invalidity. Automatic exclusion
requires an explicit policy and stable reason codes. Flags remain in a separate
long-form table joined through `prepared_row_id`, leaving `table.parquet`
unchanged.

## Priority 1 — Physical and local-structure advisories

- near-critical or near-saturation advisories only when the required reference
  values already exist in source columns or metadata; and
- stronger phase-safe discontinuity, derivative, and outlier candidate reports;
- metadata-backed grid contracts for saturation and vapor-fraction modes; and
- partition-specific fluid/phase/model coverage comparisons beyond the current
  one-dimensional group summaries.

Carnopy must not invent scientific holdout domains or numeric strata. Small or
empty declared strata must produce a clear diagnostic rather than silent
rebalancing.

## Priority 2 — Curated features and transformations

Candidates for later reviewed stages include:

- inverse temperature, with a positive-temperature contract and explicit unit;
- source-backed fluid descriptors such as molar mass or critical properties;
  and
- phase-safe gradient labels on suitable structured grids without bridging
  invalid rows or phase boundaries.

Avoid a generic `normalize` operation because it can mean min-max scaling,
standardization, or per-row vector normalization. Public configuration should
name the exact transformation.

Saturation temperature, saturation pressure, superheat, subcooling, and
pressure-ratio-to-saturation require saturation reference data. Preparation
may derive them only when those references are already present or are supplied
through a separately reviewed join contract; it must not query CoolProp.

Power and quantile transformations remain research candidates. They can distort
physical distances and are not committed until their semantics, provenance,
inverse transformation, and dependency boundary are reviewed. No additional
scikit-learn functionality is added merely to reserve these possibilities.

## Priority 3 — Further interpretable diagnostics

Possible prepared-data inspection could additionally report:

- explicitly labelled PCA component loadings and explained variance as a
  diagnostic, without replacing configured features;
- phase-, fluid-, and partition-specific range coverage; and
- candidate discontinuities or extreme local changes on compatible grids.

Fitted diagnostics use training rows only. An unsplit diagnostic may use all
eligible rows but must say so explicitly. PCA or SVD output does not silently
replace configured features.

Current optional baseline regressors assess dataset learnability only. Carnopy
will not add model registries, training loops, checkpoints, hyperparameter
search, or deployment behavior to preparation.

Neural-network architecture and optimization choices remain outside this
boundary. Flatten or dense layers, activation functions, cross-entropy and
other training losses, optimizers, epochs, and backpropagation belong to the
external framework consuming a prepared Carnopy bundle. They are not
preparation transformations or quality diagnostics.

## Future consumption-format evaluation

The implemented `.npy`, `.npz`, and SafeTensors exports already cover direct
array and framework-neutral tensor consumption while Parquet remains the
canonical structured dataset. Do not add formats merely to increase the format
count.

Two additions may justify a later reviewed export stage:

- Arrow IPC or Feather for explicit low-copy columnar interchange with
  PyArrow, pandas, Polars, and compatible consumers; and
- HDF5 for a demonstrated engineering workflow that needs hierarchical arrays
  and embedded metadata unavailable from the existing Parquet plus manifest
  bundle.

Either addition requires a concrete consumer, deterministic serialization and
hashing rules, dtype and null semantics, metadata placement, optional-dependency
review, round-trip tests, and an explicit statement that the file is derived
from canonical Parquet data.

NetCDF or Zarr is deferred unless Carnopy later owns a reviewed labelled,
multidimensional data model rather than only flat tabular outputs. JSON Lines,
Excel, SQLite, and other database-shaped exports are not current priorities:
they either weaken numerical/tabular behavior or duplicate capabilities already
covered by Parquet and downstream tools.

## Later research directions

Active learning belongs to a separate backend-aware generation workflow. It
would require a coarse dataset, an explicit error or uncertainty measure, and a
reviewed sampling policy before requesting additional backend states.

Sparse Identification of Nonlinear Dynamics (SINDy) targets time-evolving
dynamical systems. Carnopy's current thermophysical tables are static mappings,
so SINDy is deferred unless a future workflow provides trajectories or
scientifically defensible derivative targets.

Minimization and maximization are not data-preparation operations. Future
optimization requires an explicit surrogate or process model, objective,
constraints, operating domain, and validation policy. It belongs in a separate
surrogate or engineering-analysis subsystem.

PyMC may become relevant for Bayesian calibration or uncertainty
quantification against experimental observations. Carnopy currently emits
synthetic backend output rather than experimental likelihood data, so PyMC is
not part of the preparation roadmap.

## References

- Cersonsky, Cheng, Kofke, and Müller, [Machine Learning for Generating and
  Analyzing Thermophysical Data: Where We Are and Where We're
  Going](https://doi.org/10.1021/acs.jced.4c00207), *Journal of Chemical &
  Engineering Data* 69 (2024), 2041–2043.
- Géron, [Hands-On Machine Learning with Scikit-Learn and
  PyTorch](https://www.oreilly.com/library/view/hands-on-machine-learning/9798341607972/),
  O'Reilly Media, 2025.
- scikit-learn, [Common pitfalls and recommended
  practices](https://scikit-learn.org/stable/common_pitfalls.html), especially
  train/test separation and preprocessing leakage.
- scikit-learn, [Preprocessing
  reference](https://scikit-learn.org/stable/api/sklearn.preprocessing.html),
  for the semantics and tradeoffs of common transformations.
- Brunton, Proctor, and Kutz, [Discovering governing equations from data by
  sparse identification of nonlinear dynamical
  systems](https://doi.org/10.1073/pnas.1517384113), *PNAS* 113 (2016),
  3932–3937.
- [PySINDy documentation](https://pysindy.readthedocs.io/en/stable/), for the
  dynamical-system scope of SINDy methods.
