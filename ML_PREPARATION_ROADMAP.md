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
planning and execution without adding a visible editor. Stage 5 is complete:

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
  directly tested with populated and unavailable evidence; and
- Inspect exposes that component only for a successfully accepted Preparation
  bundle, keeps exact audit-artifact issues beside accepted evidence, preserves
  explicit legacy-unavailable state, and hides an obsolete selected audit tab
  when the inspected source changes; and
- operation-specific response contexts, direct-slot action guards, and
  identity-bound multi-step shutdown now protect the complete desktop
  lifecycle, while shared Plan, Execute, Cancel, Force Stop, and Inspect Result
  actions cross a queued root facade instead of mutating workflow projections
  inside their originating QML click handler; and
- the exact packaged QML and Python inventories include the complete
  Preparation surface, while both installed app-only launchers instantiate,
  bind, and responsively resize that page without runtime warnings.

This is desktop exposure of the implemented preparation contract, not new
preparation science. The complete locked local gate passed with both 1,073-test
suites and final distribution verification. Remote verification and native
functional acceptance also passed. Broader onboarding and workflow
discoverability remain a post-Stage-5 UX follow-up rather than preparation
science or an unfinished data contract. The accepted implementation record is
indexed in [`docs/archive/GUI2_STAGE5.md`](docs/archive/GUI2_STAGE5.md).

## Reviewed future direction: Optional PyTorch dataset export

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

## Framework interoperability boundary

Carnopy should make prepared thermophysical data easy to consume without
becoming a training framework or accumulating unrelated runtime dependencies.
Future interoperability should use three explicit levels:

1. framework-neutral files and manifests owned by Carnopy;
2. small, optional, version-qualified consumption adapters; and
3. external training and orchestration systems that remain outside Carnopy.

The current and candidate technologies fall into these categories:

| Technology | Roadmap classification | Rationale |
| --- | --- | --- |
| SafeTensors | Implemented derived export | Framework-neutral tensor storage with deterministic manifest evidence; Parquet remains canonical. |
| PyTorch | Reviewed optional adapter candidate | A plain `.pt` tensor dictionary, or a documented Dataset/DataLoader consumer adapter, may reduce integration effort without moving training into Carnopy. |
| DeepXDE | External physics-informed consumer | A candidate example integration for PINNs and scientific ML over prepared bundles, not a Carnopy dependency or execution engine. |
| NVIDIA PhysicsNeMo | External physics-informed consumer | A candidate consumer for PINNs and neural operators when exact coordinates, fields, constraints, and provenance can be mapped explicitly. |
| XGBoost | Optional external tabular benchmark | Useful for nonlinear regression baselines or downstream studies only when a concrete comparison need justifies an adapter. |
| LightGBM | Optional external tabular benchmark | Potentially useful for large prepared tables, but not added merely to increase estimator count. |
| CatBoost | Optional external tabular benchmark | Potentially useful when categorical fluid or model identities remain native categorical features; the current one-hot representation is not a drop-in CatBoost contract. |
| DeepSpeed | External distributed-training infrastructure | Training optimization, checkpointing, and distributed execution remain consumer responsibilities. |
| Ray | External orchestration and tuning infrastructure | A future adapter requires a concrete distributed or hyperparameter-search workflow; Ray is not part of preparation itself. |
| Helion | Out of scope for Carnopy core | A GPU kernel language sits below Carnopy's data and provenance abstraction. |
| vLLM | Out of scope for thermophysical ML Preparation | LLM inference and serving do not address Carnopy's tabular scientific-data contract. |

These classifications prevent name-driven dependency growth. An adapter must
solve a demonstrated workflow, preserve the exact Preparation bundle identity,
and pass dependency, platform, serialization, security, and maintenance review.

