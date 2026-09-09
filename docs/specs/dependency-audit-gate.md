# Capability: dependency-audit-gate

The repository ships three separately locked dependency trees — the Python
backend (`app/backend/requirements*.txt`, compiled by `uv` with hashes), the
frontend npm root (`app/frontend`), and the documentation site npm root
(`docs-site`). CI gates all three in the single `dependency-audit` job of the
`Tests` workflow. Because the job's steps run sequentially and each one fails
the job, a failure in an earlier tree hides the state of the later ones.

## Requirement: the audit gate covers every locked dependency tree

The `dependency-audit` CI job SHALL audit the backend lock, the frontend npm
root, and the docs-site npm root on every push to `main`, on pull requests, and
on the weekly schedule. A remediation SHALL NOT be considered complete until
every one of the three commands has been observed exiting 0 on the same tree,
because a green earlier step is not evidence about the steps behind it.

### Scenario: an earlier step masks a later failure

- **GIVEN** the backend audit step fails on a known advisory
- **WHEN** the `dependency-audit` job runs
- **THEN** the frontend and docs-site audit steps are reported as skipped, and
  their result on that commit is unknown rather than clean

### Scenario: the whole gate is verified before the state is called green

- **GIVEN** a change intended to restore the audit gate
- **WHEN** the maintainer verifies the remediation
- **THEN** `python -m pip_audit -r app/backend/requirements-dev.txt`,
  `npm audit --audit-level=high` in `app/frontend`, and
  `npm audit --audit-level=high` in `docs-site` have each been run on the same
  working tree and each exited 0

## Requirement: advisories are cleared by upgrading, not by suppression

Known advisories SHALL be cleared by moving the affected package to a fixed
version — directly, or by an npm `overrides` entry / recompiled `uv` lock for
transitive packages. The gate SHALL NOT be made green by ignoring advisory
identifiers, lowering `--audit-level`, dropping an audit step, or removing an
audited dependency tree from CI.

### Scenario: a transitive package has no direct pin

- **GIVEN** a high-severity advisory against a transitive npm package
- **WHEN** the maintainer remediates it
- **THEN** the fixed version is reached through the package's own dependents or
  through an explicit `overrides` entry, and `npm audit --audit-level=high`
  exits 0 afterwards

### Scenario: a pin added to fix a past advisory becomes vulnerable itself

- **GIVEN** an `overrides` entry pinning a package to an exact version that a
  later advisory covers
- **WHEN** the audit reports that pinned version as vulnerable
- **THEN** the override is raised to a fixed version rather than removed,
  so the dependents that needed the pin keep a resolvable constraint

## Requirement: backend locks stay compiled, hashed, and reproducible

Backend dependency changes SHALL be made in `requirements.in` /
`requirements-dev.in` and recompiled with
`uv pip compile <in> --universal --generate-hashes -o <txt>`. The compiled
`requirements*.txt` files SHALL NOT be hand-edited, so every pin keeps its
sha256 hashes and the header that records the generating command.

### Scenario: a backend package must move to clear an advisory

- **GIVEN** a pinned backend package with a known advisory and a published fix
- **WHEN** the maintainer raises the pin
- **THEN** the change appears in the `.in` file, the `.txt` lock is regenerated
  by `uv pip compile` with `--generate-hashes`, and the lock still installs
  under `pip install --require-hashes`

## Requirement: remediation scope stays minimal and verifiable

A remediation SHALL move only the pins needed to clear the reported advisories
plus whatever their resolution forces. Unrelated major upgrades SHALL NOT be
adopted as part of an audit fix, and every touched tree's own test and build
commands SHALL pass afterwards.

### Scenario: an unrelated major upgrade is available at the same time

- **GIVEN** an open dependency-bump proposal for a package with no advisory
  against its currently locked version
- **WHEN** the maintainer remediates an unrelated advisory
- **THEN** the unrelated major upgrade is left out of the remediation change
