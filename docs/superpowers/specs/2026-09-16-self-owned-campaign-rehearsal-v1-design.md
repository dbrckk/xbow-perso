# Self-Owned Campaign Rehearsal v1 — Design

Date: 2026-09-16
Status: Approved design, implementation not started
Repository: `dbrckk/xbow-perso`

## 1. Purpose

Add a deterministic, self-contained campaign rehearsal that exercises XBOW's existing safety, durability, provenance, cancellation, recovery, and evidence-handling behavior against a local controlled target.

The rehearsal is a verification harness, not a new scanner and not a new offensive capability. It must demonstrate that the current execution pipeline remains fail-closed under redirects, throttling, worker failures, crash windows, cancellation, secret handling, and policy drift.

## 2. Goals

The rehearsal must:

- run entirely against local/self-owned fixtures with no required Internet access;
- reuse real XBOW campaign, storage, queue, provenance, policy, validation, observation, outbox, and cancellation components wherever practical;
- produce deterministic pass/fail results for named safety and resilience invariants;
- detect duplicate execution or inconsistent durable state after recovery;
- prove that scope and policy changes invalidate stale queued work before execution;
- prove that sentinel secrets are absent from public/persisted evidence surfaces;
- be suitable for CI and repeatable locally;
- remain independent of HackerOne availability and never submit external reports.

## 3. Non-goals

v1 will not:

- run Nuclei, Strix, PentAGI, browser automation, or arbitrary shell commands against Internet targets;
- add exploit payloads, fuzzing, credential attacks, denial-of-service behavior, social engineering, or destructive testing;
- auto-confirm findings;
- test external DNS infrastructure;
- test real HackerOne programs;
- replace unit tests for queue/storage components;
- add a production API that can point the rehearsal at arbitrary hosts.

## 4. Architectural approach

### 4.1 Rehearsal coordinator

Create a focused module, tentatively `backend/app/self_owned_rehearsal.py`, responsible for orchestrating deterministic scenarios against isolated temporary storage and queue backends.

The coordinator receives explicit fixture dependencies rather than reading arbitrary external targets. It returns a structured `RehearsalReport` containing one result per invariant.

It must not own low-level policy, queue, provenance, or artifact logic. It calls existing production functions or narrow adapters around them so the rehearsal verifies the same code paths used by normal campaigns.

### 4.2 Local target fixture

Tests will run a local HTTP fixture bound only to loopback. The fixture exposes deterministic routes such as:

- `/ok` -> `200`;
- `/redirect-in-scope` -> redirect to another local in-scope path;
- `/redirect-out-of-scope` -> redirect target outside the declared fixture scope;
- `/throttle` -> deterministic `429`, optionally with a bounded `Retry-After` value;
- `/echo` -> reflects a controlled inert query value for validation tests;
- `/secret-echo` -> allows the harness to verify redaction behavior without storing the sentinel value.

No route performs destructive work. The fixture must not bind to a public interface.

### 4.3 Controlled name resolution

DNS/subdomain behavior will be modeled using an injectable resolver or deterministic host mapping in the test harness. It must not query public DNS.

The resolver supports:

- allowed subdomain -> loopback fixture;
- denied/out-of-scope subdomain -> policy rejection before network execution;
- unknown host -> deterministic resolution failure.

The rehearsal verifies policy behavior, not recursive DNS discovery.

### 4.4 Failure injection

Failure points are explicit test hooks around existing durable boundaries. They are available only to tests/rehearsal code, not as arbitrary production controls.

Required hooks:

- fail a worker after claim but before successful completion;
- simulate process interruption after queue enqueue but before the matching campaign audit event is reconciled;
- mutate campaign policy after a job has been created but before execution;
- cancel a campaign while queued work exists.

Failure injection must never bypass provenance verification, scope checks, or sandbox admission.

### 4.5 Rehearsal report

The report is deterministic and machine-readable:

```text
{
  "status": "pass" | "fail",
  "scenarios": [
    {
      "name": "scope_drift_blocks_execution",
      "status": "pass" | "fail",
      "reason": "...",
      "references": {
        "campaign_id": "...",
        "job_ids": ["..."],
        "event_types": ["..."]
      }
    }
  ],
  "external_network_used": false,
  "contains_secrets": false
}
```

References must identify durable records without embedding request bodies, secret values, authorization tokens, or raw environment values.

