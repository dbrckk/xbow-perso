# PR #151 Block 1 Validation & Provenance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate evidence-backed validation and deterministic policy-bound job provenance from PR #151 onto the current green `main` without changing offensive capability or duplicating observer/incident responsibilities.

**Architecture:** Strengthen validation semantics at the observation-graph layer, then propagate that stronger signal into consensus, resolution, and report readiness. Add a focused `job_provenance.py` admission module that fingerprints security-relevant campaign policy, attach provenance at every governed enqueue site, and verify it once at worker admission before any governed job executes. Compatibility for historical unprovenanced jobs stays explicit, disabled by default, and visible through deployment preflight.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, SQLite-backed `JobQueue`/`Storage`, pytest, Ruff, existing GitHub Actions CI/security/supply-chain workflows.

**Spec:** `docs/superpowers/specs/2026-09-15-pr151-selective-migration-design.md`

## Global Constraints

- Preserve the fail-closed authorization and execution model already present on `main`.
- Do not add attack techniques, exploit logic, payload generation, scanner expansion, credential attacks, denial-of-service behavior, or autonomous target expansion.
- New operational endpoints remain read-only unless they are existing explicit operator actions.
- Never expose secrets, raw worker errors, scanner payloads, third-party target contents, or worker identities through aggregate observability APIs.
- Do not duplicate the observer runtime, incident lifecycle, rolling telemetry, error-budget burn, or domain incident features already merged through #181.
- Prefer existing `main` abstractions over PR #151 versions when responsibilities overlap.
- Keep human approval separate from automated report readiness and submission gating.
- `job-provenance-v1` is strict by default; `XBOW_ALLOW_LEGACY_UNPROVENANCED_JOBS` is the only compatibility escape hatch and defaults to `false`.
- Governed job kinds are exactly: `strix_scan`, `nuclei_scan`, `recon_task`, `browser_flow`, `independent_validation`, `report`.
- Every task uses tests first, focused commits, and no changes to observer fencing or incident persistence.

---

## File Structure

### Create

- `backend/app/job_provenance.py` — deterministic policy snapshot/fingerprint, provenance attachment, verification, strict requirement helpers, governed-job registry.
- `backend/tests/test_job_provenance.py` — unit/API-contract tests for provenance determinism, mismatch detection, duplicate injection, redacted route registration.

### Modify

- `backend/app/validation_state.py` — add evidence-backed independent validation state without removing observed-validation compatibility helpers.
- `backend/app/finding_consensus.py` — derive consensus levels from evidence-backed validators.
- `backend/app/report_readiness.py` — consume evidence-backed validation and expose consensus level while preserving human-approval semantics.
- `backend/app/main.py` — attach provenance to direct API enqueue paths, require evidence-backed validation for resolution, expose redacted provenance status, advertise capability.
- `backend/app/orchestrator.py` — attach provenance to planner-created scan/recon/browser/validation/report jobs.
- `backend/app/worker_service.py` — verify governed-job provenance once before execution; allow legacy jobs only behind explicit flag.
- `backend/app/deployment_preflight.py` — validate and surface legacy-provenance compatibility mode without revealing values.
- `backend/tests/test_validation_state.py` — evidence attachment and mixed-state coverage.
- `backend/tests/test_finding_consensus.py` — `none` / `single_evidence_backed_validator` / `quorum` coverage.
- `backend/tests/test_report_readiness.py` — observed-but-unevidenced validation must remain blocked.
- `backend/tests/test_deployment_preflight.py` — strict/default/legacy/invalid-boolean behavior.
- `backend/tests/test_worker_concurrency.py` — stale policy, missing provenance, explicit legacy compatibility.
- `backend/tests/test_orchestrator.py` — all planner-generated governed jobs carry correct provenance and scanner engine kind is bound correctly.
- `backend/tests/test_api_idempotency.py` and/or existing API integration tests — direct API enqueue paths remain deterministic with provenance.

---

### Task 1: Evidence-backed validation state

