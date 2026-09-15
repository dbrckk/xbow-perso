# PR #151 Block 2 Queue Integrity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add tamper-evident queue transition journals for SQLite and Redis plus a read-only post-restore recovery assessment, without creating a second incident lifecycle or mutating queue state during assessment.

**Architecture:** A pure `queue_audit.py` module owns allowed transitions, canonical event hashing, and chain verification. SQLite and Redis queues append the same event schema at every durable state change and expose the same read-only audit methods. A pure `queue_recovery.py` analyzer consumes redacted job metadata plus audit results; API/CLI/metrics expose only aggregate or redacted results.

**Tech Stack:** Python 3.12, sqlite3, redis-py 8.1, FastAPI, pytest 8.4.1, Ruff.

**Spec:** `docs/superpowers/specs/2026-09-15-pr151-selective-migration-design.md`

## Global Constraints

- Preserve the fail-closed authorization and execution model already present on `main`.
- Do not add attack techniques, exploit logic, payload generation, scanner expansion, credential attacks, denial-of-service behavior, or autonomous target expansion.
- New operational endpoints remain read-only unless they are existing explicit operator actions.
- Never expose secrets, raw worker errors, scanner payloads, third-party target contents, or worker identities through aggregate observability APIs.
- Do not duplicate the observer runtime, incident lifecycle, rolling telemetry, error-budget burn, or domain incident features already merged through #181.
- Keep SQLite and Redis queue behavior semantically aligned.
- Queue recovery assessment must never requeue, recreate, clear leases, start workers, or otherwise mutate queue state.
- Every task follows RED → GREEN and ends with focused verification before the next task.

---

### Task 1: Canonical queue transition audit contract

**Files:**
- Create: `backend/app/queue_audit.py`
- Create: `backend/tests/test_queue_transition_audit.py`

**Interfaces:**
- Produces: `transition_allowed(from_status: str | None, to_status: str) -> bool`
- Produces: `build_transition_event(...)->dict[str, Any]`
- Produces: `verify_transition_events(events: list[dict[str, Any]]) -> dict[str, Any]`
- Event fields: `job_id`, `campaign_id`, `kind`, `seq`, `from_status`, `to_status`, `actor`, `reason`, `at`, `previous_hash`, `event_hash`.

- [ ] **Step 1: Write failing unit tests for valid and invalid chains**

```python
from app.queue_audit import build_transition_event, verify_transition_events


def test_transition_chain_accepts_valid_lifecycle():
    first = build_transition_event(
        job_id="job-1", campaign_id="campaign-1", kind="report", seq=1,
        from_status=None, to_status="queued", actor="queue",
        reason="job enqueued", at="t1", previous_hash=None,
    )
    second = build_transition_event(
        job_id="job-1", campaign_id="campaign-1", kind="report", seq=2,
        from_status="queued", to_status="running", actor="worker",
        reason="job claimed", at="t2", previous_hash=first["event_hash"],
    )
    result = verify_transition_events([first, second])
    assert result["valid"] is True
    assert result["final_status"] == "running"


def test_transition_chain_rejects_sequence_gap():
    first = build_transition_event(
        job_id="job-1", campaign_id="campaign-1", kind="report", seq=1,
        from_status=None, to_status="queued", actor="queue",
        reason="job enqueued", at="t1", previous_hash=None,
    )
    forged = dict(first, seq=3)
    result = verify_transition_events([first, forged])
    assert result["valid"] is False
    assert result["reason"] == "transition sequence gap"
```

- [ ] **Step 2: Run RED**

Run: `PYTHONPATH=backend pytest -q backend/tests/test_queue_transition_audit.py`
Expected: collection fails with `ModuleNotFoundError: app.queue_audit`.

- [ ] **Step 3: Implement the pure audit module**

Use exactly these allowed transitions:

```python
_ALLOWED_TRANSITIONS = {
    None: frozenset({"queued"}),
    "queued": frozenset({"running", "cancelled"}),
    "running": frozenset({"queued", "completed", "failed", "cancelled"}),
    "completed": frozenset(),
    "failed": frozenset(),
    "cancelled": frozenset(),
}
```

Canonicalize the event payload with:

```python
json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
```

and compute `event_hash = hashlib.sha256(canonical).hexdigest()`.

`verify_transition_events()` must reject sequence gaps, from/to discontinuity, invalid transitions, previous-hash discontinuity, and event-hash tampering; on success it returns `valid=True`, `checked`, `final_status`, and `head_hash`.

- [ ] **Step 4: Run GREEN**

Run: `PYTHONPATH=backend pytest -q backend/tests/test_queue_transition_audit.py`
Expected: PASS.

- [ ] **Step 5: Commit**

Commit: `feat: define tamper-evident queue transition audit`.

---

### Task 2: SQLite transition journal

