# Self-Owned Campaign Rehearsal v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic CI rehearsal that proves XBOW's existing scope, provenance, queue durability, outbox recovery, cancellation, and secret-confinement controls using only loopback/in-memory target execution.

**Architecture:** Add a small production-side coordinator for redacted scenario results, plus test-only fixture/scenario modules that invoke the real XBOW code paths. Add one narrow dependency-injection seam to `safe_http_probe` so fixture hostnames can be routed to loopback without public DNS. No scanner, exploit, browser, PentAGI, submission, or production rehearsal endpoint is added.

**Tech Stack:** Python 3.12, pytest, stdlib `http.server` / `urllib.request`, SQLite `Storage` and `JobQueue`, existing XBOW models/workers, Ruff, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-16-self-owned-campaign-rehearsal-v1-design.md`

## Global Constraints

- Target execution in the rehearsal is loopback/in-memory only; no public target connection and no public DNS lookup is required.
- Do not run Nuclei, Strix, PentAGI, browser automation, arbitrary shell jobs, exploits, fuzzing, credential attacks, denial of service, social engineering, or destructive tests.
- Do not add a production API that accepts a rehearsal target.
- In-scope redirects remain non-followed; the rehearsal verifies current no-follow behavior rather than enabling redirect traversal.
- Out-of-scope redirects and denied/undeclared fixture hosts receive zero follow-up requests.
- `429` remains observational and bounded by current behavior; add no generic retry algorithm.
- Failure injection remains test-only and never bypasses scope/provenance/sandbox gates.
- Raw sentinel secrets must be absent from campaign events, public observations, persisted evidence, non-secret queue payloads, and the public rehearsal report.
- Differential evidence never auto-confirms a finding.
- Ambiguous outcomes fail closed.
- Unexpected errors are represented by stable exception-class reason codes only; never persist raw exception messages in the rehearsal report.
- v1 is test/rehearsal infrastructure only and does not enable external HackerOne submission or a new production execution mode.

## File Structure

- Create `backend/app/self_owned_rehearsal.py`: redacted result types, mandatory scenario set, report aggregation, raw-value checker.
- Create `backend/tests/rehearsal_fixture.py`: loopback HTTP server and explicit mapped opener with no DNS fallback.
- Create `backend/tests/rehearsal_scenarios.py`: the eight test-only scenario runners that call existing XBOW production functions.
- Create `backend/tests/test_rehearsal_fixture.py`: fixture/network-isolation unit tests.
- Create `backend/tests/test_self_owned_rehearsal.py`: coordinator plus aggregate rehearsal tests.
- Create `backend/tests/test_self_owned_rehearsal_http.py`: redirect, subdomain, and `429` tests.
- Create `backend/tests/test_self_owned_rehearsal_resilience.py`: worker-failure and outbox-crash tests.
- Create `backend/tests/test_self_owned_rehearsal_controls.py`: cancellation, policy-drift, and secret-confinement tests.
- Modify `backend/app/validator.py`: optional `opener` / `sleep_fn` dependency seams only; default production behavior is unchanged.
- Do not modify `.github/workflows/ci.yml` unless test discovery itself is proven broken; the existing workflow already runs all `backend/tests`.

---

### Task 1: Redacted rehearsal coordinator

**Files:**
- Create: `backend/app/self_owned_rehearsal.py`
- Create: `backend/tests/test_self_owned_rehearsal.py`

**Interfaces:**
- Produces `MANDATORY_SCENARIOS`, `ScenarioReferences`, `ScenarioResult`, `RehearsalReport`, `run_rehearsal(...)`, and `contains_raw_value(...)`.
- Consumes stdlib only.

- [ ] **Step 1: Write the failing coordinator tests**

```python
# backend/tests/test_self_owned_rehearsal.py
from app.self_owned_rehearsal import (
    MANDATORY_SCENARIOS,
    ScenarioReferences,
    ScenarioResult,
    contains_raw_value,
    run_rehearsal,
)


def _pass(name: str) -> ScenarioResult:
    return ScenarioResult(
        name=name,
        status="pass",
        reason="invariant_satisfied",
        references=ScenarioReferences(),
    )


def test_run_rehearsal_requires_all_mandatory_scenarios():
    scenarios = {name: (lambda name=name: _pass(name)) for name in MANDATORY_SCENARIOS}
    report = run_rehearsal(scenarios)
    assert report.status == "pass"
    assert [item.name for item in report.scenarios] == list(MANDATORY_SCENARIOS)
    assert report.external_network_used is False
    assert report.contains_secrets is False


def test_missing_scenario_fails_closed():
    scenarios = {name: (lambda name=name: _pass(name)) for name in MANDATORY_SCENARIOS[:-1]}
    report = run_rehearsal(scenarios)
    assert report.status == "fail"
    assert report.scenarios[-1].name == MANDATORY_SCENARIOS[-1]
    assert report.scenarios[-1].reason == "scenario_missing"


