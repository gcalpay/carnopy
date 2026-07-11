# Carnopy ML preparation roadmap

## Purpose

Carnopy prepares reproducible, backend-derived thermophysical datasets for
external machine-learning and surrogate-model workflows. It does not train,
select, optimize, or deploy models.

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
- `unsplit`, deterministic `shuffle`, `coordinate_block`, `range_holdout`,
  `leave_fluid_out`, `phase_holdout`, and `model_holdout` scenarios;
- ordered `log10`, `standard`, and `minmax` transformations, with fitted
  parameters learned from the training partition only;
- explicit reference-state compatibility checks for absolute specific
  enthalpy, entropy, and internal energy;
- optional `.npy`, `.npz`, and SafeTensors exports with recorded column order,
  units, shapes, dtypes, hashes, vocabularies, and conversion-error summaries;
  and
- machine-readable manifests, diagnostics, scenario reports, and a dataset
  card.

Parquet remains canonical. Array and tensor files are derived consumption
formats. Carnopy does not export pickled arrays, `.pt`, or `.pth` files and does
not require scikit-learn or PyTorch.

Categorical auxiliary arrays may use deterministic integer codes only when
auxiliary export is explicitly enabled. The manifest records the original
column, vocabulary, code order, missing-value code, dtype, and output-array
name.

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
- finite and missing summaries for selected features, targets, and numeric
  auxiliary fields;
- per-partition target summaries;
- duplicate thermodynamic-state candidates grouped from state columns, not
  target values; and
- conservative structured-grid diagnostics that explicitly skip unsupported
  shapes.

Quality flags are advisory by default. A statistical or structural warning is a
candidate for review, not proof of thermodynamic invalidity. Automatic exclusion
requires an explicit policy and stable reason codes. Flags remain in a separate
long-form table joined through `prepared_row_id`, leaving `table.parquet`
unchanged.

## Priority 1 — Quality and evaluation

- deterministic stratified hash scenarios using user-declared categorical
  strata and explicit numeric bin boundaries;
- declared-strata distributions and balance reports;
- missing-cell and spacing reports where the source mode makes those concepts
  valid;
- near-critical or near-saturation advisories only when the required reference
  values already exist in source columns or metadata; and
- stronger discontinuity and outlier candidate reports.

Carnopy must not invent scientific holdout domains or numeric strata. Small or
empty declared strata must produce a clear diagnostic rather than silent
rebalancing.

## Priority 2 — Curated features and transformations

Candidates for later reviewed stages include:

- robust scaling fitted from training-partition medians and interquartile
  ranges;
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
inverse transformation, and dependency boundary are reviewed. No dependency on
scikit-learn is planned merely to reserve these possibilities.

## Priority 3 — Interpretable diagnostics

Possible prepared-data inspection could report:

- feature and target correlations;
- numerical rank and singular-value spectra;
- PCA explained variance as a diagnostic;
- phase-, fluid-, and partition-specific range coverage; and
- candidate discontinuities or extreme local changes on compatible grids.

Fitted diagnostics use training rows only. An unsplit diagnostic may use all
eligible rows but must say so explicitly. PCA or SVD output does not silently
replace configured features.

Simple scikit-learn baseline regressors may eventually assess dataset
learnability, but only as an optional diagnostic workflow. Carnopy will not add
model registries, training loops, checkpoints, or deployment behavior to
preparation.

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