**Files:**
- Modify: `backend/app/validation_state.py:1-60`
- Modify: `backend/tests/test_validation_state.py:1-130`

**Interfaces:**
- Consumes: `ObservationGraph.by_kind(kind)` and observation `parent_ids`, `source`, `value`, `id`.
- Produces: `ValidationState.evidence_backed_independent_finding_ids`, `ValidationState.unevidenced_finding_ids`, `ValidationState.all_evidence_backed_independently`, `evidence_backed_independent_finding_ids(graph) -> set[str]`, `has_evidence_backed_independent_validation(graph, finding_id) -> bool`.
- Preserves: `observed_independent_finding_ids()` and `has_observed_independent_validation()` for callers that still intentionally reason about observation rather than evidence sufficiency.

- [ ] **Step 1: Add failing tests for attached evidence semantics**

Add imports and tests equivalent to:

```python
from app.validation_state import (
    evidence_backed_independent_finding_ids,
    has_evidence_backed_independent_validation,
)


def test_observed_validation_without_child_evidence_is_not_evidence_backed():
    graph = _graph()

    state = analyze_validation_state(graph)

    assert state.observed_independent_finding_ids == {"finding:f1"}
    assert state.evidence_backed_independent_finding_ids == frozenset()
    assert state.unevidenced_finding_ids == {"finding:f1"}
    assert has_evidence_backed_independent_validation(graph, "finding:f1") is False


def test_evidence_must_be_child_of_independent_observed_validation():
    graph = _graph()
    graph.add(
        Observation(
            id="evidence:e1",
            kind="evidence",
            value="artifact-reference",
            source="validator",
            parent_ids=("validation:v1",),
        )
    )

    state = analyze_validation_state(graph)

    assert evidence_backed_independent_finding_ids(graph) == {"finding:f1"}
    assert state.unevidenced_finding_ids == frozenset()
    assert state.all_evidence_backed_independently is True
```

Also add a regression where evidence attached directly to the finding, or to a self-validation node, does **not** count as evidence-backed independent validation.

- [ ] **Step 2: Run the focused tests and confirm failure**

Run:

```bash
PYTHONPATH=backend python -m pytest backend/tests/test_validation_state.py -q
```

Expected: new tests fail because the new fields/helpers do not exist.

- [ ] **Step 3: Implement the minimum evidence-backed state**

Extend `ValidationState` and `analyze_validation_state()` with the child-evidence relationship:

```python
@dataclass(frozen=True)
class ValidationState:
    finding_ids: frozenset[str]
    attempted_finding_ids: frozenset[str]
    observed_independent_finding_ids: frozenset[str]
    evidence_backed_independent_finding_ids: frozenset[str]

    @property
    def unevidenced_finding_ids(self) -> frozenset[str]:
        return (
            self.observed_independent_finding_ids
            - self.evidence_backed_independent_finding_ids
        )

    @property
    def all_evidence_backed_independently(self) -> bool:
        return bool(self.finding_ids) and (
            self.finding_ids == self.evidence_backed_independent_finding_ids
        )
```

Build an `evidence_parent_ids` set from `graph.by_kind("evidence")`. Only add a finding to `evidence_backed_independent` when the validation is `observed`, its source differs from the finding source, and the validation observation ID appears in `evidence_parent_ids`.

Add:

```python
def evidence_backed_independent_finding_ids(graph: Any) -> set[str]:
    return set(analyze_validation_state(graph).evidence_backed_independent_finding_ids)


def has_evidence_backed_independent_validation(graph: Any, finding_id: str) -> bool:
    return (
        finding_id
        in analyze_validation_state(graph).evidence_backed_independent_finding_ids
    )
```

- [ ] **Step 4: Run validation-state tests**

Run:

```bash
PYTHONPATH=backend python -m pytest backend/tests/test_validation_state.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 1**

```bash
git add backend/app/validation_state.py backend/tests/test_validation_state.py
git commit -m "feat: require evidence-backed validation state"
```

---

### Task 2: Consensus and report-readiness semantics

**Files:**
- Modify: `backend/app/finding_consensus.py:1-105`
- Modify: `backend/app/report_readiness.py:1-155`
- Modify: `backend/tests/test_finding_consensus.py:1-80`
- Modify: `backend/tests/test_report_readiness.py:1-180`

**Interfaces:**
- Consumes: Task 1 evidence-backed validation state and existing observation graph.
- Produces: `FindingConsensus.evidence_backed_validator_count`, `FindingConsensus.consensus_level`, `ReportReadiness.evidence_backed_independent_validation`, `ReportReadiness.consensus_level`.
- Consensus values are exactly `none`, `single_evidence_backed_validator`, `quorum`.

- [ ] **Step 1: Add failing consensus tests**

Add assertions for the single-evidence-backed case:

```python
result = build_finding_consensus(graph)[0]
assert result.independent_validator_count == 1
assert result.evidence_backed_validator_count == 1
assert result.consensus_level == "single_evidence_backed_validator"
assert result.corroborated is True
```

Add a quorum test with two independent observed validation nodes, each with its own evidence child and distinct validator sources:

```python
assert result.evidence_backed_validator_count == 2
assert result.consensus_level == "quorum"
```

Add an observed-but-unevidenced case:

```python
assert result.independent_validator_count == 1
assert result.evidence_backed_validator_count == 0
assert result.consensus_level == "none"
assert result.corroborated is False
```

- [ ] **Step 2: Add failing report-readiness test for observed-but-unevidenced validation**

Construct a confirmed finding with an independent `validation` observation but no evidence child:

```python
item = build_report_readiness([_finding("f1", "confirmed")], graph)[0]

assert item.independent_validation_observed is True
assert item.evidence_backed_independent_validation is False
assert item.ready_for_human_review is False
assert "missing_evidence_backed_independent_validation" in item.blockers
```

Also assert a complete evidence-backed case exposes:

```python
assert item.evidence_backed_independent_validation is True
assert item.consensus_level == "single_evidence_backed_validator"
```

- [ ] **Step 3: Run focused tests and confirm failure**

```bash
PYTHONPATH=backend python -m pytest \
  backend/tests/test_finding_consensus.py \
  backend/tests/test_report_readiness.py -q
```

Expected: FAIL on missing fields/semantics.

- [ ] **Step 4: Implement evidence-backed consensus**

In `build_finding_consensus()`, map evidence to each independent validation separately instead of treating any evidence anywhere as sufficient:

```python
evidence_by_validation = {
    validation.id: [
        item
        for item in children.get(validation.id, [])
        if item.kind == "evidence"
    ]
    for validation in independent_validations
}

evidence_backed_validator_sources = {
    validation.source
    for validation in independent_validations
    if evidence_by_validation.get(validation.id)
}
```

Derive:

```python
if len(evidence_backed_validator_sources) >= 2:
    consensus_level = "quorum"
elif evidence_backed_validator_sources:
    consensus_level = "single_evidence_backed_validator"
else:
    consensus_level = "none"
```

`corroborated` must be `bool(evidence_backed_validator_sources)`. Preserve deterministic sorting and expose summary counts for `quorum` and `single_evidence_backed_validator`.

- [ ] **Step 5: Implement stronger report readiness**

Import `build_finding_consensus`, read Task 1 state, and use evidence-backed validation for the 0.30 validation contribution:

```python
evidence_backed = (
    graph_id in validation.evidence_backed_independent_finding_ids
)
consensus = consensus_by_id.get(finding_id)
consensus_level = str(consensus.consensus_level if consensus else "none")

if independent and not evidence_backed:
    blockers.append("missing_evidence_backed_independent_validation")
```

Keep `independent_validation_observed` as a separate diagnostic field. `ready_for_human_review` and `submission_ready` stay advisory/human-gated; this task does not add automatic approval or submission.

- [ ] **Step 6: Run focused tests**

```bash
PYTHONPATH=backend python -m pytest \
  backend/tests/test_finding_consensus.py \
  backend/tests/test_report_readiness.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit Task 2**

