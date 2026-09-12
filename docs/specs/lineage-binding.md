# Capability: ABX lineage binding

<!-- Durable spec: it outlives the run. One capability per file; MyFlow injects the requirements a task
     references into the WorkOrder and the review pack. Format is OpenSpec-compatible. -->

## Requirement: Every protocol reference resolves to the bundled protocol content
The verifier SHALL compute `protocol_revision_id` as the SHA-256 digest of the RFC 8785 canonical bytes of
the bundled protocol document. The manifest, run document, every estimate lineage, and every decision
record SHALL carry that value. A well-formed digest string that does not equal the computed value is an
unbound reference and SHALL fail lineage with `lineage/unbound_reference`.

### Scenario: a one-byte protocol change cannot be hidden by rebinding integrity
- **GIVEN** a protocol member changed by one byte and a manifest whose member size, digest, and bundle id
  are recomputed
- **WHEN** the bundle is verified without updating its protocol references
- **THEN** integrity passes but lineage fails with `lineage/unbound_reference`

→ test: app/backend/tests/test_evidence_abx_content_binding.py::test_one_byte_protocol_json_change_fails_lineage_after_integrity_rebind

### Scenario: a decision protocol mismatch is a binding failure
- **GIVEN** a decision whose `protocol_revision_id` is a different well-formed digest
- **WHEN** the enclosing member and manifest integrity are rebound
- **THEN** lineage fails with `lineage/unbound_reference`, not `decision_context`

→ test: app/backend/tests/test_evidence_abx_content_binding.py::test_decision_protocol_mismatch_is_unbound_reference_not_decision_context

## Requirement: A query identity binds exact SQL bytes and its execution identity
Each query's `statement_digest` SHALL equal the manifest digest of the exact bytes at `statement_path`.
Its `query_id` SHALL equal the digest of the canonical identity document formed from `dialect`,
`parameters_digest`, the referenced source document's `fingerprint`, and `statement_digest`. Estimate
lineage may cite only query ids declared by the run.

### Scenario: changing SQL bytes invalidates the statement binding
- **GIVEN** a query member whose SQL bytes change while the run retains its old `statement_digest`
- **WHEN** member integrity is rebound in the manifest
- **THEN** lineage fails with `lineage/unbound_reference`

→ test: app/backend/tests/test_evidence_abx_content_binding.py::test_statement_digest_not_bound_to_query_bytes_fails_lineage

### Scenario: changing an identity input invalidates query_id
- **GIVEN** a run whose `parameters_digest` changes while its `query_id` remains unchanged
- **WHEN** the bundle is verified
- **THEN** lineage fails because `query_id` no longer matches the canonical identity document

→ test: app/backend/tests/test_evidence_abx_content_binding.py::test_query_id_not_bound_to_identity_document_fails_lineage

## Requirement: Estimate metric lineage binds the exact bundled metric member
For each estimate, `lineage.metric.metric_id` SHALL resolve to one bundled metric,
`lineage.metric.metric_version` SHALL equal that metric's version, and
`lineage.metric.metric_digest` SHALL equal the manifest digest of the metric member's exact saved bytes.
Recomputing the outer manifest cannot substitute an unrelated digest into the estimate.

### Scenario: an unrelated metric digest fails lineage
- **GIVEN** an estimate whose metric id and version resolve but whose `metric_digest` is unrelated
- **WHEN** the enclosing member and manifest integrity are rebound
- **THEN** lineage fails with `lineage/unbound_reference`

→ test: app/backend/tests/test_evidence_abx_content_binding.py::test_estimate_metric_digest_not_bound_to_metric_content_fails_lineage

## Requirement: Definition digests bind embedded metric semantics when those semantics are present
When exactly one extension payload contains a `definition`, the metric's `definition_digest` SHALL equal
the digest of that canonical definition value, and the matching protocol metric reference SHALL carry the
same content-bound digest. A changed definition cannot be legitimized by leaving matching stale strings in
the protocol and metric. If no definition is embedded, the verifier SHALL preserve interoperability by
reporting the metric path in `unbound_bindings` while still comparing the protocol and metric digest
strings. Ambiguous or unlocatable embedded definitions SHALL be both reported in `unbound_bindings` and
rejected with `lineage/unbound_reference`.

### Scenario: matching stale definition strings do not authenticate changed semantics
- **GIVEN** an embedded definition is changed while the protocol and metric retain the same old
  `definition_digest`
- **WHEN** metric-member and manifest integrity are rebound
- **THEN** lineage fails because the digest is not bound to the embedded definition content

→ test: app/backend/tests/test_evidence_abx_content_binding.py::test_embedded_definition_mutation_fails_lineage_while_digest_strings_still_match

### Scenario: an absent embedded definition is disclosed without inventing a failure
- **GIVEN** metric documents with no embedded definition payload
- **WHEN** their protocol and metric digest strings still agree
- **THEN** the bundle remains valid and the metric paths appear in `unbound_bindings`

→ test: app/backend/tests/test_evidence_abx_t09_deferred.py::test_absent_embedded_definition_surfaces_unbound_bindings

### Scenario: ambiguous and unlocated definitions cannot claim a content binding
- **GIVEN** one metric with multiple candidate definitions and another with an extension payload whose
  definition cannot be located
- **WHEN** the bundle is verified
- **THEN** both paths appear in `unbound_bindings` and lineage fails

→ test: app/backend/tests/test_evidence_abx_t09_deferred.py::test_ambiguous_and_unlocated_definitions_are_in_unbound_bindings

## Requirement: A decision child is an append-only citation of one parent bundle
Recording a human decision SHALL leave the parent run unchanged and create a distinct child run. The child
run's `parent_run_id` SHALL name the parent run. Its decision predicate `cites_bundle_id`, manifest
`supersedes`, and the single in-toto statement subject SHA-256 SHALL all name the same parent bundle id.
Any disagreement among the citation, subject, and supersedes value is an unbound lineage reference.

### Scenario: a recorded decision forms a verified child chain
- **GIVEN** a completed parent run and a human decision on its evidence
- **WHEN** the decision child is materialized and verified
- **THEN** the parent is unchanged and `parent_run_id`, `cites_bundle_id`, `supersedes`, and the DSSE
  statement subject form one consistent chain

→ test: app/backend/tests/test_evidence_decisions.py::test_human_decisions_create_verified_append_only_child_runs