def test_unexpected_exception_message_is_not_exposed():
    marker = "SECRET-MUST-NOT-LEAK"
    scenarios = {name: (lambda name=name: _pass(name)) for name in MANDATORY_SCENARIOS}

    def explode():
        raise RuntimeError(marker)

    scenarios[MANDATORY_SCENARIOS[0]] = explode
    report = run_rehearsal(scenarios)
    assert report.scenarios[0].reason == "unexpected_RuntimeError"
    assert marker not in str(report)


def test_contains_raw_value_detects_nested_text_and_bytes():
    marker = "rehearsal-sentinel"
    assert contains_raw_value(marker, [{"nested": [b"xxrehearsal-sentinelxx"]}]) is True
    assert contains_raw_value(marker, [{"nested": ["[redacted]"]}]) is False
```

- [ ] **Step 2: Verify RED**

Run:
```bash
PYTHONPATH=backend pytest -q backend/tests/test_self_owned_rehearsal.py
```
Expected: import/collection failure because `app.self_owned_rehearsal` does not exist.

- [ ] **Step 3: Implement the minimal coordinator**

```python
# backend/app/self_owned_rehearsal.py
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Callable, Iterable, Literal, Mapping

MANDATORY_SCENARIOS = (
    "redirect_scope_enforcement",
    "subdomain_scope_enforcement",
    "http_429_bounded",
    "worker_failure_durability",
    "crash_window_outbox_recovery",
    "cancellation_enforcement",
    "secret_sentinel_confinement",
    "scope_drift_blocks_execution",
)


@dataclass(frozen=True)
class ScenarioReferences:
    campaign_id: str | None = None
    job_ids: tuple[str, ...] = ()
    event_types: tuple[str, ...] = ()
    counters: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class ScenarioResult:
    name: str
    status: Literal["pass", "fail"]
    reason: str
    references: ScenarioReferences = field(default_factory=ScenarioReferences)
    external_network_used: bool = False
    contains_secrets: bool = False


@dataclass(frozen=True)
class RehearsalReport:
    status: Literal["pass", "fail"]
    scenarios: tuple[ScenarioResult, ...]
    external_network_used: bool
    contains_secrets: bool


def contains_raw_value(value: str, surfaces: Iterable[object]) -> bool:
    if not value:
        return False
    needle = value.encode("utf-8")
    for surface in surfaces:
        encoded = surface if isinstance(surface, bytes) else json.dumps(
            surface, ensure_ascii=False, default=str
        ).encode("utf-8")
        if needle in encoded:
            return True
    return False


def run_rehearsal(
    scenarios: Mapping[str, Callable[[], ScenarioResult]],
) -> RehearsalReport:
    results: list[ScenarioResult] = []
    for name in MANDATORY_SCENARIOS:
        runner = scenarios.get(name)
        if runner is None:
            results.append(ScenarioResult(name=name, status="fail", reason="scenario_missing"))
            continue
        try:
            result = runner()
        except Exception as exc:
            result = ScenarioResult(
                name=name,
                status="fail",
                reason=f"unexpected_{exc.__class__.__name__}",
            )
        if result.name != name:
            result = ScenarioResult(name=name, status="fail", reason="scenario_name_mismatch")
        results.append(result)
    external = any(item.external_network_used for item in results)
    secrets = any(item.contains_secrets for item in results)
    failed = external or secrets or any(item.status != "pass" for item in results)
    return RehearsalReport(
        status="fail" if failed else "pass",
        scenarios=tuple(results),
        external_network_used=external,
        contains_secrets=secrets,
    )
```

- [ ] **Step 4: Verify GREEN and lint**

Run:
```bash
PYTHONPATH=backend pytest -q backend/tests/test_self_owned_rehearsal.py
ruff check backend/app/self_owned_rehearsal.py backend/tests/test_self_owned_rehearsal.py
```
Expected: tests PASS; Ruff prints `All checks passed!`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/self_owned_rehearsal.py backend/tests/test_self_owned_rehearsal.py
git commit -m "test(rehearsal): add redacted scenario coordinator"
```

---

### Task 2: Loopback-only target fixture

**Files:**
- Create: `backend/tests/rehearsal_fixture.py`
- Create: `backend/tests/test_rehearsal_fixture.py`

**Interfaces:**
- Produces `ExternalTargetAttempt`, `RequestRecord`, `LocalRehearsalServer`, and `MappedLoopbackOpener`.
- `MappedLoopbackOpener.open(request, timeout)` accepts only explicitly mapped fixture hostnames and connects only to `127.0.0.1` / `::1`.

- [ ] **Step 1: Write failing fixture tests**