**Files:**
- Modify: `backend/app/jobqueue.py`
- Extend: `backend/tests/test_queue_transition_audit.py`

**Interfaces:**
- Produces: `JobQueue.job_transitions(job_id) -> list[dict[str, Any]]`
- Produces: `JobQueue.verify_job_transitions(job_id) -> dict[str, Any]`
- Produces: `JobQueue.campaign_transition_audit(campaign_id) -> dict[str, Any]`

- [ ] **Step 1: Add failing SQLite lifecycle tests**

```python
def test_sqlite_queue_records_claim_and_completion_transitions(tmp_path):
    queue = JobQueue(str(tmp_path / "queue.sqlite3"))
    job = queue.enqueue("campaign-1", "report", {"campaign_id": "campaign-1"})
    queue.claim("worker-a")
    queue.finish(job["id"], "worker-a", True)
    events = queue.job_transitions(job["id"])
    assert [e["to_status"] for e in events] == ["queued", "running", "completed"]
    assert queue.verify_job_transitions(job["id"])["valid"] is True
```

Also cover retry/requeue, queued cancellation, owned cancellation, lease recovery, deleted event rows, and direct DB tampering.

- [ ] **Step 2: Run RED**

Run: `PYTHONPATH=backend pytest -q backend/tests/test_queue_transition_audit.py`
Expected: failures because `job_transitions` and journal storage do not exist.

- [ ] **Step 3: Add `job_transitions` table and transactional append helper**

Schema:

```sql
CREATE TABLE IF NOT EXISTS job_transitions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    campaign_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    seq INTEGER NOT NULL,
    from_status TEXT,
    to_status TEXT NOT NULL,
    actor TEXT NOT NULL,
    reason TEXT NOT NULL,
    at TEXT NOT NULL,
    previous_hash TEXT,
    event_hash TEXT NOT NULL,
    UNIQUE(job_id, seq)
)
```

Add `_append_transition(...)` and call it in the same SQLite transaction as the job mutation for enqueue, claim/claim_allowed/claim_kind, finish/requeue/fail, cancel_queued, cancel_owned, and expired-lease recovery.

Never put `last_error` or raw worker error content into `reason`; use generic reasons such as `job completed`, `job requeued after failure`, `job failed`, and `worker lease expired before completion`.

- [ ] **Step 4: Add verification/read APIs**

`verify_job_transitions()` must compare verified chain `final_status` with the current durable job status and fail with `audit final status does not match job status` on mismatch.

- [ ] **Step 5: Run GREEN**

Run: `PYTHONPATH=backend pytest -q backend/tests/test_queue_transition_audit.py backend/tests/test_worker_concurrency.py backend/tests/test_campaign_cancel.py`
Expected: PASS.

- [ ] **Step 6: Commit**

Commit: `feat: persist sqlite queue transition journal`.

---

### Task 3: Redis parity and atomicity guardrails

**Files:**
- Modify: `backend/app/redis_jobqueue.py`
- Extend: `backend/tests/test_queue_transition_audit.py`
- Extend existing Redis queue tests where needed.

**Interfaces:** Same public methods and event schema as `JobQueue`.

- [ ] **Step 1: Write Redis parity tests**

For a Redis queue, assert enqueue → claim → completion yields the same three `to_status` values and the same verification shape as SQLite. Cover retry/requeue, cancel, and expired lease recovery.

- [ ] **Step 2: Run RED**

Run with CI Redis available:
`PYTHONPATH=backend XBOW_REDIS_URL=redis://localhost:6379/15 pytest -q backend/tests/test_queue_transition_audit.py`
Expected: Redis-specific assertions fail because audit methods are absent.

- [ ] **Step 3: Implement Redis audit storage**

Use one Redis list per job (`<prefix>:audit:<job_id>`) containing canonical JSON events. `_append_transition()` derives seq/previous hash from the current list tail and rejects status discontinuity.

Integrate append calls only after a successful WATCH/MULTI state transition. If the durable state update did not win, do not append an event.

- [ ] **Step 4: Verify parity**

Run: `PYTHONPATH=backend XBOW_REDIS_URL=redis://localhost:6379/15 pytest -q backend/tests/test_queue_transition_audit.py backend/tests/test_worker_concurrency.py`
Expected: PASS.

- [ ] **Step 5: Commit**

Commit: `feat: mirror queue transition audit in redis`.

---

### Task 4: Read-only queue recovery assessment

**Files:**
- Create: `backend/app/queue_recovery.py`
- Create: `backend/tests/test_queue_recovery.py`
- Modify: `backend/app/jobqueue.py`
- Modify: `backend/app/redis_jobqueue.py`

**Interfaces:**
- Produces: `analyze_queue_recovery(jobs, *, lease_seconds, audit_results=None, now=None) -> dict[str, Any]`
- Produces: `JobQueue.recovery_assessment() -> dict[str, Any]`
- Produces: `RedisJobQueue.recovery_assessment() -> dict[str, Any]`

