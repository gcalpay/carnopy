# Packaging and release safeguards

This document is an authoritative routed part of the root
[contributor and coding-agent guide](../../AGENTS.md). Read it in full before
changing packaging metadata, dependency extras, distribution inventories,
publishing workflows, versions, tags, or releases. It must be combined with the
routed development workflow and `.agents/local.md`.

## Packaging and release safeguards

Use the `src/` layout and Hatchling:

```toml
[build-system]
requires = ["hatchling>=1.27.0"]
build-backend = "hatchling.build"
```

Matplotlib remains optional through `viz`; SafeTensors remains optional through
`ml`; scikit-learn remains optional through `analysis`; PySide6 Essentials and
Matplotlib remain optional through `app`; `all`
must remain synchronized with all user-facing extras. PyArrow remains core.
Qt/PySide6 remains an externally licensed optional dependency. Carnopy does not
vendor Qt or ship standalone desktop installers; downstream redistribution
requires review of the applicable Qt terms rather than assumptions based on
Carnopy's MIT license.

Carnopy uses alpha releases before stable `0.1.0`. The release workflow builds
one wheel and sdist, verifies them, requires human approval, and publishes them
to production PyPI through GitHub OIDC Trusted Publishing.

Only a human maintainer may:

- make the repository public;
- configure GitHub environments or Trusted Publishers;
- create or push release tags;
- approve production deployment;
- publish to PyPI.

Never rebuild changed payloads under an uploaded version. Any changed payload
requires a new version. Never use `skip-existing` to repair a partial release.

For each release:

1. update the source version and user-facing installation examples;
2. run the complete source and distribution gates;
3. commit and push, then require green CI on `main`;
4. create one annotated `v<version>` tag;
5. push only that tag and approve the protected `pypi` environment;
6. verify the published release and create a matching GitHub pre-release while
   Carnopy remains alpha.

Do not move or reuse a published version tag. After stable `0.1.0`, use ordinary
release versions unless a deliberate prerelease is needed.

Distribution checks:

```bash
uv run --locked --group release python -m build
uv run --locked --group release python -m twine check dist/*
uv run --locked python scripts/check_distribution.py dist/*
```

`python -m build` normally uses its default isolated build environment. That
environment installs the `[build-system]` requirements declared in
`pyproject.toml`. Do not modify the development environment solely to satisfy
the build backend. Use the ignored, repository-local `prerelease/` directory
for non-destructive rehearsal builds when an existing `dist/` must be
preserved. Final release artifacts belong in `dist/`. Do not write Carnopy
build artifacts outside the repository.

