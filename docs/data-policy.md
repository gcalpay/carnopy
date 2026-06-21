# Data and provenance policy

Carnopy outputs backend-generated synthetic thermophysical data. It does not
produce experimental measurements or backend-independent ground truth.

Every numeric dataset column uses SI and carries a unit suffix where applicable.
The same unit mapping is stored in metadata and Parquet schema metadata.

Rows use strict validity. If a required coordinate, phase, or requested property
fails, `valid` is false. Successfully evaluated values remain populated and
failed values remain null. Stable Carnopy failure fields are primary; raw
backend exception details are secondary diagnostics.

Configuration provenance includes:

- SHA-256 of exact source YAML bytes.
- SHA-256 of canonical materialized SI configuration bytes.
- Scientific `spec_id`.
- Artifact-context `generation_context_id`.
- Unique execution `run_id`.
- SHA-256 hashes of emitted non-metadata artifacts.

Specific enthalpy, entropy, and internal energy are reference-state dependent.
The CoolProp adapter sets requested fluids to `DEF` once before generation and
records that policy. This makes the convention reproducible but does not turn
these quantities into universal absolutes.

Generated run directories are immutable disposable artifacts and must not be
committed. Their human-facing names contain a UTC timestamp, a short mode label,
and an eight-character `run_id` prefix. The directory name is only a convenient
locator: full scientific and execution identities remain in `metadata.json`.
Carnopy preserves the exact source YAML as `config.original.yaml` and hashes
its bytes; it does not add the host source-config path to metadata.

Scientific figures are derived artifacts written outside source runs. Every
export includes a `.plot.json` sidecar containing the source hash, run/spec
identity, selected property and fluids, effective plotting settings, and image
hash. When source metadata is available, plotting fails on dataset hash
mismatch. Standalone files without metadata are marked unverified. Existing
image or sidecar paths are refused. Concurrent export cannot overwrite an
existing artifact, although process termination between the image and sidecar
links may leave an incomplete pair.
