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

The public Python API is intentionally narrow: load, validate, and generate.
Mode generators and CoolProp mappings are internal.

The backend boundary covers only capabilities used in Milestone 1. It is not a
plugin framework. Future adapters can implement the same semantic operations
when concrete requirements exist.

Runs are staged in a sibling directory and atomically renamed. Existing run
directories are never overwritten.

Identity layers:

- `spec_id`: canonical scientific specification.
- `generation_context_id`: specification plus software/artifact context.
- `run_id`: one UUID4 execution attempt.
- Artifact hashes: the exact emitted bytes.