```bash
git add \
  backend/app/finding_consensus.py \
  backend/app/report_readiness.py \
  backend/tests/test_finding_consensus.py \
  backend/tests/test_report_readiness.py
git commit -m "feat: strengthen validation consensus and readiness"
```

---

### Task 3: Deterministic job-provenance module

**Files:**
- Create: `backend/app/job_provenance.py`
- Create: `backend/tests/test_job_provenance.py`

**Interfaces:**
- Produces: `PROVENANCE_SCHEMA`, `JobProvenanceError`, `stable_policy_snapshot()`, `policy_snapshot_fingerprint()`, `build_job_provenance()`, `attach_job_provenance()`, `verify_job_provenance()`, `require_job_provenance()`, `GOVERNED_JOB_KINDS`, `provenance_required_for_job_kind()`.
- Policy snapshot binds campaign ID, target URL/host, authorization reference, sorted allow/deny scope, request-rate limit, automated scanning flag, and all prohibited-action flags.
- Provenance is metadata only; it does not authorize work by itself and does not replace existing policy receipts.

- [ ] **Step 1: Write the provenance tests before the module exists**

Create `backend/tests/test_job_provenance.py` covering:

```python
def test_policy_fingerprint_is_deterministic_and_order_stable(): ...

def test_policy_fingerprint_changes_when_governance_changes(): ...

def test_attached_provenance_verifies_against_current_campaign(): ...

def test_stale_policy_fingerprint_fails_closed(): ...

def test_wrong_job_kind_is_rejected(): ...

def test_missing_provenance_is_rejected_by_strict_verifier(): ...

def test_duplicate_provenance_injection_is_rejected(): ...
```

For stale policy, mutate `campaign.target.rules.max_requests_per_second` after the payload is built and assert both `policy_fingerprint_mismatch` and `request_rate_limit_mismatch` appear.

- [ ] **Step 2: Confirm the new tests fail**

```bash
PYTHONPATH=backend python -m pytest backend/tests/test_job_provenance.py -q
```

Expected: import/module failure.

- [ ] **Step 3: Implement canonical policy snapshot and fingerprint**

Create `backend/app/job_provenance.py` with:

```python
PROVENANCE_SCHEMA = "job-provenance-v1"
GOVERNED_JOB_KINDS = frozenset(
    {
        "strix_scan",
        "nuclei_scan",
        "recon_task",
        "browser_flow",
        "independent_validation",
        "report",
    }
)
```

Canonicalize with `json.dumps(..., sort_keys=True, separators=(",", ":"), ensure_ascii=False)` and SHA-256. Sort allow/deny lists before hashing.

- [ ] **Step 4: Implement attachment and verification**

`attach_job_provenance()` must reject preexisting `_provenance`. `verify_job_provenance()` returns a redacted structure:

```python
{
    "valid": bool,
    "reasons": list[str],
    "policy_fingerprint": str | None,
    "expected_policy_fingerprint": str,
}
```

Verify schema, campaign ID, job kind, policy fingerprint, scope host, and declared request-rate limit. Never return the full policy snapshot or authorization reference.

- [ ] **Step 5: Run provenance tests**

