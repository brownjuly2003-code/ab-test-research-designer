# ADR 0005: Trialmark rename

- Status: Accepted
- Date: 2026-08-26
- Scope: product brand, bundle filename, and HTTP media type

## Context

EvidenceOS is renamed to Trialmark. The v0.1 bundle transport needs a matching
public filename and media type, while its ZIP format and manifest identity stay
unchanged.

## Decision

- Product-facing text, UI, and CLI use the Trialmark name; the CLI program is
  `trialmark`.
- Newly created bundle destinations use the `.tmk` suffix. Verification and
  inspection identify a bundle by its ZIP content and manifest, not its
  filename.
- Trialmark bundle responses and uploads use
  `application/vnd.trialmark.bundle+zip`. The Workbench verifier also accepts
  legacy `application/octet-stream` uploads during the compatibility period.
- The archive remains a standard ZIP transport; no new magic bytes are added.

## Consequences

- ADR 0003 and ADR 0004 remain the accepted historical records. Their
  EvidenceOS and `.abx` terminology is superseded only where this ADR changes
  the public name, suffix, and media type.
- Module names, manifest field `abx_version`, schema catalog path, schema IDs,
  and `urn:evidenceos:abx:*` identifiers remain unchanged. ADR 0006 settles that
  question: `abx` is the name of the bundle format, Trialmark is the name of the
  product, and the 0.1 namespace is frozen until a bundle format version 0.2.