## 5. Scenario contract

### 5.1 Redirect enforcement

The rehearsal must show both behaviors:

1. A redirect whose destination remains within the declared local scope is handled only according to the existing component's redirect policy.
2. A redirect whose destination is outside scope is never followed into execution.

A pass requires that no out-of-scope HTTP request is observed by the fixture or transport spy.

### 5.2 Subdomain and resolver scope

An explicitly allowed fixture subdomain may resolve to loopback and proceed through the normal policy gate. A denied or undeclared subdomain must be rejected before target execution.

A pass requires zero requests to the denied host mapping.

### 5.3 HTTP 429 handling

A deterministic `429` must not cause an unbounded retry loop or exceed campaign request-rate constraints.

The rehearsal records the bounded outcome: deferred, failed, or retried only according to the existing job policy. v1 does not introduce a new generic retry algorithm solely for the rehearsal.

A pass requires a bounded request count and a durable terminal/deferred state consistent with current worker semantics.

### 5.4 Worker failure durability

Inject a worker failure after claim. The queue and campaign state must remain internally consistent and the job must not be falsely recorded as successful.

If the existing queue supports retry, retry count must remain within configured limits. If not, the failure must be durable and observable.

A pass requires no fabricated completion event and no duplicate successful execution.

### 5.5 Crash-window outbox recovery

Simulate interruption after enqueue and before the corresponding audit reconciliation step.

Use the existing outbox recovery diagnostics and local reconciliation flow. Recovery must not create a second equivalent job.

A pass requires exactly one durable job identity for the logical request and a reconciled local audit state.

### 5.6 Cancellation

Cancel a campaign with queued work. Existing queued jobs must be cancelled where supported, no new campaign work may be admitted afterward, and running work must not be represented as forcibly terminated when the queue cannot guarantee that.

A pass requires:

- campaign state `cancelled`;
- no newly admitted work after cancellation;
- queued work cancelled according to the queue backend contract;
- running-job reporting remains truthful.

### 5.7 Secret sentinel confinement

Use a unique sentinel string in a controlled secret-bearing input. Inspect the persistence surfaces created by the rehearsal:

- campaign events;
- public observation records;
- persisted validation/scanner-style evidence created by the harness;
- public rehearsal report;
- relevant job payload snapshots that are intended to be non-secret.

A pass requires the raw sentinel to be absent from every public or persistence surface that is not explicitly a secret vault.

The secret vault itself is outside this assertion because its purpose is to hold secrets; the rehearsal verifies that the value does not escape it.

### 5.8 Policy/scope drift provenance

Create a job from a campaign with valid provenance, then change the campaign scope or policy before execution.

Execution must revalidate provenance/policy binding and reject stale work before any target request occurs.

A pass requires:

- execution rejected fail-closed;
- zero target requests after drift;
- durable reason indicating provenance/policy mismatch;
- no success artifact for the stale job.

## 6. Data flow

For each scenario:

1. create isolated temporary storage, artifact root, and queue;
2. create the local fixture and explicit scope;
3. create the campaign through existing model/storage APIs;
4. enqueue or prepare work using existing production code paths;
5. inject only the scenario-specific controlled condition;
6. execute or reconcile using existing worker/control functions;
7. collect durable state from storage, queue, observations, artifacts, and campaign events;
8. evaluate scenario invariants in pure deterministic assertion code;
9. append a redacted scenario result to the report;
10. tear down the fixture and verify no external-network usage was observed.

Each scenario uses independent temporary state so one failure cannot contaminate another.

## 7. Component boundaries

### `self_owned_rehearsal.py`

Owns scenario coordination and result aggregation. Does not implement scanner logic, policy logic, retry logic, or secret storage.

### `rehearsal_fixture.py` or test fixture helpers

Owns loopback HTTP behavior, deterministic host mappings, request counters, and external-network assertions.

### Existing production modules

Reused without weakening their contracts:

- `main.py` for campaign state and policy-related public behavior;
- `job_provenance.py` for provenance generation/verification;
- `jobqueue.py` / queue backend for durable work state;
- `outbox_recovery.py` for crash-window reconciliation;
- `worker_service.py` and relevant worker functions for dispatch semantics;
- `validator.py` where validation behavior is under rehearsal;
- `observation_writer.py` / `observation_graph.py` for evidence records;
- `storage.py` / storage backend for artifacts and campaign persistence;
- `secret_vault.py` only as the approved secret storage boundary.