```bash
PYTHONPATH=backend python -m pytest backend/tests/test_job_provenance.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 3**

```bash
git add backend/app/job_provenance.py backend/tests/test_job_provenance.py
git commit -m "feat: add policy-bound job provenance"
```

---

### Task 4: Attach provenance at every governed enqueue site

**Files:**
- Modify: `backend/app/main.py:210-270, 1070-1660` by function, not wholesale replay
- Modify: `backend/app/orchestrator.py:285-425`
- Modify: `backend/tests/test_orchestrator.py`
- Modify: `backend/tests/test_api_idempotency.py` and existing direct API tests only where required by the changed payload contract
- Extend: `backend/tests/test_job_provenance.py`

**Interfaces:**
- Consumes: Task 3 `attach_job_provenance()`.
- Produces: every newly enqueued governed job carries `_provenance` matching its actual queue `kind`.
- Scanner action is `automated_scan`; recon/browser action is `crawl`; independent validation action is `validate`; report action is `report`.

- [ ] **Step 1: Add failing tests for planner-created jobs**

In `test_orchestrator.py`, exercise `_enqueue_recon_tasks()` and `_enqueue_action()` and assert:

```python
assert job["payload"]["_provenance"]["schema"] == "job-provenance-v1"
assert job["payload"]["_provenance"]["job_kind"] == job["kind"]
assert job["payload"]["_provenance"]["campaign_id"] == campaign.id
```

Cover all six governed kinds. Add an explicit scanner regression with both `strix` and `nuclei` engines to prove each payload is built with the engine-specific queue kind rather than reusing a `strix_scan` provenance block for `nuclei_scan`.

- [ ] **Step 2: Add failing tests for direct API enqueue paths**

Cover direct campaign start, finding validation enqueue, explicit report enqueue, and completion-report enqueue. Assert `_provenance` exists while queue deduplication/idempotency still returns a single logical job for repeated equivalent requests.

- [ ] **Step 3: Run the focused enqueue tests and confirm failure**

```bash
PYTHONPATH=backend python -m pytest \
  backend/tests/test_orchestrator.py \
  backend/tests/test_api_idempotency.py \
  backend/tests/test_job_provenance.py -q
```

Expected: new provenance assertions fail.

- [ ] **Step 4: Make `sanitized_scan_payload()` job-kind aware**

Change the signature to:

```python
def sanitized_scan_payload(
    campaign: Campaign,
    receipt: dict[str, Any],
    *,
    job_kind: str = "strix_scan",
) -> dict[str, Any]:
```

Keep transient receipt fields out of the deterministic payload, then call:

```python
return attach_job_provenance(
    payload,
    campaign,
    job_kind=job_kind,
    action="automated_scan",
)
```

- [ ] **Step 5: Attach provenance in `main.py` without copying PR #151 wholesale**

Use `attach_job_provenance()` for `independent_validation` and `report` enqueue calls. Keep all current #181 incident/observer imports/routes untouched. Replace `_has_observed_independent_validation()` only in the finding-resolution path with an evidence-backed equivalent from Task 1.

- [ ] **Step 6: Attach provenance in `orchestrator.py`**

Wrap browser, recon, validation, and report payloads. Build scanner payload inside the per-engine loop:

```python
for engine in engines:
    kind = "strix_scan" if engine == "strix" else "nuclei_scan"
    payload = sanitized_scan_payload(
        campaign,
        stable_receipt,
        job_kind=kind,
    )
```

Do not change planner gates, budgets, scanner admission logic, or target expansion behavior.

- [ ] **Step 7: Run enqueue/idempotency tests**

```bash
PYTHONPATH=backend python -m pytest \
  backend/tests/test_orchestrator.py \
  backend/tests/test_api_idempotency.py \
  backend/tests/test_job_provenance.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit Task 4**

```bash
git add \
  backend/app/main.py \
  backend/app/orchestrator.py \
  backend/tests/test_orchestrator.py \
  backend/tests/test_api_idempotency.py \
  backend/tests/test_job_provenance.py
git commit -m "feat: bind governed jobs to campaign policy"
```

---

### Task 5: Fail-closed worker admission with explicit legacy compatibility

**Files:**
- Modify: `backend/app/worker_service.py:430-530`
- Modify: `backend/tests/test_worker_concurrency.py`

**Interfaces:**
- Consumes: Task 3 `provenance_required_for_job_kind()` and `require_job_provenance()`.
- Produces: `_verify_policy_bound_job(job, store) -> None` called once immediately after claim and before `_lease_heartbeat()`/dispatch.
- Compatibility env: `XBOW_ALLOW_LEGACY_UNPROVENANCED_JOBS`, default false.

- [ ] **Step 1: Add failing worker tests**

Add these focused scenarios:

```python
def test_worker_rejects_policy_bound_job_after_scope_policy_changes(...): ...

def test_worker_rejects_unprovenanced_governed_job_by_default(...): ...

def test_legacy_unprovenanced_job_requires_explicit_compatibility_flag(...): ...
```