```python
# backend/tests/test_rehearsal_fixture.py
from urllib.error import HTTPError
from urllib.request import Request

import pytest

from rehearsal_fixture import ExternalTargetAttempt, LocalRehearsalServer, MappedLoopbackOpener


def test_mapped_fixture_uses_loopback_and_preserves_fixture_host():
    with LocalRehearsalServer() as server:
        opener = MappedLoopbackOpener({"allowed.rehearsal.test": ("127.0.0.1", server.port)})
        with opener.open(Request("http://allowed.rehearsal.test/ok", method="GET"), timeout=1) as response:
            assert response.getcode() == 200
        assert server.requests[-1].host.startswith("allowed.rehearsal.test")
        assert server.requests[-1].path == "/ok"
        assert opener.blocked_hosts == []


def test_unmapped_host_is_rejected_before_network_fallback():
    with LocalRehearsalServer() as server:
        opener = MappedLoopbackOpener({"allowed.rehearsal.test": ("127.0.0.1", server.port)})
        with pytest.raises(ExternalTargetAttempt, match="unmapped_target"):
            opener.open(Request("http://outside.rehearsal.test/ok", method="GET"), timeout=1)
        assert opener.blocked_hosts == ["outside.rehearsal.test"]
        assert server.requests == []


def test_fixture_redirect_is_not_followed():
    with LocalRehearsalServer() as server:
        opener = MappedLoopbackOpener({"allowed.rehearsal.test": ("127.0.0.1", server.port)})
        with pytest.raises(HTTPError) as exc:
            opener.open(Request("http://allowed.rehearsal.test/redirect-in-scope", method="GET"), timeout=1)
        assert exc.value.code == 302
        assert [item.path for item in server.requests] == ["/redirect-in-scope"]
```

- [ ] **Step 2: Verify RED**

Run:
```bash
PYTHONPATH=backend:backend/tests pytest -q backend/tests/test_rehearsal_fixture.py
```
Expected: import failure because `rehearsal_fixture.py` does not exist.

- [ ] **Step 3: Implement deterministic routes and no-DNS mapped opener**

Implement `ThreadingHTTPServer(("127.0.0.1", 0), Handler)` with a daemon thread and these exact route semantics:

```python
STATIC_ROUTES = {
    "/ok": (200, {}, b"ok"),
    "/redirect-in-scope": (302, {"Location": "/ok"}, b""),
    "/redirect-out-of-scope": (302, {"Location": "http://outside.rehearsal.test/ok"}, b""),
    "/throttle": (429, {"Retry-After": "1"}, b"throttled"),
}
```

`/echo` and `/secret-echo` may reflect only the first query value in the response body. Request logging stores method, Host, and path only; never request bodies, Authorization, Cookie, or secret values. Override `log_message` to suppress stdout.

`MappedLoopbackOpener` must parse the original hostname, look it up in the explicit map before any network call, require mapped address in `{127.0.0.1, ::1}`, rewrite only the connection destination, preserve the original Host header, and use a local `_NoRedirect(HTTPRedirectHandler)` whose `redirect_request` returns `None`.

- [ ] **Step 4: Verify GREEN**

Run:
```bash
PYTHONPATH=backend:backend/tests pytest -q backend/tests/test_rehearsal_fixture.py
ruff check backend/tests/rehearsal_fixture.py backend/tests/test_rehearsal_fixture.py
```
Expected: all tests PASS and Ruff is clean.

- [ ] **Step 5: Commit**

```bash
git add backend/tests/rehearsal_fixture.py backend/tests/test_rehearsal_fixture.py
git commit -m "test(rehearsal): add loopback-only target fixture"
```

---

### Task 3: Validator injection seam and HTTP safety scenarios

**Files:**
- Modify: `backend/app/validator.py` in `safe_http_probe`
- Create: `backend/tests/rehearsal_scenarios.py`
- Create: `backend/tests/test_self_owned_rehearsal_http.py`

**Interfaces:**
- Changes signature to `safe_http_probe(campaign, finding, *, opener=None, sleep_fn=time.sleep) -> ProbeResult`.
- Produces test-only runners `run_redirect_scope_scenario(root, monkeypatch)`, `run_subdomain_scope_scenario(root, monkeypatch)`, and `run_http_429_scenario(root, monkeypatch)` returning `ScenarioResult`.
- Production call sites keep using `safe_http_probe(campaign, finding)` unchanged.

- [ ] **Step 1: Write failing scenario tests**

```python
# backend/tests/test_self_owned_rehearsal_http.py
from rehearsal_scenarios import (
    run_http_429_scenario,
    run_redirect_scope_scenario,
    run_subdomain_scope_scenario,
)


def test_redirect_scope_scenario(tmp_path, monkeypatch):
    result = run_redirect_scope_scenario(tmp_path, monkeypatch)
    assert result.status == "pass"
    assert result.reason == "redirects_observed_without_followup"
    assert result.external_network_used is False
    assert result.references.counters["requests_observed"] == 2


def test_subdomain_scope_scenario(tmp_path, monkeypatch):
    result = run_subdomain_scope_scenario(tmp_path, monkeypatch)
    assert result.status == "pass"
    assert result.reason == "denied_host_blocked_before_transport"
    assert result.references.counters["requests_observed"] == 1


def test_http_429_scenario(tmp_path, monkeypatch):
    result = run_http_429_scenario(tmp_path, monkeypatch)
    assert result.status == "pass"
    assert result.reason == "http_429_observed_once"
    assert result.references.counters["requests_observed"] == 1
```

