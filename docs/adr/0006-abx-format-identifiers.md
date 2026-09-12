# ADR 0006: `abx` is the format name, Trialmark is the product name

- Status: Accepted
- Date: 2026-09-08
- Scope: bundle format identifiers — schema `$id`s, `schema_id` manifest
  entries, the `abx_version` manifest field, and the `app.backend.app.evidence`
  module names

## Context

ADR 0005 renamed the product to Trialmark and changed the public surface: the
CLI program, the `.tmk` bundle suffix, and the
`application/vnd.trialmark.bundle+zip` media type. It deliberately left the
internal identifiers alone and deferred them to a later "phase B migration",
which left an open question with no decision behind it: does
`urn:evidenceos:abx:*` eventually become `urn:trialmark:tmk:*`?

The identifiers in question are the twelve schema `$id`s under
`app/backend/app/evidence/contracts/schemas/abx/0.1/`, the `schema_id` recorded
against every manifest entry that has one, the module-level `*_SCHEMA_ID`
constants that write them (`abx/`, `pipeline.py`, `decisions.py`,
`decision_statement.py`, `stats_kernel_abx.py`), and the `abx_version` field a
verifier reads out of `manifest.json`. Thirty-one files carry the string
today.

Renaming them is not a text substitution. A manifest entry's `schema_id` is part
of the canonical bytes the manifest digest covers, and ADR 0004 makes that digest
the bundle identity, so a rename rotates the `bundle_id` of every bundle ever
produced. The three committed ASOS benchmark bundles would need repacking and
their identities re-pinned in `AGENT_STATE.md` and the fixture tests, along with
every `.tmk` an external practitioner had already been given.

Two facts make the timing decidable now rather than later:

- No external bundle exists yet, so there is nothing in the field to break;
- the first one is due in phase J, so the window closes on its own.

## Decision

`abx` is the name of the bundle format. Trialmark is the name of the product
that writes and reads it. They are allowed to differ, the way a product's name
differs from the name of the file format it saves.

- `urn:evidenceos:abx:schema:0.1:*` is frozen as the namespace of format
  version 0.1. It is an opaque identifier: it resolves nothing, it is not
  fetched, and it makes no claim about who publishes the product today.
- The manifest field stays `abx_version`, and the module and schema-catalog
  paths keep the `abx` segment.
- These names change only together with a bundle format version — the earliest
  opportunity is 0.2 — and only if that version is worth publishing on its own
  merits. A rename is not by itself a reason to cut a format version.
- Product-facing surfaces stay Trialmark, exactly as ADR 0005 specifies. The
  `.tmk` suffix, the media type, the CLI name, and every user-visible string are
  unaffected by this ADR.

## Consequences

- The last bullet of ADR 0005 no longer defers to a "phase B migration"; this
  ADR is the decision it was waiting for. ADR 0005 stays accepted as written in
  every other respect.
- A reader who meets `urn:evidenceos:abx:schema:0.1:manifest` inside a bundle is
  meeting the format's namespace, not a stale brand. The schema catalog's
  `README.md` and this ADR are where that is written down.
- The three committed ASOS identities in `AGENT_STATE.md` stay valid, and no
  bundle in circulation is invalidated by a naming decision.
- A future 0.2 that does rename these identifiers must treat it as a breaking
  format change: new `$id`s, a new version field, repacked fixtures, and a
  verifier that still reads 0.1 bundles.
