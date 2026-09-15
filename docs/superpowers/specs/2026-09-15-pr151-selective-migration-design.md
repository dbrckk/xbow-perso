# PR #151 Selective Migration Design

## Goal

Recover the still-useful governance, provenance, queue-integrity, disaster-recovery, reporting-governance, and control-plane ideas from PR #151 without merging its stale 317-commit history or replacing the hardening/observer/incident stack already landed on `main` through #181.

PR #151 remains a source of behavior and tests, not a branch to merge.

## Decision

Use a selective forward migration from current `main`.

Do not rebase, merge, or replay PR #151 wholesale. For each capability, compare the old implementation with the current `main`, write tests against the desired current contract, then implement only the minimum compatible behavior on a fresh branch derived from `main`.

The migration is split into four independently reviewable blocks. Each block must pass the full repository CI before the next block starts.

## Global constraints

- Preserve the fail-closed authorization and execution model already present on `main`.
- Do not add attack techniques, exploit logic, payload generation, scanner expansion, credential attacks, denial-of-service behavior, or autonomous target expansion.
- New operational endpoints remain read-only unless they are existing explicit operator actions.
- Never expose secrets, raw worker errors, scanner payloads, third-party target contents, or worker identities through aggregate observability APIs.
- Do not duplicate the observer runtime, incident lifecycle, rolling telemetry, error-budget burn, or domain incident features already merged through #181.
- Prefer existing `main` abstractions over PR #151 versions when responsibilities overlap.
- Keep SQLite and Redis queue behavior semantically aligned where both are supported.
- Keep human approval separate from automated report readiness and submission gating.
- Every block uses tests first, focused commits, and a full CI gate before merge.

## Block 1 — Evidence-backed validation and policy-bound job provenance

### Purpose

Make validation progression depend on independent validation that has attached evidence, and bind governed queued work to the campaign policy state that authorized it.

### Capabilities to migrate

- `validation_state` tracks both observed independent validation and evidence-backed independent validation.
- Finding consensus exposes `none`, `single_evidence_backed_validator`, and `quorum`.
- Finding resolution requires evidence-backed independent validation.
- Report readiness consumes the stronger validation signal.
- Deterministic `job-provenance-v1` fingerprints the security-relevant campaign policy state.
- Governed job kinds carry provenance metadata when enqueued.
- Workers verify provenance before processing governed work and reject missing/stale provenance by default.
- Optional legacy unprovenanced-job compatibility is explicit, disabled by default, and surfaced by deployment preflight.
- Read-only provenance status may be exposed without returning job payloads.

### Adaptation rules

Current `main` already contains newer observer/incident safety work. Provenance verification must remain isolated from observer fencing and incident persistence; it is an admission check for work, not an incident-store concern.

The migration should reuse current campaign, queue, worker, and deployment-preflight interfaces rather than copying PR #151 files unchanged.

### Tests

Cover evidence attachment requirements, self-validation rejection, provenance determinism, policy mutation rejection, missing provenance rejection, explicit legacy mode, and all governed job kinds.

## Block 2 — Queue transition integrity and recovery assessment

### Purpose

Make every job-state transition independently auditable and make post-restore reconciliation observable without mutating queue state.

### Capabilities to migrate

- Append-only hash-linked transition events for job creation, claim, retry/requeue, completion, failure, cancellation, and lease recovery.
- Enforce the allowed lifecycle: create→queued, queued→running/cancelled, running→queued/completed/failed/cancelled.
- Verify sequence, status continuity, previous hash, event hash, and final status consistency.
- Support the same audit semantics for SQLite and Redis queue backends.
- Add redacted read-only job and campaign transition-audit views.
- Add queue recovery assessment that detects stale or malformed leases, invalid retry state, exhausted queued retry budgets, and invalid transition journals.
- Recovery assessment remains read-only and never requeues, recreates, clears leases, or starts workers.

### Adaptation rules

Do not use queue transition events as a second incident lifecycle. Queue integrity feeds operational metrics and may generate incident signals through the already-landed observer/incident pipeline.

### Tests

Cover normal lifecycle, retries, cancellation, lease recovery, sequence gaps, impossible transitions, hash tampering, final-status mismatch, Redis/SQLite parity, and zero-mutation recovery assessment.

## Block 3 — Recovery attestation and reporting governance

### Purpose

Bind disaster-recovery readiness and report approval to verifiable evidence without adding automation that bypasses operators.

### Recovery capabilities