- [ ] **Step 2: Verify RED**

Run:
```bash
PYTHONPATH=backend:backend/tests pytest -q backend/tests/test_self_owned_rehearsal_http.py
```
Expected: import failure because `rehearsal_scenarios.py` and its runners do not exist.

- [ ] **Step 3: Add the narrow validator seam**

In `safe_http_probe`, replace only the opener/sleep construction points:

```python
def safe_http_probe(campaign, finding, *, opener=None, sleep_fn=time.sleep) -> ProbeResult:
    # existing gates/scope checks remain unchanged
    request_opener = opener if opener is not None else build_opener(_NoRedirect())
    baseline = _request_get(request_opener, url, timeout=timeout, max_bytes=max_bytes)
    # existing redaction remains unchanged
    if differential_enabled and marker_url is not None:
        sleep_fn(1.0 / campaign.target.rules.max_requests_per_second)
        marker_result = _request_get(
            request_opener,
            marker_url,
            timeout=timeout,
            max_bytes=max_bytes,
        )
        # existing differential comparison remains unchanged
```

Do not add redirect, retry, resolver, or network environment flags.

- [ ] **Step 4: Implement the three HTTP scenario runners**

Use a campaign whose allowed hosts are `allowed.rehearsal.test` and `*.allowed.rehearsal.test`, with `denied.allowed.rehearsal.test` explicitly denied. Enable only `XBOW_ENABLE_HTTP_VALIDATION=true`; keep differential validation disabled for these scenarios.

Runner invariants:
- redirect runner performs one GET to `/redirect-in-scope` and one to `/redirect-out-of-scope`; both return observed `302`; exactly two fixture requests total; neither destination is followed;
- subdomain runner maps `api.allowed.rehearsal.test` to loopback and receives `200`, then passes a denied hostname to `safe_http_probe` and gets `status="blocked"` before opener use; exactly one fixture request total;
- `429` runner GETs `/throttle`, observes status `429`, performs exactly one request, and adds no retry.

Return only stable reason codes and counters; never URLs/bodies in `ScenarioReferences`.

- [ ] **Step 5: Verify GREEN plus existing validator regression**

Run:
```bash
PYTHONPATH=backend:backend/tests pytest -q \
  backend/tests/test_validator.py \
  backend/tests/test_self_owned_rehearsal_http.py
ruff check backend/app/validator.py backend/tests/rehearsal_scenarios.py backend/tests/test_self_owned_rehearsal_http.py
```
Expected: all selected tests PASS and Ruff is clean.

- [ ] **Step 6: Commit**

```bash
git add backend/app/validator.py backend/tests/rehearsal_scenarios.py backend/tests/test_self_owned_rehearsal_http.py
git commit -m "test(rehearsal): exercise local HTTP safety invariants"
```

---

### Task 4: Worker failure and lease-recovery scenario

**Files:**
- Modify: `backend/tests/rehearsal_scenarios.py`
- Create: `backend/tests/test_self_owned_rehearsal_resilience.py`

**Interfaces:**
- Produces `run_worker_failure_scenario(root, monkeypatch) -> ScenarioResult`.
- Consumes existing `JobQueue.enqueue`, `claim`, `recover_expired_leases`, `worker_service.process_one`, and `attach_job_provenance`.

- [ ] **Step 1: Write the failing scenario test**

```python
# backend/tests/test_self_owned_rehearsal_resilience.py
from rehearsal_scenarios import run_worker_failure_scenario


def test_worker_failure_scenario_is_durable_and_bounded(tmp_path, monkeypatch):
    result = run_worker_failure_scenario(tmp_path, monkeypatch)
    assert result.status == "pass"
    assert result.reason == "expired_lease_recovered_then_failed_at_attempt_limit"
    assert result.references.counters == {
        "attempts": 2,
        "successful_outcomes": 0,
    }
```

- [ ] **Step 2: Verify RED**

Run:
```bash
PYTHONPATH=backend:backend/tests pytest -q \
  backend/tests/test_self_owned_rehearsal_resilience.py::test_worker_failure_scenario_is_durable_and_bounded
```
Expected: import error for the missing runner.

- [ ] **Step 3: Implement the runner using the existing queue semantics**

