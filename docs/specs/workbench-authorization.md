# Capability: Workbench decision authorization

<!-- Durable spec: it outlives the run. One capability per file; MyFlow injects the requirements a task
     references into the WorkOrder and the review pack. Format is OpenSpec-compatible. -->

## Requirement: A human decision or finding override is attributed to the authenticated principal, never to the request body
The system SHALL derive the recorded `actor_ref` of a workbench decision or finding override from the
principal established by write authentication, and SHALL NOT accept an actor identity supplied by the
caller. When no API keys are configured the service runs in open mode and SHALL still produce a principal,
attributed to `local-operator`, so that every recorded action names an actor.

### Scenario: the recorded actor comes from the principal in open mode
- **GIVEN** a service with no API keys configured and a completed evidence run
- **WHEN** a client records a human decision on that run
- **THEN** the stored decision names `local-operator` as its `actor_ref`

### Scenario: an actor identity in the request body is rejected
- **GIVEN** a completed evidence run
- **WHEN** a client posts a decision or an override whose body carries an `actor_ref` field
- **THEN** the request is rejected with HTTP 422 and no decision or override is recorded

## Requirement: A principal whose role is outside the frozen approval policy cannot decide
The system SHALL compare the principal's role against `protocol.decision.approval_policy.roles` frozen into
the run's protocol, and SHALL refuse the write when the role is not listed. The refusal SHALL be
distinguishable by clients from a conflict with the run's state and from a malformed request: it SHALL use
HTTP 403 and the error code `role_not_permitted`.

A principal that declares no role at all is not refused: an undeclared role resolves to the frozen policy's
first approval role. Only a principal that declares a role outside the policy is refused.

### Scenario: a role outside the approval policy is refused with 403
- **GIVEN** a completed evidence run whose frozen approval policy lists only the role `analyst`
- **WHEN** a principal whose role is `impostor` records a decision or overrides a finding on that run
- **THEN** the response is HTTP 403, its error code is `role_not_permitted`, and the run is unchanged

### Scenario: a permitted role still succeeds
- **GIVEN** a completed evidence run whose frozen approval policy lists the principal's role
- **WHEN** that principal records a human decision on the run
- **THEN** the decision is recorded and the response carries the updated run view

### Scenario: a principal that declares no role is still admitted
- **GIVEN** a service in open mode, whose `local-operator` principal declares no approval role
- **WHEN** that principal records a human decision on a completed evidence run
- **THEN** the decision is recorded under the frozen policy's first approval role

## Requirement: A recorded decision names where its role came from
The system SHALL record `decided_by.role_source` on every human decision, with exactly one of three values,
so that a reader of the bundle can tell a role the system verified from a role the caller merely claimed:

- `credential` -- the authenticated API key carries the role. This is the only source the service verifies.
- `asserted` -- the caller stated the role about itself (the CLI's `--role`). Nothing verifies the claim.
- `policy_default` -- no role was declared at all, and the frozen policy's first approval role applied.

The field SHALL be optional in `decision.schema.json`, so that decisions recorded before it existed remain
valid, and a verifier SHALL NOT infer a source for a record that omits it. The rendered report SHALL show
the source alongside the actor and role.

### Scenario: a role carried by an issued key is recorded as a credential
- **GIVEN** an issued API key whose stored role is listed in the run's frozen approval policy
- **WHEN** its holder records a human decision
- **THEN** the decision records that role with `role_source: credential`

### Scenario: a role named on the command line is recorded as asserted
- **GIVEN** a `trialmark decide --role <role>` invocation naming a role the frozen policy lists
- **WHEN** the decision is recorded
- **THEN** the decision records that role with `role_source: asserted`, even when it equals the policy default

### Scenario: no declared role is recorded as the policy default
- **GIVEN** a principal that declares no approval role
- **WHEN** it records a human decision
- **THEN** the decision records the policy's first approval role with `role_source: policy_default`

### Scenario: a role outside the policy is refused whatever its source
- **GIVEN** a role that the run's frozen approval policy does not list
- **WHEN** it is presented by an issued key or by `--role`
- **THEN** the write is refused with `role_not_permitted` -- HTTP 403 over the API, exit status 1 from the CLI

## Requirement: A policy that wants more approvals than one call records is refused
Recording a decision writes exactly one approval, the decider's own. When the run's frozen
`approval_policy.minimum_approvals` is greater than one, the system SHALL refuse to record the decision
rather than write one approval against a policy that demands several: an approved decision carrying half
the signatures its policy requires would misstate what happened. The refusal SHALL use the error code
`approval_quorum_unmet`, and HTTP 409 over the API -- the caller is permitted, and the frozen policy is what
cannot be satisfied.

### Scenario: a two-approval policy is refused, not half-satisfied
- **GIVEN** a completed analysis run whose frozen policy sets `minimum_approvals: 2`
- **WHEN** a permitted principal records a human decision on it
- **THEN** the response is HTTP 409 with error code `approval_quorum_unmet`, and no decision run is created

### Scenario: a single-approval policy is unaffected
- **GIVEN** a completed analysis run whose frozen policy sets `minimum_approvals: 1`
- **WHEN** a permitted principal records a human decision on it
- **THEN** the decision is recorded with one approval, as before