For stale policy, enqueue a correctly provenanced report job, mutate the stored campaign `max_requests_per_second`, run `process_one()`, and assert the job ends `failed` with `policy_fingerprint_mismatch` in `last_error`.

For strict default, enqueue an unprovenanced governed report job with `max_attempts=1` and assert it fails once with `provenance_missing`.

For legacy mode, set `XBOW_ALLOW_LEGACY_UNPROVENANCED_JOBS=true`, enqueue the same legacy report shape, and assert it completes.

- [ ] **Step 2: Confirm the worker tests fail before implementation**

```bash
PYTHONPATH=backend python -m pytest \
  backend/tests/test_worker_concurrency.py -q
```

Expected: new strict-admission tests fail.

- [ ] **Step 3: Implement one centralized worker admission check**

Import:

```python
from .job_provenance import (
    JobProvenanceError,
    provenance_required_for_job_kind,
    require_job_provenance,
)
```

Add:

```python
def _legacy_unprovenanced_jobs_allowed() -> bool:
    return _worker_bool("XBOW_ALLOW_LEGACY_UNPROVENANCED_JOBS", False)


def _verify_policy_bound_job(job: dict, store: Storage) -> None:
    payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
    has_provenance = "_provenance" in payload
    required = provenance_required_for_job_kind(str(job.get("kind") or ""))

    if required and not has_provenance:
        if _legacy_unprovenanced_jobs_allowed():
            return
        raise WorkerPolicyError("job provenance rejected: provenance_missing")

    if not has_provenance:
        return

    campaign, _version = _campaign(store, job["campaign_id"])
    try:
        require_job_provenance(job, campaign)
    except JobProvenanceError as exc:
        raise WorkerPolicyError(str(exc)) from exc
```

Call `_verify_policy_bound_job(job, store)` as the first operation inside `process_one()`'s `try`, before `_lease_heartbeat()` and before any job-specific function.

Do not add duplicate provenance checks inside individual processors unless a test demonstrates a necessary defense-in-depth case; one admission point is the source of truth.

- [ ] **Step 4: Update existing worker fixtures to create provenanced governed jobs**

Any existing test that intentionally exercises a governed job beyond admission must now attach valid provenance. Do not enable the legacy flag globally in tests; legacy mode must remain opt-in per test.

- [ ] **Step 5: Run worker tests**

```bash
PYTHONPATH=backend python -m pytest backend/tests/test_worker_concurrency.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 5**

```bash
git add backend/app/worker_service.py backend/tests/test_worker_concurrency.py
git commit -m "feat: enforce provenance at worker admission"
```

---

### Task 6: Preflight, capability, resolution gate, and redacted provenance API

**Files:**
- Modify: `backend/app/deployment_preflight.py:1-165`
- Modify: `backend/app/main.py:210-370, validation route, job routes`
- Modify: `backend/tests/test_deployment_preflight.py:1-180`
- Extend: `backend/tests/test_job_provenance.py`
- Modify existing finding-validation API tests that assert the old observed-only resolution behavior.

**Interfaces:**
- Consumes: Tasks 1 and 3.
- Produces: preflight `job_provenance` object, capability `policy_bound_job_provenance`, redacted `GET /api/jobs/{job_id}/provenance`, evidence-backed finding-resolution gate.

- [ ] **Step 1: Add failing preflight tests**

Extend `_ENV_NAMES` with `XBOW_ALLOW_LEGACY_UNPROVENANCED_JOBS` and add:

```python
def test_preflight_reports_strict_job_provenance_by_default(monkeypatch):
    _clear(monkeypatch)
    result = build_deployment_preflight({"ok": True})
    assert result["job_provenance"] == {
        "strict_by_default": True,
        "legacy_unprovenanced_jobs_enabled": False,
        "configuration_valid": True,
        "schema": "job-provenance-v1",
    }