The runner must:
1. create an isolated ready campaign, `Storage`, and `JobQueue` under `root`;
2. enqueue a provenance-bound `report` job with `max_attempts=2`;
3. claim it as `worker-crashed`;
4. update only that test queue row's `lease_expires_at` to one hour in the past;
5. call `queue.recover_expired_leases()` and assert it returns `1`;
6. monkeypatch `worker_service.process_report` to raise `RuntimeError("injected-rehearsal-failure")` and `advance_campaign` to stop;
7. call `process_one(queue, store, "worker-retry")`;
8. verify final status `failed`, attempts `2`, and zero `worker_outcome` events with `success=True` for the job.

The runner returns `pass` only when all invariants hold; otherwise return `fail` with one of these stable reasons: `lease_not_requeued`, `attempt_limit_mismatch`, `false_success_recorded`.

- [ ] **Step 4: Verify queue/worker regressions**

Run:
```bash
PYTHONPATH=backend:backend/tests pytest -q \
  backend/tests/test_self_owned_rehearsal_resilience.py \
  backend/tests/test_jobqueue.py \
  backend/tests/test_worker_watchdog.py
```
Expected: all selected tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/tests/rehearsal_scenarios.py backend/tests/test_self_owned_rehearsal_resilience.py
git commit -m "test(rehearsal): cover worker failure durability"
```

---

### Task 5: Crash-window outbox recovery scenario

**Files:**
- Modify: `backend/tests/rehearsal_scenarios.py`
- Modify: `backend/tests/test_self_owned_rehearsal_resilience.py`

**Interfaces:**
- Produces `run_outbox_recovery_scenario(root, monkeypatch) -> ScenarioResult`.
- Consumes `append_campaign_event`, `JobQueue.enqueue/get_by_dedupe`, and `main.reconcile_campaign_outbox_local`.

- [ ] **Step 1: Add the failing scenario test**

```python
from rehearsal_scenarios import run_outbox_recovery_scenario


def test_outbox_crash_window_reconciles_without_duplicate_job(tmp_path, monkeypatch):
    result = run_outbox_recovery_scenario(tmp_path, monkeypatch)
    assert result.status == "pass"
    assert result.reason == "audit_reconciled_without_job_recreation"
    assert result.references.counters == {
        "jobs_before": 1,
        "jobs_after": 1,
        "repaired_events": 1,
    }
```

- [ ] **Step 2: Verify RED**

Run:
```bash
PYTHONPATH=backend:backend/tests pytest -q \
  backend/tests/test_self_owned_rehearsal_resilience.py::test_outbox_crash_window_reconciles_without_duplicate_job
```
Expected: import error for the missing runner.

- [ ] **Step 3: Implement the crash-window runner**

Use the established `report_requested` / `report:generic:{request_id}` pattern from `backend/tests/test_outbox_chaos.py`:
- persist `report_requested` intent;
- enqueue exactly one `report` row with stable dedupe key;
- instantiate/reuse the queue after the simulated process-memory loss;
- call `main.reconcile_campaign_outbox_local(campaign.id)`;
- verify `repaired == 1`, `remaining == []`, `automatic_job_creation is False`, queue total remains `1`, dedupe lookup returns the same job ID, and exactly one `report_queued` event exists with `reconciled_locally=True`.

Also exercise the missing-job negative case inside the runner using a second isolated campaign: local reconciliation must report `job_missing`, repair `0`, and keep queue total `0`.

- [ ] **Step 4: Verify outbox regressions**

Run:
```bash
PYTHONPATH=backend:backend/tests pytest -q \
  backend/tests/test_self_owned_rehearsal_resilience.py \
  backend/tests/test_outbox_chaos.py
```
Expected: all selected tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/tests/rehearsal_scenarios.py backend/tests/test_self_owned_rehearsal_resilience.py
git commit -m "test(rehearsal): prove crash-safe outbox recovery"
```

---

### Task 6: Cancellation enforcement scenario

**Files:**
- Modify: `backend/tests/rehearsal_scenarios.py`
- Create: `backend/tests/test_self_owned_rehearsal_controls.py`

**Interfaces:**
- Produces `run_cancellation_scenario(root, monkeypatch) -> ScenarioResult`.
- Consumes existing `main.cancel_campaign`, queue status counts, and cancellation guards.

- [ ] **Step 1: Write the failing cancellation test**

```python
# backend/tests/test_self_owned_rehearsal_controls.py
from rehearsal_scenarios import run_cancellation_scenario


def test_cancellation_scenario_blocks_new_work_and_reports_running_truthfully(tmp_path, monkeypatch):
    result = run_cancellation_scenario(tmp_path, monkeypatch)
    assert result.status == "pass"
    assert result.reason == "queued_cancelled_running_reported_new_work_blocked"
    assert result.references.counters == {
        "queued_cancelled": 1,
        "running_jobs": 1,
        "post_cancel_admissions": 0,
    }
```

- [ ] **Step 2: Verify RED**

