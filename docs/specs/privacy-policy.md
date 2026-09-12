# Capability: ABX privacy policy

<!-- Durable spec: it outlives the run. One capability per file; MyFlow injects the requirements a task
     references into the WorkOrder and the review pack. Format is OpenSpec-compatible. -->

## Requirement: Privacy scanning covers the exact content that can leave the workspace
The verifier SHALL recursively scan `manifest.json`, every structured JSON role, and embedded schemas.
Every other member, including query and report roles, SHALL be decoded as UTF-8 and scanned as text. A
decision carried in DSSE SHALL be scanned twice at its two meaningful representations: the envelope as a
structured member and the decoded in-toto statement recursively, including its decision predicate. The run
materializer SHALL apply the same logical verification to the exact member bytes before publishing them.

### Scenario: a connection string in a query fails the bundle privacy verdict
- **GIVEN** a manifest-listed SQL query containing a database connection string
- **WHEN** the archive is verified
- **THEN** `privacy_policy` is `fail` and an error has code `sensitive_value`

→ test: app/backend/tests/test_abx_cli.py::test_privacy_policy_rejects_connection_string_in_query

### Scenario: materialization applies policy before bytes are published
- **GIVEN** a completed run whose exact query member contains a connection string
- **WHEN** the run is materialized as a logical ABX bundle
- **THEN** materialization fails with `sensitive_value`

→ test: app/backend/tests/test_evidence_run_bundle.py::test_materializer_applies_privacy_policy_to_exact_members

## Requirement: Secret-bearing keys and recognizable sensitive text are rejected
JSON keys SHALL be split across camel case, acronym boundaries, and punctuation before comparison. A
non-empty value under `access_token`, `api_key`, `api_token`, `connection_string`, `credentials`, `dsn`,
`password`, `passwd`, `private_key`, `secret`, or `secret_key` SHALL be rejected regardless of nesting.
String content SHALL also be rejected when it contains a supported database connection URI, PEM private
key header, AWS `AKIA` or `ASIA` access key, GitHub provider token, OpenAI `sk-` token, email address,
supported international or Russian phone number, valid IPv4 or IPv6 address, or absolute Windows, UNC, or
POSIX path. Every such violation SHALL set `privacy_policy` to `fail` with code `sensitive_value` and a
path to the offending member or JSON pointer.

### Scenario: adversarial key styles and text patterns are detected
- **GIVEN** nested JSON using camel-case or acronym secret keys, contact details, network addresses, or
  absolute filesystem paths
- **WHEN** the value is recursively scanned
- **THEN** each supported sensitive value produces a specific privacy issue

→ test: app/backend/tests/test_evidence_abx_privacy.py::test_privacy_scanner_rejects_adversarial_corpus

## Requirement: Long numeric identifiers are rejected only in identity-bearing fields
A number or numeric string with magnitude at least 1,000,000 SHALL be rejected when its normalized JSON
key contains the token `account`, `id`, `msisdn`, `phone`, `subject`, or `user`. The same rule SHALL recurse
through lists stored under that key. Large numbers under unrelated keys are not classified as identifiers.

### Scenario: sensitive containers are scanned recursively at the numeric boundary
- **GIVEN** a list under `userIds` and a numeric value under `accountNumber`
- **WHEN** values below and at the 1,000,000 boundary are scanned
- **THEN** only the values at or above the boundary produce `numeric_identifier` issues

→ test: app/backend/tests/test_evidence_abx_privacy.py::test_privacy_scanner_rejects_long_numeric_values_in_sensitive_containers

## Requirement: Narrow suppressions prevent generated evidence identifiers from looking like phone numbers
The phone detector SHALL ignore complete and embedded SHA-256 digests and digest-backed Trialmark ids. A
40- or 64-character lowercase hexadecimal value SHALL be suppressed as a phone number only under the
exact normalized key `git_commit`; the same value in free text remains subject to scanning. Suppression of
a digest SHALL NOT hide a real phone number elsewhere in the same text.

### Scenario: SHA-256 and digest-backed ids are not phone numbers
- **GIVEN** a bundle id, a generated run id, or text containing a labelled or bare SHA-256 digest
- **WHEN** the value is scanned
- **THEN** digit runs inside the generated identifier do not produce a phone-number issue

→ test: app/backend/tests/test_evidence_abx_privacy.py::test_privacy_scanner_ignores_embedded_digests_in_scanned_text

### Scenario: git commit suppression is scoped to the git_commit field
- **GIVEN** the same valid hexadecimal commit in `git_commit` and in an unrelated free-text field
- **WHEN** both values are scanned
- **THEN** only the `git_commit` value receives the commit-specific phone suppression

→ test: app/backend/tests/test_evidence_abx_privacy.py::test_privacy_scanner_ignores_valid_git_commit_field_as_phone_number

### Scenario: a real phone beside a digest is still rejected
- **GIVEN** text containing both a SHA-256 digest and an international phone number
- **WHEN** the text is scanned
- **THEN** the digest is ignored but the phone number produces a privacy issue

→ test: app/backend/tests/test_evidence_abx_privacy.py::test_privacy_scanner_still_reports_a_phone_number_beside_a_digest

## Requirement: Structural notation and empty placeholders remain usable
Null, empty-string, empty-list, and empty-object values under secret-bearing keys SHALL be allowed. Relative
paths, otherwise non-sensitive URLs, invalid IP lookalikes, and non-identity large numbers SHALL remain
allowed. An absolute-path
match SHALL be suppressed only for the exact normalized key `json_pointer`, because JSON Pointer syntax
begins with `/` but does not name a filesystem path.

### Scenario: bounded non-sensitive values do not create privacy findings
- **GIVEN** empty secret placeholders, a JSON Pointer, relative paths, a non-sensitive URL, and invalid
  address lookalikes
- **WHEN** the document is recursively scanned
- **THEN** the scanner returns no privacy issues

→ test: app/backend/tests/test_evidence_abx_privacy.py::test_privacy_scanner_ignores_bounded_non_sensitive_values

## Requirement: ZIP platform metadata is outside the privacy claim
Privacy scanning covers ABX member content, not central-directory-only ZIP platform fields. Under the
accepted F-T-06-15 boundary, `version-made-by`, `internal_attr`, and `external_attr` are unauthenticated and
MUST NOT be interpreted by downstream consumers as trusted file-type, owner, permission, or privacy
metadata. The container path and content checks remain authoritative.

### Scenario: central-only external attributes do not affect a privacy claim
- **GIVEN** a valid bundle whose central-directory `external_attr` is changed without changing member bytes
- **WHEN** the bundle is verified
- **THEN** the change neither invalidates the bundle nor creates a trusted file-type assertion

→ test: app/backend/tests/test_evidence_abx_zip_transport.py::test_verify_bundle_accepts_central_directory_external_attr_change
