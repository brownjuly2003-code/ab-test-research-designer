# Capability: ABX bundle container

<!-- Durable spec: it outlives the run. One capability per file; MyFlow injects the requirements a task
     references into the WorkOrder and the review pack. Format is OpenSpec-compatible. -->

## Requirement: A readable ABX uses the supported, reproducible ZIP encodings
The verifier SHALL accept members written with ZIP `Stored` or `Deflate`. It SHALL accept a data
descriptor, including its Zip64 form, only when its CRC and sizes agree with the central directory and it
ends exactly at the next record boundary. Consistent classic and Zip64 end records are valid. Deflate-level
hints, the data-descriptor flag, and the UTF-8 filename flag are supported transport semantics.

### Scenario: a writer may use data descriptors
- **GIVEN** a bundle whose member CRC and sizes are carried in data descriptors
- **WHEN** the bundle is verified
- **THEN** the transport is accepted when every descriptor agrees with the central directory

→ test: app/backend/tests/test_evidence_abx_zip_transport.py::test_verify_bundle_accepts_data_descriptors

### Scenario: a writer may use consistent Zip64 end records
- **GIVEN** a bundle with a Zip64 end record and locator that describe the same central directory
- **WHEN** the bundle is verified
- **THEN** the transport is accepted without changing its logical bundle identity

→ test: app/backend/tests/test_evidence_abx_zip_transport.py::test_verify_bundle_accepts_zip64_end_records

## Requirement: Member records and the archive trailer contain no unclaimed bytes
The physical walk SHALL start at byte zero, traverse contiguous local member records, meet the central
directory immediately after the final member, and consume the complete classic or Zip64 trailer. A prefix,
a gap, an out-of-bounds record, an inconsistent data descriptor or end record, or bytes after EOCD SHALL
fail integrity with `archive_trailing_bytes`. The code name is retained for compatibility even when the
unclaimed bytes occur before or between records.

### Scenario: bytes before the first member are rejected
- **GIVEN** an otherwise valid bundle with a prefix before its first local header
- **WHEN** the bundle is verified
- **THEN** integrity fails with `archive_trailing_bytes`

→ test: app/backend/tests/test_evidence_abx_zip_transport.py::test_verify_bundle_rejects_prefix_bytes

### Scenario: bytes between member records are rejected
- **GIVEN** an otherwise valid bundle with a gap between two local records
- **WHEN** the bundle is verified
- **THEN** integrity fails with `archive_trailing_bytes` on the member after the gap

→ test: app/backend/tests/test_evidence_abx_zip_transport.py::test_verify_bundle_rejects_gap_between_member_records

### Scenario: bytes after EOCD are rejected
- **GIVEN** an otherwise valid bundle with bytes appended after its end-of-central-directory record
- **WHEN** the bundle is verified
- **THEN** integrity fails with `archive_trailing_bytes`

→ test: app/backend/tests/test_evidence_abx_zip_transport.py::test_verify_bundle_rejects_bytes_after_eocd

## Requirement: Local and central records agree on authenticated transport fields
Each local header SHALL agree with the corresponding central-directory entry on extraction version,
flags, compression method, timestamp, CRC and sizes where carried, filename bytes, and the physical local
record offset. A mismatch in a local header SHALL produce `local_header_mismatch`; a central entry whose
authenticated fields or local offset disagree SHALL produce `central_directory_mismatch`. A mismatched
descriptor or an out-of-bounds record SHALL produce `archive_trailing_bytes`.

### Scenario: a changed local header is rejected
- **GIVEN** an archive whose central directory is unchanged but a local header field is changed
- **WHEN** the bundle is verified
- **THEN** integrity fails with `local_header_mismatch`

→ test: app/backend/tests/test_evidence_abx_zip_transport.py::test_verify_bundle_rejects_local_header_mismatch

### Scenario: a changed central local-header offset is rejected
- **GIVEN** an archive whose central entry points one byte away from its member's physical local record
- **WHEN** the bundle is verified
- **THEN** integrity fails with `central_directory_mismatch` on that member

→ test: app/backend/tests/test_evidence_abx_t09_deferred.py::test_tampered_cd_local_header_offset_is_reported_on_that_member

