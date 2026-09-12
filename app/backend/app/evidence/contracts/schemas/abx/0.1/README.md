# ABX v0.1 schema catalog

This directory is the trusted offline JSON Schema Draft 2020-12 catalog for
ABX `0.1.x`. Each schema has an absolute `urn:evidenceos:abx:schema:0.1:*`
identifier. Verifiers resolve those identifiers only from their built-in
catalog; embedded bundle copies are archival evidence, not trust roots.

The catalog defines the manifest and every structured artifact in the v0.1
logical layout: frozen protocol, amendments, run, source snapshot, metric,
finding, estimate, decision record, and unsigned DSSE decision statement.
Objects are closed by default, except for the standard DSSE envelope where
unknown fields remain forward-compatible. Extension data is allowed only under
explicit `extensions` objects with namespaced keys.

Schema validation covers local structure and formats. The bundle verifier must
separately enforce rules that require bytes or relationships, including:

- duplicate-key and non-I-JSON rejection before schema validation;
- manifest entry ordering and unique normalized paths;
- bundle and artifact digest/size verification;
- cross-artifact references and known required capabilities;
- protocol allocation and other cross-field domain invariants;
- privacy, secret and small-cell policy.

Golden cases live in `app/backend/tests/fixtures/abx/0.1`. `cases.json`
declares the expected schema verdict and the decisive validator location for
every invalid case.