If implementation reveals that a production function cannot be called without broad side effects, add the narrowest injectable seam possible rather than duplicating its logic inside the rehearsal.

## 8. Safety invariants

The implementation must preserve all of the following:

- loopback-only target transport in CI;
- no public DNS lookups required;
- no arbitrary host input accepted by a production rehearsal endpoint;
- no destructive methods added for the rehearsal;
- no exploit execution;
- no bypass of policy/provenance checks;
- no automatic HackerOne submission;
- no raw secret value in report output;
- no relaxation of scanner sandbox requirements;
- no change to the rule that differential evidence cannot auto-confirm a finding.

A scenario fails closed on ambiguous state. Ambiguity is reported as failure, not silently treated as success.

## 9. External-network isolation

CI must make external-network usage observable and fail the rehearsal if an attempted target connection is not loopback or an explicitly injected in-memory transport.

Preferred order:

1. use dependency injection/transport spies so target traffic is fully controlled;
2. for the local HTTP fixture, assert every observed destination is loopback;
3. do not depend on firewall manipulation as the primary correctness mechanism.

The test suite may still access package registries during dependency installation outside the rehearsal itself; `external_network_used=false` refers to rehearsal target execution, not the entire CI job lifecycle.

## 10. Error handling

Each scenario catches expected injected failures and converts them into invariant evidence. Unexpected exceptions fail that scenario and preserve a sanitized exception class/reason without sensitive values.

The overall report is `fail` if any mandatory scenario fails.

A failed rehearsal must not mutate a normal operator campaign because all v1 scenarios use isolated temporary campaign state.

## 11. Testing strategy

Implementation follows TDD.

### Unit tests

Test report aggregation, result redaction, deterministic scenario evaluation, resolver mappings, and external-network guards as pure logic.

### Integration tests

Exercise the eight mandatory scenarios against real temporary storage/queue implementations already used by the backend tests.

Where both SQLite/local queue and Redis/Postgres paths exist in CI, the core invariants should be tested at least once on the default lightweight backend and critical durability/provenance invariants should reuse the existing backend integration coverage instead of duplicating an entire matrix in v1.

### CI acceptance

The branch is mergeable only when:

- all existing tests remain green;
- all rehearsal scenarios pass;
- the rehearsal records zero external target connections;
- the secret sentinel does not appear in persisted/public outputs;
- crash recovery yields one logical job, not duplicates;
- policy drift yields zero post-drift target requests;
- lint, compile, readiness, dependency audit, security, and supply-chain workflows remain green.

## 12. Determinism and idempotency

The harness must avoid wall-clock-sensitive assertions where possible. Retry/backoff tests use injectable clocks/sleep functions or bounded counters rather than real long waits.

Logical request identifiers and dedupe keys must be stable inside a scenario. Re-running a scenario from a fresh isolated state must produce the same pass/fail semantics even if generated campaign/job UUID values differ.

## 13. Observability

The rehearsal report should expose only the minimum diagnostics needed to locate a failure:

- scenario name;
- status;
- stable reason code;
- relevant job IDs;
- relevant campaign event types;
- bounded counters such as requests observed or jobs created.

It must not expose raw bodies, bearer tokens, TOTP values, secret sentinel values, environment secrets, or full external endpoint values.

## 14. Rollout

v1 lands as test/rehearsal infrastructure and does not enable a new production execution mode.

After merge, a later separately approved change may choose to expose a read-only operator summary of the most recent rehearsal result or require a passing rehearsal as part of a production release gate. That is explicitly outside this design.

## 15. Acceptance criteria

The design is complete when an implementation can demonstrate all of the following in CI:

- eight mandatory scenarios exist and pass independently;
- target execution is loopback/in-memory only;
- out-of-scope redirects and hosts receive zero requests;
- `429` handling is bounded;
- worker failure is durable and never appears as false success;
- crash recovery reconciles without duplicate logical work;
- cancellation blocks new work and accurately reports running work;
- sentinel secrets remain confined;
- post-creation policy/scope drift blocks stale execution before network activity;
- rehearsal output is redacted and deterministic;
- no offensive capability, exploit execution, or external submission behavior is added.