Run:
```bash
PYTHONPATH=backend:backend/tests pytest -q \
  backend/tests/test_self_owned_rehearsal_controls.py::test_cancellation_scenario_blocks_new_work_and_reports_running_truthfully
```
Expected: import error for the missing runner.

- [ ] **Step 3: Implement the cancellation runner**

Match the existing proven sequence in `test_campaign_cancel.py`:
1. configure `XBOW_DB_PATH` / `XBOW_ARTIFACT_ROOT` to the isolated root;
2. persist a running campaign;
3. enqueue a provenance-bound `report` job, claim it as the running job;
4. enqueue a second governed queued job;
5. call `main.cancel_campaign(campaign.id)`;
6. verify campaign state `cancelled`, `cancelled_queued_jobs == 1`, `running_jobs == 1`, and `running_jobs_not_forcibly_terminated is True`;
7. verify queued row `cancelled`, claimed row still `running`;
8. call `main.queue_report(campaign.id)` and require HTTP 409 containing `cancelled`;
9. set `post_cancel_admissions` to zero because no new queue row was created.

Never terminate the running job from the cancellation endpoint.

- [ ] **Step 4: Verify cancellation regressions**

Run:
```bash
PYTHONPATH=backend:backend/tests pytest -q \
  backend/tests/test_self_owned_rehearsal_controls.py \
  backend/tests/test_campaign_cancel.py
```
Expected: all selected tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/tests/rehearsal_scenarios.py backend/tests/test_self_owned_rehearsal_controls.py
git commit -m "test(rehearsal): prove cancellation enforcement"
```

---

### Task 7: Policy drift must block stale work before dispatch

**Files:**
- Modify: `backend/tests/rehearsal_scenarios.py`
- Modify: `backend/tests/test_self_owned_rehearsal_controls.py`

**Interfaces:**
- Produces `run_policy_drift_scenario(root, monkeypatch) -> ScenarioResult` for mandatory scenario name `scope_drift_blocks_execution`.
- Consumes `attach_job_provenance` and `worker_service.process_one`.

- [ ] **Step 1: Add the failing policy-drift test**

```python
from rehearsal_scenarios import run_policy_drift_scenario


def test_policy_drift_blocks_stale_job_before_processor_dispatch(tmp_path, monkeypatch):
    result = run_policy_drift_scenario(tmp_path, monkeypatch)
    assert result.name == "scope_drift_blocks_execution"
    assert result.status == "pass"
    assert result.reason == "policy_fingerprint_mismatch_before_dispatch"
    assert result.references.counters == {"processor_calls": 0}
```

- [ ] **Step 2: Verify RED**

Run:
```bash
PYTHONPATH=backend:backend/tests pytest -q \
  backend/tests/test_self_owned_rehearsal_controls.py::test_policy_drift_blocks_stale_job_before_processor_dispatch
```
Expected: import error for the missing runner.

- [ ] **Step 3: Implement a model-valid policy drift and processor spy**

The runner must:
1. persist a ready campaign with `max_requests_per_second=2.0`;
2. create a provenance-bound `report` job from that snapshot with `max_attempts=1`;
3. reload the campaign and change only `target.rules.max_requests_per_second` to `3.0`, then save with the expected version;
4. monkeypatch `worker_service.process_report` to append to a local `processor_calls` list, and `advance_campaign` to stop;
5. call `worker_service.process_one(queue, store, "worker-drift")`;
6. verify the job becomes `failed`, `last_error` contains `policy_fingerprint_mismatch`, and `processor_calls` remains empty.

This is the execution-side drift proof. The subdomain scenario from Task 3 independently proves scope allow/deny enforcement; do not persist an invalid campaign whose primary target is outside its own allowed scope.

- [ ] **Step 4: Verify provenance regressions**

Run:
```bash
PYTHONPATH=backend:backend/tests pytest -q \
  backend/tests/test_self_owned_rehearsal_controls.py \
  backend/tests/test_worker_job_provenance.py \
  backend/tests/test_job_provenance_integration.py
```
Expected: all selected tests PASS and the processor spy remains unused.

- [ ] **Step 5: Commit**

```bash
git add backend/tests/rehearsal_scenarios.py backend/tests/test_self_owned_rehearsal_controls.py
git commit -m "test(rehearsal): prove stale provenance blocks dispatch"
```

---

### Task 8: Sentinel-secret confinement scenario

**Files:**
- Modify: `backend/tests/rehearsal_scenarios.py`
- Modify: `backend/tests/test_self_owned_rehearsal_controls.py`

**Interfaces:**
- Produces `run_secret_confinement_scenario(root, monkeypatch) -> ScenarioResult`.
- Consumes `secret_vault.set_secret`, `Storage.put/list/read` APIs, `JobQueue`, and `contains_raw_value`.

- [ ] **Step 1: Add the failing secret-confinement test**

```python
from rehearsal_scenarios import run_secret_confinement_scenario