def test_preflight_warns_when_legacy_unprovenanced_jobs_are_enabled(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("XBOW_ALLOW_LEGACY_UNPROVENANCED_JOBS", "true")
    result = build_deployment_preflight({"ok": True})
    assert result["status"] == "warning"
    assert "legacy_unprovenanced_jobs_enabled" in {
        item["code"] for item in result["issues"]
    }


def test_preflight_rejects_invalid_legacy_provenance_boolean(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("XBOW_ALLOW_LEGACY_UNPROVENANCED_JOBS", "maybe")
    result = build_deployment_preflight({"ok": True})
    assert result["status"] == "error"
    assert "invalid_legacy_provenance_flag" in {
        item["code"] for item in result["issues"]
    }
```

- [ ] **Step 2: Add failing API contract tests**

Add OpenAPI registration assertion:

```python
assert "/api/jobs/{job_id}/provenance" in app.openapi()["paths"]
```

Add an API/unit route test showing the response includes only job ID, campaign ID, kind, verification summary, `read_only`, `payload_exposed=False`, and `fail_closed_capable=True`; assert the serialized response does **not** contain authorization reference, target URL, raw job payload, or secret values.

Update finding-resolution tests so an independently observed validation without child evidence receives HTTP 409 with the evidence-backed requirement, while the same validation with an evidence child may resolve.

- [ ] **Step 3: Run the focused tests and confirm failure**

```bash
PYTHONPATH=backend python -m pytest \
  backend/tests/test_deployment_preflight.py \
  backend/tests/test_job_provenance.py \
  backend/tests/test_validation_state.py \
  backend/tests/test_report_readiness.py -q
```

Expected: preflight/API/resolution assertions fail.

- [ ] **Step 4: Add strict boolean parsing to deployment preflight**

Add a non-throwing helper that returns `(value, valid)`:

```python
def _bool_env(name: str, default: bool = False) -> tuple[bool, bool]:
    raw = os.getenv(name)
    if raw is None:
        return default, True
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True, True
    if value in {"0", "false", "no", "off"}:
        return False, True
    return default, False
```

Invalid configuration is an `error`; explicit legacy mode is a `warning`. Return only booleans/schema, never the raw env value.

- [ ] **Step 5: Strengthen finding resolution**

In `main.py`, import `has_evidence_backed_independent_validation` and replace the resolution gate only:

```python
if not _has_evidence_backed_independent_validation(campaign_id, finding):
    raise HTTPException(
        status_code=409,
        detail=(
            "Finding requires evidence-backed independent validation "
            "before resolution"
        ),
    )
```

Do not remove observed-validation diagnostics used elsewhere unless a specific caller should also be strengthened and has a test proving it.

- [ ] **Step 6: Add the redacted provenance status route and capability flag**

Expose:

```python
@app.get("/api/jobs/{job_id}/provenance")
def get_job_provenance_status(job_id: str):
    job = queue().get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    campaign = assert_campaign_exists(str(job["campaign_id"]))
    verification = verify_job_provenance(job, campaign)
    return {
        "job_id": job["id"],
        "campaign_id": campaign.id,
        "job_kind": job["kind"],
        "provenance": verification,
        "read_only": True,
        "payload_exposed": False,
        "fail_closed_capable": True,
    }
```

Add `policy_bound_job_provenance: True` under `campaign_control` capabilities. Do not add Block 2 queue-audit or Block 3/4 capabilities early.

- [ ] **Step 7: Run focused Task 6 tests**

```bash
PYTHONPATH=backend python -m pytest \
  backend/tests/test_deployment_preflight.py \
  backend/tests/test_job_provenance.py \
  backend/tests/test_validation_state.py \
  backend/tests/test_finding_consensus.py \
  backend/tests/test_report_readiness.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit Task 6**

```bash
git add \
  backend/app/deployment_preflight.py \
  backend/app/main.py \
  backend/tests/test_deployment_preflight.py \
  backend/tests/test_job_provenance.py \
  backend/tests/test_validation_state.py \
  backend/tests/test_finding_consensus.py \
  backend/tests/test_report_readiness.py \
  backend/tests/test_api_idempotency.py
git commit -m "feat: expose strict provenance governance"
```

---

### Task 7: Block 1 integration verification and PR

**Files:**
- No production file changes unless a failing integration test reveals a defect.
- May modify tests only to fix incorrect fixtures that intentionally create governed jobs without provenance.

**Interfaces:**
- Verifies all Block 1 contracts together.
- No merge until full CI, security, and supply-chain workflows are green.

- [ ] **Step 1: Run the complete focused Block 1 suite**

```bash
PYTHONPATH=backend python -m pytest \
  backend/tests/test_validation_state.py \
  backend/tests/test_finding_consensus.py \
  backend/tests/test_report_readiness.py \
  backend/tests/test_job_provenance.py \
  backend/tests/test_deployment_preflight.py \
  backend/tests/test_orchestrator.py \
  backend/tests/test_worker_concurrency.py \
  backend/tests/test_api_idempotency.py -q
```

Expected: PASS.

- [ ] **Step 2: Run static checks**

```bash
python -m compileall -q backend/app backend/tests
python -m ruff check backend
```

Expected: PASS.

- [ ] **Step 3: Run the full backend test suite**

```bash
PYTHONPATH=backend python -m pytest backend/tests -q
```

Expected: all tests pass; the pre-Block-1 baseline was 1060 passing tests, so the final count must be greater than or equal to 1060 with zero failures.

- [ ] **Step 4: Check dependency integrity**

Using the same environment as repository CI:

```bash
python -m pip check
python -m pip_audit
```

Expected: PASS according to the repository's existing CI policy.

- [ ] **Step 5: Verify no duplicate observer/incident integration was introduced**

Search the diff and assert Block 1 does not create or modify alternate observer runtime, incident store/lifecycle, rolling telemetry, or error-budget modules. Provenance failures remain worker policy failures and flow through existing job failure/operational telemetry naturally.

- [ ] **Step 6: Open a PR from a fresh implementation branch targeting `main`**

Title:

```text
Governance: evidence-backed validation and policy-bound job provenance
```

Body must state:

```text
- selective migration from #151, not a history replay
- no offensive capability expansion
- evidence-backed validation required for finding resolution/report readiness
- six governed job kinds carry deterministic job-provenance-v1 metadata
- workers reject missing/stale provenance by default
- legacy compatibility is explicit and preflight-visible
- no observer/incident/SLO duplication
```

- [ ] **Step 7: Wait for PR workflows and inspect all conclusions**

Required green workflows: repository CI, security, supply-chain. Inspect pytest logs if any test fails; do not merge on partial green.

- [ ] **Step 8: Merge only after verified green CI**

After merge, verify `main` points to the resulting commit and the Block 1 PR is closed as merged. Do **not** start Block 2 from the old selective-migration planning branch; create Block 2 from the newly green `main`.

---

## Self-Review Results

### Spec coverage

- Evidence-backed independent validation: Tasks 1, 2, 6.
- Explicit consensus levels: Task 2.
- Deterministic `job-provenance-v1`: Task 3.
- Provenance on all six governed job kinds: Task 4.
- Worker fail-closed verification: Task 5.
- Explicit legacy compatibility and deployment visibility: Tasks 5, 6.
- Redacted provenance status: Task 6.
- No observer/incident duplication: Global Constraints and Task 7.
- Full CI gate before Block 2: Task 7.

### Placeholder scan

No `TBD`, `TODO`, deferred implementation, unspecified error handling, or generic “write tests” steps remain.

### Type and naming consistency

- Provenance schema: `job-provenance-v1` everywhere.
- Governed kinds: one shared `GOVERNED_JOB_KINDS` registry.
- Evidence-backed helpers and dataclass field use identical names across validation, consensus, readiness, API, and tests.
- Compatibility env name is consistently `XBOW_ALLOW_LEGACY_UNPROVENANCED_JOBS`.
- Block 1 intentionally does not introduce reporting-governance fingerprints, queue transition audit, recovery attestation, control-plane health, or SLO code; those remain Blocks 2–4.
