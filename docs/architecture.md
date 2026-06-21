# Architecture

Carnopy separates configuration, backend access, generation, and artifact
writing:

```text
YAML
  -> validated config
  -> canonical SI specification
  -> thin backend adapter
  -> mode-specific rows
  -> stable DataFrame schema
  -> CSV/Parquet + metadata/report
```

The public Python API is intentionally narrow: load, validate, generate, and
optional visualization. Mode generators and CoolProp mappings are internal.

The backend boundary covers only capabilities used in Milestone 1. It is not a
plugin framework. Future adapters can implement the same semantic operations
when concrete requirements exist.

Runs are staged in a sibling directory and atomically renamed. Existing run
directories are never overwritten. Final names use
`<UTC-second>_<mode-slug>_<run-prefix>` for practical command-line use. The
short name is not a reproducible identity; complete identities remain in
metadata.

Optional visualization is isolated under `carnopy.visualization`. It reads
finalized datasets, verifies recorded hashes, and exports figures outside the
immutable source run. Property curves and sampled heatmaps use only emitted
columns; visualization never calls a backend or interpolates thermodynamic
states. A centralized semantic-field registry controls scientific labels,
units, filters, and later plot extensions. Matplotlib is not imported by
generation modules or CLI help. Figure and sidecar finalization uses exclusive
same-filesystem hard links to prevent overwrites; the pair is not fully
crash-atomic.

Identity layers:

- `spec_id`: canonical scientific specification.
- `generation_context_id`: specification plus software/artifact context.
- `run_id`: one UUID4 execution attempt.
- Artifact hashes: the exact emitted bytes.