def test_secret_sentinel_is_confined_to_vault(tmp_path, monkeypatch):
    result = run_secret_confinement_scenario(tmp_path, monkeypatch)
    assert result.status == "pass"
    assert result.reason == "raw_sentinel_absent_from_public_surfaces"
    assert result.contains_secrets is False
    assert result.references.counters["checked_surfaces"] >= 6
```

- [ ] **Step 2: Verify RED**

Run:
```bash
PYTHONPATH=backend:backend/tests pytest -q \
  backend/tests/test_self_owned_rehearsal_controls.py::test_secret_sentinel_is_confined_to_vault
```
Expected: import error for the missing runner.

- [ ] **Step 3: Implement vault setup and exact persistence-surface inspection**

Configure the test vault exactly as existing vault tests do:

```python
monkeypatch.setenv("XBOW_VAULT_ENABLED", "true")
monkeypatch.setenv(
    "XBOW_VAULT_MASTER_KEY",
    base64.urlsafe_b64encode(b"r" * 32).decode("ascii"),
)
monkeypatch.setenv("XBOW_VAULT_PATH", str(root / "rehearsal-vault.json"))
marker = "REHEARSAL-SENTINEL-7c44f1"
set_secret("llm_api_key", marker)
```

Persist only redacted non-secret data into the campaign, one `evidence` observation, one `validation` artifact, and one non-secret queued report payload. Read the artifact through integrity-checking storage API:

```python
artifact = store.put_artifact(
    campaign.id,
    "validation",
    b'{"secret":"[redacted]"}',
    media_type="application/json",
    idempotency_key="rehearsal-secret-artifact",
)
artifact_metadata, artifact_content = store.read_artifact(campaign.id, artifact["id"])
public_surfaces = [
    store.get_campaign(campaign.id),
    store.list_observations(campaign.id),
    store.list_artifacts(campaign.id),
    artifact_metadata,
    artifact_content,
    queue.get(job["id"]),
]
leaked = contains_raw_value(marker, public_surfaces)
```

Add a positive control inside the runner/test path: `contains_raw_value(marker, [{"accidental": marker}])` must be true. Never inspect or include the vault file itself in public surfaces; the vault is the approved secret boundary.

- [ ] **Step 4: Verify vault/secret regressions**

Run:
```bash
PYTHONPATH=backend:backend/tests pytest -q \
  backend/tests/test_self_owned_rehearsal_controls.py \
  backend/tests/test_worker_secrets.py \
  backend/tests/test_secret_vault.py
```
Expected: all selected tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/tests/rehearsal_scenarios.py backend/tests/test_self_owned_rehearsal_controls.py
git commit -m "test(rehearsal): enforce sentinel secret confinement"
```

---

### Task 9: Aggregate all eight scenarios and prove determinism

**Files:**
- Modify: `backend/tests/rehearsal_scenarios.py`
- Modify: `backend/tests/test_self_owned_rehearsal.py`

**Interfaces:**
- Produces `build_rehearsal_scenarios(root_factory, monkeypatch) -> dict[str, Callable[[], ScenarioResult]]`.
- Consumes all eight runners and Task 1 `run_rehearsal`.

- [ ] **Step 1: Write the failing aggregate test**

```python
from pathlib import Path

from app.self_owned_rehearsal import MANDATORY_SCENARIOS, run_rehearsal
from rehearsal_scenarios import build_rehearsal_scenarios


def test_full_self_owned_rehearsal_passes_all_mandatory_scenarios(tmp_path, monkeypatch):
    counter = 0

    def make_root(name: str) -> Path:
        nonlocal counter
        counter += 1
        root = tmp_path / f"{counter:02d}-{name}"
        root.mkdir()
        return root

    report = run_rehearsal(build_rehearsal_scenarios(make_root, monkeypatch))
    assert report.status == "pass"
    assert [item.name for item in report.scenarios] == list(MANDATORY_SCENARIOS)
    assert all(item.status == "pass" for item in report.scenarios)
    assert report.external_network_used is False
    assert report.contains_secrets is False
```

- [ ] **Step 2: Verify RED**

Run:
```bash
PYTHONPATH=backend:backend/tests pytest -q \
  backend/tests/test_self_owned_rehearsal.py::test_full_self_owned_rehearsal_passes_all_mandatory_scenarios
```
Expected: import error for missing `build_rehearsal_scenarios`.

- [ ] **Step 3: Implement the exact mandatory mapping**