- Read-only recovery readiness decision: `READY`, `REVIEW`, or `BLOCK`.
- Decision considers deployment preflight, queue recovery assessment, campaign/worker/queue audit integrity, and signed recovery attestation.
- `recovery-attestation-v1` signs canonical aggregate verification metadata with the configured audit HMAC key.
- Attestation excludes targets, payloads, secrets, and backup contents.
- Verification detects unsupported schema, digest mismatch, signature mismatch, unsafe files, and missing signing material.
- Recovery readiness snapshots may be persisted for trend analysis, but must not auto-start workers.

### Reporting capabilities

- Report provenance manifest ties a finding to finding, validation, evidence, and artifact observations.
- Reporting-governance fingerprint binds readiness, provenance, and quality-gate state.
- Report quality grades remain advisory; human approval is still required.
- Approval basis includes report bytes plus current provenance/governance fingerprints.
- Approval becomes stale when artifact, approval basis, provenance, or reporting governance changes.
- Generated report artifacts expose freshness/staleness without automatic submission.

### Adaptation rules

Keep the existing report-review and submission surfaces on `main`; strengthen their contracts rather than introducing parallel APIs with overlapping ownership.

### Tests

Cover signed-attestation round trips and tamper detection, recovery `READY/REVIEW/BLOCK`, report provenance determinism, governance fingerprint changes, stale approval reasons, artifact freshness, and human-approval preservation.

## Block 4 — Unified control-plane health and SLO projection

### Purpose

Provide one read-only operational projection that consumes the existing observer/incident telemetry plus the new governance/queue/recovery signals.

### Capabilities to migrate or adapt

- Control-plane health score across governance, queue integrity, validation, recovery, storage/durability, and reporting.
- Explicit hard blockers and reason codes.
- Persistent control-plane health snapshots and trend detection.
- Platform SLO projection for availability, queue integrity, job reliability, recovery readiness, and reporting/outbox health.
- Historical windows may expose 1h/24h/7d coverage and burn information when data quality is sufficient.
- Operations dashboard aggregates metrics, recovery, queue integrity, reporting integrity, alerts, health, and SLOs.

### Conflict policy with current `main`

`main` already contains:

- worker watchdog and readiness integration,
- operational SLO classifier,
- rolling 5m/1h telemetry,
- multi-window error-budget burn,
- incident engine and persistent lifecycle,
- observer leader lease/fencing/resilience/deadline/heartbeat/runtime metrics/self-SLO,
- independent workload/control-plane/observability incident domains.

Therefore PR #151's SLO and health code must not replace those modules. The migrated control-plane projection should consume or adapt existing outputs where possible. Any duplicate calculation must be removed or folded into a single source of truth.

In particular:

- existing `operational_slo.py`, `rolling_telemetry.py`, and `error_budget.py` remain authoritative for observer/workload reliability telemetry;
- the new control-plane health model is an aggregate governance projection, not a replacement SLO engine;
- control-plane degradation should become an input to the existing control-plane incident domain instead of spawning a second incident system;
- `/api/metrics` remains aggregate-only;
- UI work happens only after these backend contracts stabilize.

### Tests

Cover weighted scoring, hard caps, history/trends, aggregation with current observer health, no duplicate incident creation, SLO data-quality handling, and redaction guarantees.

## Migration order and merge strategy

1. Branch each implementation block from the latest green `main`.
2. Write focused failing tests for the block's desired current contract.
3. Port behavior from #151 selectively, adapting to current interfaces.
4. Run focused tests, then full backend tests, Ruff, compileall, dependency audit, build, security, and supply-chain workflows.
5. Merge the block into `main` only when fully green.
6. Start the next block from the newly merged `main`.
7. After all four blocks land and full CI is green, close #151 as superseded by the selective migration PRs.

Do not stack the new migration PRs on old branches; every integration boundary ultimately targets `main`.

## Deliberately excluded from direct replay

- Old `main.py` monolithic edits that conflict with current routes or incident APIs.
- PR #151 metrics code that duplicates current observer/rolling/error-budget telemetry.
- Any automatic worker resume or automatic queue mutation during recovery.
- Any direct scanner capability expansion.
- Any UI work before the backend contracts above are stable.
- Historical commits whose only purpose was intermediate refactoring or fixes already superseded on current `main`.

## Completion criteria

The migration is complete when:

- all four blocks are merged to `main`;
- full CI is green after the final merge;
- governed jobs fail closed on stale/missing provenance unless explicit legacy mode is enabled;
- finding resolution/report readiness use evidence-backed independent validation;
- queue transitions are tamper-evident for supported queue backends;
- recovery assessment and attestation are read-only and verifiable;
- report approval is bound to provenance/governance state and becomes stale when that state changes;
- control-plane health integrates with, rather than duplicates, the existing observer/incident/SLO stack;
- PR #151 is closed as superseded rather than merged.