Flatten operations are tensor reshaping or neural-network layer choices, not
thermophysical feature transformations. Cross-entropy is a classification loss
and is relevant only to an explicit future classification target such as phase
or validity class. It is not an appropriate default for continuous property
regression. More relevant external regression measures include mean absolute
error, root mean squared error, Huber loss, carefully defined relative error,
maximum error, and physics-consistency residuals. Carnopy may define how
imported evaluation evidence is interpreted, but it does not own the training
loop or loss optimization.

## Imported prediction results and ML visualization

A useful ML workflow requires more than writing arrays. A future reviewed
result-import contract should let Carnopy inspect and compare outputs from an
external trainer without loading executable model objects. Every imported
result must bind to:

- the exact Preparation bundle and manifest identity;
- scenario and partition identities;
- source dataset or sweep identity;
- feature, target, unit, row, and transformation definitions;
- external framework, model, training-run, and artifact identities;
- prediction and uncertainty column semantics;
- declared metrics and aggregation domains; and
- immutable imported bytes with hashes and provenance.

Imported results must reject or clearly quarantine incompatible row identities,
partitions, targets, units, inverse transformations, and stale source bindings.
Carnopy should not deserialize arbitrary checkpoints, execute user models, or
infer missing training metadata.

Candidate result views include:

- predicted-versus-reference parity plots;
- residual distributions and quantile summaries;
- error by fluid, phase, backend model, temperature, pressure, composition, and
  validity domain;
- train, validation, test, and holdout comparisons;
- learning and validation curves when supplied by the external trainer;
- uncertainty calibration and coverage plots; and
- side-by-side model comparisons over the exact same accepted rows.

The result-import and visualization contract should work across PyTorch,
DeepXDE, PhysicsNeMo, scikit-learn, XGBoost, LightGBM, CatBoost, and other
external consumers without making any one framework the scientific authority.

Framework-ready future exports should preserve coordinates, properties, units,
composition, domain masks, phase labels, available derivatives, physical
constraints, and complete provenance. They must not fabricate derivative or
constraint fields merely because a consumer framework can accept them.

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
- scikit-learn, [Model evaluation](https://scikit-learn.org/stable/modules/model_evaluation.html)
  and [learning curves](https://scikit-learn.org/stable/modules/learning_curve.html).
- PyTorch, [`torch.flatten`](https://docs.pytorch.org/docs/stable/generated/torch.flatten.html)
  and [`CrossEntropyLoss`](https://docs.pytorch.org/docs/stable/generated/torch.nn.CrossEntropyLoss.html),
  for their actual tensor and classification semantics.
- [DeepXDE](https://github.com/lululxvi/deepxde) and
  [NVIDIA PhysicsNeMo](https://docs.nvidia.com/deeplearning/physicsnemo/physicsnemo-core/),
  as candidate external physics-informed consumers.
- [XGBoost](https://xgboost.readthedocs.io/en/stable/index.html),
  [LightGBM](https://lightgbm.readthedocs.io/en/stable/), and
  [CatBoost](https://catboost.ai/docs/en/), as candidate external tabular
  consumers.
- [DeepSpeed](https://deepspeed.readthedocs.io/en/stable/index.html),
  [Ray Tune](https://docs.ray.io/en/latest/tune/tutorials/tune-lifecycle.html),
  [Helion](https://pytorch.org/blog/helion/), and
  [vLLM](https://docs.vllm.ai/en/stable/index.html), for the boundaries between
  data preparation, external orchestration, kernel generation, and LLM serving.
- Hugging Face, [SafeTensors](https://huggingface.co/docs/safetensors/index), for
  the implemented framework-neutral tensor format.
- Brunton, Proctor, and Kutz, [Discovering governing equations from data by
  sparse identification of nonlinear dynamical
  systems](https://doi.org/10.1073/pnas.1517384113), *PNAS* 113 (2016),
  3932–3937.
- [PySINDy documentation](https://pysindy.readthedocs.io/en/stable/), for the
  dynamical-system scope of SINDy methods.