```python
def build_rehearsal_scenarios(root_factory, monkeypatch):
    return {
        "redirect_scope_enforcement": lambda: run_redirect_scope_scenario(
            root_factory("redirect"), monkeypatch
        ),
        "subdomain_scope_enforcement": lambda: run_subdomain_scope_scenario(
            root_factory("subdomain"), monkeypatch
        ),
        "http_429_bounded": lambda: run_http_429_scenario(
            root_factory("429"), monkeypatch
        ),
        "worker_failure_durability": lambda: run_worker_failure_scenario(
            root_factory("worker-failure"), monkeypatch
        ),
        "crash_window_outbox_recovery": lambda: run_outbox_recovery_scenario(
            root_factory("outbox"), monkeypatch
        ),
        "cancellation_enforcement": lambda: run_cancellation_scenario(
            root_factory("cancel"), monkeypatch
        ),
        "secret_sentinel_confinement": lambda: run_secret_confinement_scenario(
            root_factory("secret"), monkeypatch
        ),
        "scope_drift_blocks_execution": lambda: run_policy_drift_scenario(
            root_factory("drift"), monkeypatch
        ),
    }
```

- [ ] **Step 4: Add a repeated-run semantic determinism test**

Build two fresh mappings with separate roots and compare only `(name, status, reason)` tuples, never generated campaign/job IDs:

```python
first = run_rehearsal(build_rehearsal_scenarios(make_root_a, monkeypatch))
second = run_rehearsal(build_rehearsal_scenarios(make_root_b, monkeypatch))
assert [(x.name, x.status, x.reason) for x in first.scenarios] == [
    (x.name, x.status, x.reason) for x in second.scenarios
]
```

- [ ] **Step 5: Verify all rehearsal tests**

Run:
```bash
PYTHONPATH=backend:backend/tests pytest -q \
  backend/tests/test_rehearsal_fixture.py \
  backend/tests/test_self_owned_rehearsal.py \
  backend/tests/test_self_owned_rehearsal_http.py \
  backend/tests/test_self_owned_rehearsal_resilience.py \
  backend/tests/test_self_owned_rehearsal_controls.py
```
Expected: all rehearsal tests PASS; aggregate report has `status="pass"`, `external_network_used=False`, `contains_secrets=False`.

- [ ] **Step 6: Commit**

```bash
git add backend/tests/rehearsal_scenarios.py backend/tests/test_self_owned_rehearsal.py
git commit -m "test(rehearsal): aggregate self-owned safety scenarios"
```

---

### Task 10: Full verification and merge gate

**Files:**
- No feature file changes expected.

**Interfaces:**
- Produces final PR evidence only.

- [ ] **Step 1: Run compile/lint exactly as CI does**

```bash
python -m compileall -q backend/app backend/tests
ruff check backend/app backend/tests
```
Expected: exit 0; Ruff reports `All checks passed!`.

- [ ] **Step 2: Run the complete backend test suite with the repository's strict settings**

```bash
PYTHONPATH=backend pytest -q --strict-config --strict-markers backend/tests
```
Expected: all existing and new tests PASS; rehearsal tests require no public Internet target access.

- [ ] **Step 3: Run package/readiness/audit gates**

```bash
python -m pip check
PYTHONPATH=backend \
XBOW_DB_PATH=/tmp/xbow-rehearsal-readiness.sqlite3 \
XBOW_ARTIFACT_ROOT=/tmp/xbow-rehearsal-readiness-artifacts \
python -m app.readiness
pip-audit -r backend/requirements.txt
```
Expected: no broken requirements; readiness exits 0; dependency audit meets the repository's existing zero-known-vulnerability gate.

- [ ] **Step 4: Run config/frontend syntax gates from CI**

```bash
node --check frontend/app.js
node --check frontend/sw.js
docker compose config --quiet
XBOW_POSTGRES_PASSWORD=ci-postgres \
XBOW_DATABASE_URL=postgresql://xbow:ci-postgres@postgres:5432/xbow \
XBOW_REDIS_PASSWORD=ci-redis \
XBOW_REDIS_URL=redis://:ci-redis@redis:6379/0 \
docker compose -f docker-compose.yml -f docker-compose.distributed.yml config --quiet
XBOW_PUBLIC_HOST=example.test \
docker compose -f docker-compose.yml -f docker-compose.tls.yml config --quiet
```
Expected: every command exits 0.

- [ ] **Step 5: Review final diff for forbidden capability expansion**

```bash
git diff main...HEAD -- backend/app backend/tests .github/workflows
```
Required review findings:
- no production rehearsal endpoint;
- no scanner/PentAGI/browser activation;
- no exploit/fuzz/payload feature;
- no redirect-following enablement;
- no `429` retry loop;
- no public-DNS fallback in rehearsal fixture;
- worker provenance verification still occurs before `process_*` dispatch;
- no raw secret values added to persisted/public outputs.

- [ ] **Step 6: Open/update the PR and verify exact-head workflows**

The PR description records: loopback/in-memory only, eight scenarios, no new offensive capability, production validator defaults unchanged, exact final pytest count, and security/supply-chain results. Require CI, security, and supply-chain green on the exact final head SHA before merge.

- [ ] **Step 7: Merge and verify `main` on the exact merge SHA**

After merge, verify CI, security, and supply-chain runs attached to the merge SHA. Do not declare completion from PR-head evidence alone.