- [ ] **Step 1: Write RED tests for inconsistencies**

Cover `running_without_owner`, `running_without_claim_timestamp`, `invalid_claim_timestamp`, `expired_running_lease`, `non_running_job_has_lease_fields`, `invalid_retry_state`, `queued_retry_budget_exhausted`, and `transition_audit_invalid`.

Every result must include:

```python
assert result["read_only"] is True
assert result["automatic_requeue"] is False
assert result["automatic_job_creation"] is False
assert result["automatic_mutation"] is False
```

- [ ] **Step 2: Run RED**

Run: `PYTHONPATH=backend pytest -q backend/tests/test_queue_recovery.py`
Expected: collection fails with missing `app.queue_recovery`.

- [ ] **Step 3: Implement the pure analyzer**

Only inspect metadata: `id`, `status`, `attempts`, `max_attempts`, `claimed_by`, `claimed_at`. Do not accept job payload as an input requirement and never return payloads.

- [ ] **Step 4: Add queue adapters**

Each backend gathers only redacted metadata and calls its own `verify_job_transitions()` results into the analyzer. Add `storage: sqlite|redis` to the returned assessment.

- [ ] **Step 5: Run GREEN**

Run: `PYTHONPATH=backend pytest -q backend/tests/test_queue_recovery.py backend/tests/test_queue_transition_audit.py`
Expected: PASS.

- [ ] **Step 6: Commit**

Commit: `feat: add read-only queue recovery assessment`.

---

### Task 5: API, CLI, capabilities, and aggregate observability

**Files:**
- Modify: `backend/app/main.py`
- Modify: `backend/app/dr_cli.py`
- Modify: `backend/app/queue_backend.py`
- Modify: `backend/app/metrics.py`
- Modify: `backend/app/campaign_overview.py` only if the current overview lacks a queue-integrity summary.
- Extend: `backend/tests/test_queue_transition_audit.py`
- Extend: `backend/tests/test_queue_recovery.py`
- Extend: `backend/tests/test_dr_cli.py`
- Extend: `backend/tests/test_metrics.py`

**Interfaces:**
- GET `/api/jobs/{job_id}/transitions`
- GET `/api/campaigns/{campaign_id}/audit/queue-transitions`
- GET `/api/recovery/queue`
- CLI: `python -m app.dr_cli queue-check`

- [ ] **Step 1: Add RED route and CLI tests**

OpenAPI must contain all three read-only routes. Job transition responses may expose IDs, status transitions, actor class/reason/timestamps and hashes, but never job payload or `last_error`. Recovery endpoint must return the analyzer result verbatim/redacted and must not mutate jobs.

- [ ] **Step 2: Implement API/CLI using queue backend abstraction**

`queue-check` prints the assessment and exits non-zero when `safe_to_resume` is false. It must call only `recovery_assessment()`.

- [ ] **Step 3: Add aggregate metrics only**

Expose counts such as audited jobs, invalid audited jobs, and recovery issue counts. Do not include campaign IDs, job IDs, payloads, raw errors, or worker identities in `/api/metrics`.

- [ ] **Step 4: Run GREEN**

Run: `PYTHONPATH=backend pytest -q backend/tests/test_queue_transition_audit.py backend/tests/test_queue_recovery.py backend/tests/test_dr_cli.py backend/tests/test_metrics.py`
Expected: PASS.

- [ ] **Step 5: Commit**

Commit: `feat: expose queue integrity and recovery diagnostics`.

---

### Task 6: Block 2 integration gate

**Files:** No new production behavior unless verification reveals a real regression.

- [ ] **Step 1: Run static verification**

Run:
`python -m compileall -q backend/app backend/tests`
`ruff check backend/app backend/tests`
Expected: both pass.

- [ ] **Step 2: Run full backend suite**

Run:
`PYTHONPATH=backend XBOW_REDIS_URL=redis://localhost:6379/15 XBOW_TEST_POSTGRES_URL=postgresql://xbow:xbow-ci@localhost:5432/xbow pytest -q --strict-config --strict-markers backend/tests`
Expected: 0 failures.

- [ ] **Step 3: Run dependency and build gates**

Run `python -m pip check`, `pip-audit -r backend/requirements.txt`, frontend JS syntax checks, Docker Compose config, and Docker builds via repository CI.

- [ ] **Step 4: Scope review**

Confirm no changes add scanner/exploit capability, no recovery method mutates queue state, and no incident/observer lifecycle is duplicated.

- [ ] **Step 5: Open PR to `main`**

PR title: `Governance: tamper-evident queue integrity and read-only recovery assessment`.
Merge only after CI, Security, and Supply-chain are green on the PR head.