## Requirement: ZIP comments and non-canonical extra fields carry no evidence
Archive comments, entry comments, and central-only extra fields SHALL be rejected with
`entry_extra_field`. A local extra field SHALL also be rejected, except for the exact Zip64 size payload
needed by a Zip64 local record. These bytes are not represented in the ABX manifest and cannot be allowed
as an unauthenticated side channel.

### Scenario: an archive comment is rejected
- **GIVEN** a valid bundle with an otherwise harmless ZIP archive comment
- **WHEN** the bundle is verified
- **THEN** integrity fails only with `entry_extra_field`

→ test: app/backend/tests/test_evidence_abx_zip_transport.py::test_verify_bundle_rejects_archive_comment

### Scenario: a central-only extra field is rejected
- **GIVEN** a valid bundle with an extra field added only to a central-directory entry
- **WHEN** the bundle is verified
- **THEN** integrity fails with `entry_extra_field`

→ test: app/backend/tests/test_evidence_abx_zip_transport.py::test_verify_bundle_rejects_central_only_entry_extra_field

## Requirement: Names, features, and expansion stay inside fixed safety bounds
The preflight SHALL enforce the following rejection codes and causes before reading member content:

- `member_count_exceeded` when the archive contains more than 512 members;
- `duplicate_member` when an exact member name occurs more than once;
- `unsafe_member_path` for an empty, NUL-containing, backslash-containing, absolute, drive-qualified,
  directory, dot-segment, or otherwise non-canonical relative POSIX path;
- `normalized_name_collision` when distinct names collide after Unicode NFC normalization and case-folding;
- `member_size_exceeded` when one expanded member exceeds 16 MiB;
- `compression_ratio_exceeded` when a non-empty member has zero compressed bytes or expands by more than
  100:1;
- `encrypted_member` when the ZIP encryption bit is set;
- `unsupported_member_flags` when any flag outside encryption, Deflate hints, data descriptor, and UTF-8
  filename semantics is set;
- `unsupported_compression` when a member is neither Stored nor Deflate; and
- `total_size_exceeded` when the sum of expanded member sizes exceeds 64 MiB.

### Scenario: the manifest counts toward the member limit
- **GIVEN** a logical run whose artifacts plus `manifest.json` would exceed 512 members
- **WHEN** the run is materialized as ABX
- **THEN** materialization is refused for exceeding the member count

→ test: app/backend/tests/test_evidence_run_bundle.py::test_materializer_counts_manifest_against_member_limit

### Scenario: unsafe and unlisted paths are rejected
- **GIVEN** a packed bundle with an added traversal path or an unlisted member
- **WHEN** the bundle is verified
- **THEN** integrity fails with `unsafe_member_path` or `unlisted_member`, respectively

→ test: app/backend/tests/test_abx_cli.py::test_verifier_rejects_unsafe_and_unlisted_members

### Scenario: unsupported general-purpose flags have a specific cause
- **GIVEN** a member marked as compressed-patched data or strong encryption
- **WHEN** the bundle is verified
- **THEN** integrity fails with `unsupported_member_flags`, not a generic unreadable-member error

→ test: app/backend/tests/test_evidence_abx_zip_transport.py::test_verify_bundle_rejects_unsupported_general_purpose_flags

## Requirement: Central-directory-only platform metadata is not authenticated
`version-made-by`, `internal_attr`, `external_attr`, and equivalent central-directory-only platform metadata
have no matching source of truth in a local record. The verifier SHALL ignore differences in those fields
so that correct foreign ZIP writers interoperate. This is the accepted F-T-06-15 boundary: downstream
consumers MUST NOT use those values, including Unix file-type or symlink bits in `external_attr`, as trusted
evidence. Member path rules remain authoritative.

### Scenario: external file-type bits do not become authenticated evidence
- **GIVEN** an otherwise valid bundle whose central-only `external_attr` is changed to Unix symlink bits
- **WHEN** the bundle is verified
- **THEN** the bundle remains valid and no `special_member` conclusion is drawn

→ test: app/backend/tests/test_evidence_abx_zip_transport.py::test_verify_bundle_accepts_central_directory_external_attr_change
