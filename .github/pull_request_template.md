## Intent and scope

Describe the problem, the intended outcome, and what is deliberately out of
scope.

## Public compatibility

List any impact on CLI commands, Python APIs, YAML, dataset columns, metadata,
reports, failure codes, provenance, or existing generated runs. Write `None`
when there is no public-contract change.

## Scientific assumptions

Document thermodynamic assumptions, backend behavior, units, reference-state
considerations, tolerances, and primary references. Write `Not applicable` for
non-scientific changes.

## Verification

List the focused tests and quality commands run.

## Documentation and dependencies

Describe documentation updates and any dependency or packaging changes.

## Checklist

- [ ] The change is focused and linked to an issue when it changes a scientific
      or public contract.
- [ ] Tests cover each changed contract or corrected regression.
- [ ] User-facing behavior is documented.
- [ ] No generated datasets, figures, caches, environments, credentials, or
      local paths are committed.
- [ ] Dependency changes, if any, are intentional and reflected in
      `pyproject.toml` and `uv.lock`.
- [ ] I read and followed `AGENTS.md`.
