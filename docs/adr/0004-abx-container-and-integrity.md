# ADR 0004: ABX container and integrity model

- Status: Accepted for v0.1
- Date: 2026-08-21
- Scope: protocol and evidence portability
- Superseded in part by ADR 0005.

## Context

Evidence must remain inspectable after the original UI, database connection or
vendor disappears. A bundle therefore needs portable files, stable identities,
offline verification and explicit provenance. It must not imply that checksums
prove statistical validity or author identity.

Relevant prior art:

- [RFC 8785](https://www.rfc-editor.org/rfc/rfc8785.html) defines deterministic
  JSON canonicalization for hashing;
- [JSON Schema 2020-12](https://json-schema.org/draft/2020-12) provides the
  validation dialect;
- [RFC 8493 BagIt](https://www.rfc-editor.org/info/rfc8493/) demonstrates
  manifest-based completeness and checksum verification;
- [RO-Crate](https://www.researchobject.org/ro-crate/specification/1.3/)
  demonstrates rich research-object metadata;
- [DSSE](https://github.com/secure-systems-lab/dsse) separates signatures from
  payload semantics and key management.

## Decision

`.abx` v0.1 is a ZIP-compatible transport with a normative logical manifest.
The ZIP byte stream is not the bundle identity because compression metadata can
vary. `bundle_id` is `sha256:...` over the RFC 8785 canonical bytes of the
manifest core, excluding `bundle_id` and signatures. Every listed artifact has
its own SHA-256 digest and byte size.

Normative JSON uses JSON Schema Draft 2020-12, UTF-8, I-JSON-compatible values,
no duplicate keys, no NaN/Infinity and no timestamps outside UTC RFC 3339.
Protocol YAML is an optional authoring artifact; the canonical Protocol JSON is
the hashed source of truth.

The v0.1 container includes structured protocol, run, source, query, finding,
estimate and decision artifacts plus an optional self-contained HTML report.
Raw user-level rows, secrets, DSNs and prompt contents are forbidden.

The verifier:

1. reads the central directory without extracting;
2. rejects absolute paths, `..`, directory entries (filename trailing `/`,
   reported as `unsafe_member_path`), duplicate normalized names and configured
   file/count/size/compression-ratio limits. Central-directory entry-type
   metadata (`external_attr` and ZIP file-type bits) is unauthenticated and is
   not a basis for rejection; consumers extracting with a third-party unzip
   must not honour those bits;
3. validates manifest syntax with a trusted local schema catalog;
4. streams every listed member through SHA-256 and checks size;
5. rejects unlisted or missing members except the manifest itself;
6. validates each structured artifact and all cross-references;
7. applies privacy/secret policy and emits separate integrity, conformance,
   lineage and policy verdicts. Binding states for `unbound_bindings`:
   - `absent`: the path is listed and accepted.
   - `ambiguous` and `unlocated`: the path is listed and rejected as
     `lineage/unbound_reference`.
   - `present` with a digest that does not match: rejected as
     `lineage/unbound_reference` and not listed.
   - `present` with a matching digest: the definition is bound; the path is
     accepted and not listed.
   - `null` / `not_checked`: lineage was not evaluated.
   An empty `unbound_bindings` list does not mean every definition is bound.

How the physical-layout scan authenticates the stored CD offset, and what
happens when no stored offset can be located, is defined in
TRIALMARK_ARCHITECTURE.md §7.4; it is not restated here.

Embedded schema snapshots are archival evidence, not trusted validators. The
verifier chooses a built-in schema by version and checks the embedded schema
digest against its registry.

Cryptographic signatures are deferred until a threat model and trust-root/key
management ADR exist. The current workspace HMAC is not reused: a shared secret
cannot provide open third-party verification. A later signature profile may
wrap the exact manifest bytes in DSSE.

## Trust statement

ABX v0.1 provides tamper evidence, schema conformance and traceable claims. It
does not prove:

- that the source data were truthful;
- that the analysis design was causally valid;
- that the named author controlled a trusted identity;
- that an archive was never copied or withheld.

These remain separate verifier results and human review responsibilities.
`unbound_bindings` binding states are defined in verifier step 7; they are
not restated here.

## Rejected alternatives

- **Hash the ZIP bytes:** couples identity to compression and platform metadata.
- **Hash authoring YAML:** parsers, aliases and formatting make it ambiguous.
- **BagIt conformance:** useful integrity model, but its opaque payload does not
  define EvidenceOS domain semantics.
- **RO-Crate as the core format:** useful future export mapping, but JSON-LD and
  open vocabularies make a stricter v0.1 verifier harder.
- **Database dump:** not portable, reviewable or privacy-minimal.
- **HMAC-only signing:** verifier would need the shared secret.

## Compatibility

- Patch versions may add optional fields and artifact roles.
- Minor versions may add schemas while preserving all previous verifier rules.
- Major versions may break structure and require an explicit migration tool.
- A verifier must fail closed on unknown required capabilities and may inspect,
  but not claim conformance for, a future major version.
