# Self-Owned Campaign Rehearsal v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic CI rehearsal that exercises XBOW's existing scope, provenance, queue durability, outbox recovery, cancellation, and secret-confinement controls entirely against loopback/in-memory fixtures.

**Architecture:** Add a small production-side rehearsal coordinator that only aggregates named scenario callbacks and emits a redacted machine-readable report. Keep all target simulation in test-only fixtures. Add one narrow dependency-injection seam to the HTTP validator so tests can route declared fixture hostnames to loopback without public DNS; all other scenarios call the existing queue, worker, outbox, cancellation, provenance, storage, and vault code paths directly.

**Tech Stack:** Python 3.12, pytest, stdlib `http.server`, `urllib.request`, SQLite-backed `Storage`/`JobQueue`, existing FastAPI/domain models, Ruff, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-16-self-owned-campaign-rehearsal-v1-design.md`

## Global Constraints

- Rehearsal target execution is loopback/in-memory only; no public target traffic and no public DNS lookup is required.
- Do not run Nuclei, Strix, PentAGI, browser automation, arbitrary shell jobs, exploit payloads, fuzzing, credential attacks, DoS, social engineering, or destructive testing as part of the rehearsal.
- Do not add a production endpoint that accepts an arbitrary rehearsal target.
- In-scope redirects remain non-followed by the current validator; the rehearsal verifies that the redirect destination is scope-valid without changing redirect behavior.
- Out-of-scope redirects and denied/undeclared fixture hosts must receive zero requests.
- `429` handling must remain bounded by existing semantics; v1 adds no new generic retry algorithm.
- Failure injection exists only in test/rehearsal code and never bypasses provenance, scope, or sandbox checks.
- Raw sentinel secrets must not appear in campaign events, public observations, persisted rehearsal evidence, non-secret job payloads, or the public rehearsal report.
- Differential evidence must not auto-confirm findings.
- Any ambiguous scenario outcome fails closed.
- Rehearsal errors expose stable reason/class codes only, never raw exception messages.
- v1 remains test/rehearsal infrastructure; it does not enable a new production execution mode or external HackerOne submission.

---

## File Structure

**Create `backend/app/self_owned_rehearsal.py`**
- Owns `ScenarioResult`, `RehearsalReport`, mandatory scenario-name validation, redacted report aggregation, stable unexpected-exception classification, and pure secret-surface checking helpers.
- Does not import test fixtures, create Internet clients, or implement policy/queue/retry behavior.

**Create `backend/tests/rehearsal_fixture.py`**
- Owns the loopback HTTP server, deterministic routes, request log, explicit hostname-to-loopback mapping, and an opener that refuses unmapped/non-loopback destinations before DNS/network access.

**Create `backend/tests/test_self_owned_rehearsal.py`**
- Unit tests for report aggregation, mandatory scenario coverage, exception sanitization, and secret-surface detection.

**Create `backend/tests/test_self_owned_rehearsal_http.py`**
- Integration tests for redirects, mapped subdomains, denied/unknown hosts, and `429` behavior through `safe_http_probe`.

**Create `backend/tests/test_self_owned_rehearsal_resilience.py`**
- Integration tests for worker failure/lease recovery and crash-window outbox recovery.

**Create `backend/tests/test_self_owned_rehearsal_controls.py`**
- Integration tests for cancellation, policy/scope drift provenance rejection, and secret confinement.

**Modify `backend/app/validator.py`**
- Add optional `opener` and `sleep_fn` dependency seams to `safe_http_probe`; production defaults stay exactly as today.

**No workflow file is required initially.** Existing `.github/workflows/ci.yml` already executes all `backend/tests`, Ruff, compileall, readiness, pip check, pip-audit, and Docker build. Only modify CI if the new tests cannot be discovered by the existing command; discovery is the expected path.

---

### Task 1: Redacted rehearsal report coordinator

**Files:**
- Create: `backend/app/self_owned_rehearsal.py`
- Create: `backend/tests/test_self_owned_rehearsal.py`

**Interfaces:**
- Produces:
  - `MANDATORY_SCENARIOS: tuple[str, ...]`
  - `ScenarioReferences(campaign_id: str | None, job_ids: tuple[str, ...], event_types: tuple[str, ...], counters: dict[str, int])`
  - `ScenarioResult(name: str, status: Literal["pass", "fail"], reason: str, references: ScenarioReferences, external_network_used: bool = False, contains_secrets: bool = False)`
  - `RehearsalReport(status: Literal["pass", "fail"], scenarios: tuple[ScenarioResult, ...], external_network_used: bool, contains_secrets: bool)`
  - `run_rehearsal(scenarios: Mapping[str, Callable[[], ScenarioResult]]) -> RehearsalReport`
  - `contains_raw_value(value: str, surfaces: Iterable[object]) -> bool`
- Consumes: no new runtime dependencies beyond stdlib/dataclasses/typing/json.

- [ ] **Step 1: Write failing report/coordinator tests**

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


def test_run_rehearsal_requires_exact_mandatory_scenario_set():
    scenarios = {name: (lambda name=name: _pass(name)) for name in MANDATORY_SCENARIOS}
    report = run_rehearsal(scenarios)
    assert report.status == "pass"
    assert [item.name for item in report.scenarios] == list(MANDATORY_SCENARIOS)
    assert report.external_network_used is False
    assert report.contains_secrets is False


def test_run_rehearsal_fails_closed_on_missing_scenario():
    scenarios = {name: (lambda name=name: _pass(name)) for name in MANDATORY_SCENARIOS[:-1]}
    report = run_rehearsal(scenarios)
    assert report.status == "fail"
    assert report.scenarios[-1].name == MANDATORY_SCENARIOS[-1]
    assert report.scenarios[-1].reason == "scenario_missing"


def test_run_rehearsal_sanitizes_unexpected_exception_message():
    marker = "SECRET-MUST-NOT-LEAK"
    scenarios = {name: (lambda name=name: _pass(name)) for name in MANDATORY_SCENARIOS}

    def explode():
        raise RuntimeError(marker)

    scenarios[MANDATORY_SCENARIOS[0]] = explode
    report = run_rehearsal(scenarios)
    encoded = str(report)
    assert report.status == "fail"
    assert report.scenarios[0].reason == "unexpected_RuntimeError"
    assert marker not in encoded


def test_contains_raw_value_checks_nested_text_and_bytes():
    marker = "sentinel-raw-value"
    assert contains_raw_value(marker, [{"nested": [b"prefix sentinel-raw-value suffix"]}]) is True
    assert contains_raw_value(marker, [{"nested": ["redacted"]}]) is False
```

- [ ] **Step 2: Run the tests to verify RED**

Run:
```bash
PYTHONPATH=backend pytest -q backend/tests/test_self_owned_rehearsal.py
```
Expected: collection/import failure because `app.self_owned_rehearsal` does not exist.

- [ ] **Step 3: Implement the minimal coordinator and redaction-safe data types**

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


def _unexpected_result(name: str, exc: Exception) -> ScenarioResult:
    return ScenarioResult(
        name=name,
        status="fail",
        reason=f"unexpected_{exc.__class__.__name__}",
    )


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
            result = _unexpected_result(name, exc)
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


def contains_raw_value(value: str, surfaces: Iterable[object]) -> bool:
    if not value:
        return False
    needle = value.encode("utf-8")
    for surface in surfaces:
        if isinstance(surface, bytes):
            encoded = surface
        else:
            encoded = json.dumps(surface, ensure_ascii=False, default=str).encode("utf-8")
        if needle in encoded:
            return True
    return False
```

Do not add arbitrary detail/message fields to `ScenarioResult`; stable reason codes are the deliberate leak-prevention boundary.

- [ ] **Step 4: Run Task 1 tests to verify GREEN**

Run:
```bash
PYTHONPATH=backend pytest -q backend/tests/test_self_owned_rehearsal.py
```
Expected: all Task 1 tests PASS.

- [ ] **Step 5: Run Ruff on the new unit**

Run:
```bash
ruff check backend/app/self_owned_rehearsal.py backend/tests/test_self_owned_rehearsal.py
```
Expected: `All checks passed!`

- [ ] **Step 6: Commit Task 1**

```bash
git add backend/app/self_owned_rehearsal.py backend/tests/test_self_owned_rehearsal.py
git commit -m "test(rehearsal): add redacted scenario coordinator"
```

---

### Task 2: Loopback-only HTTP fixture and mapped opener

**Files:**
- Create: `backend/tests/rehearsal_fixture.py`
- Create: `backend/tests/test_rehearsal_fixture.py`

**Interfaces:**
- Produces:
  - `ExternalTargetAttempt(RuntimeError)`
  - `RequestRecord(host: str, path: str, status_hint: int | None = None)`
  - `LocalRehearsalServer` context manager with `.port`, `.requests`, `.base_url`
  - `MappedLoopbackOpener(mapping: Mapping[str, tuple[str, int]])` with `.open(request, timeout)` and `.blocked_hosts`
- Consumes: stdlib `ThreadingHTTPServer`, `BaseHTTPRequestHandler`, `urllib.request`, `urllib.parse`; production `_NoRedirect` is not imported here to keep the fixture self-contained.

- [ ] **Step 1: Write failing fixture tests**

```python
# backend/tests/test_rehearsal_fixture.py
from urllib.error import HTTPError
from urllib.request import Request

import pytest

from rehearsal_fixture import ExternalTargetAttempt, LocalRehearsalServer, MappedLoopbackOpener


def test_fixture_binds_loopback_and_serves_deterministic_routes():
    with LocalRehearsalServer() as server:
        opener = MappedLoopbackOpener({"allowed.rehearsal.test": ("127.0.0.1", server.port)})
        with opener.open(Request("http://allowed.rehearsal.test/ok", method="GET"), timeout=1) as response:
            assert response.getcode() == 200
        assert server.requests[-1].host.startswith("allowed.rehearsal.test")
        assert server.requests[-1].path == "/ok"
        assert opener.blocked_hosts == []


def test_mapped_opener_refuses_unmapped_host_without_fallback():
    with LocalRehearsalServer() as server:
        opener = MappedLoopbackOpener({"allowed.rehearsal.test": ("127.0.0.1", server.port)})
        with pytest.raises(ExternalTargetAttempt, match="unmapped_target"):
            opener.open(Request("http://outside.rehearsal.test/ok", method="GET"), timeout=1)
        assert opener.blocked_hosts == ["outside.rehearsal.test"]
        assert server.requests == []


def test_fixture_redirect_is_not_followed_by_mapped_opener():
    with LocalRehearsalServer() as server:
        opener = MappedLoopbackOpener({"allowed.rehearsal.test": ("127.0.0.1", server.port)})
        with pytest.raises(HTTPError) as exc:
            opener.open(Request("http://allowed.rehearsal.test/redirect-in-scope", method="GET"), timeout=1)
        assert exc.value.code == 302
        assert len(server.requests) == 1
```

- [ ] **Step 2: Run fixture tests to verify RED**

Run:
```bash
PYTHONPATH=backend:backend/tests pytest -q backend/tests/test_rehearsal_fixture.py
```
Expected: import failure because `rehearsal_fixture.py` does not exist.

- [ ] **Step 3: Implement `LocalRehearsalServer`**

Use `ThreadingHTTPServer(("127.0.0.1", 0), Handler)` and a daemon thread. The handler must implement only `GET` and these exact routes:

```python
ROUTES = {
    "/ok": (200, {}, b"ok"),
    "/redirect-in-scope": (302, {"Location": "/ok"}, b""),
    "/redirect-out-of-scope": (302, {"Location": "http://outside.rehearsal.test/ok"}, b""),
    "/throttle": (429, {"Retry-After": "1"}, b"throttled"),
}
```

For `/echo` and `/secret-echo`, return the query value in the body only so validation/redaction tests can inspect what would have been reflected. Suppress access logging by overriding `log_message` to return `None`. Record only Host/path/method metadata in memory; do not record Authorization/Cookie headers or body values.

- [ ] **Step 4: Implement `MappedLoopbackOpener` with no DNS fallback**

The opener must:
1. parse the original hostname;
2. reject absent/unmapped hostnames with `ExternalTargetAttempt("unmapped_target")` before calling any network API;
3. require the mapped IP to be `127.0.0.1` or `::1`;
4. rewrite the connection destination to the mapped loopback IP/port;
5. preserve the original Host header;
6. use an inner `build_opener(_NoRedirect())` where the test-only `_NoRedirect` subclass returns `None` from `redirect_request`.

```python
class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None
```

No code path may call `socket.getaddrinfo()` for an unmapped rehearsal hostname.

- [ ] **Step 5: Run fixture tests to verify GREEN**

Run:
```bash
PYTHONPATH=backend:backend/tests pytest -q backend/tests/test_rehearsal_fixture.py
```
Expected: all fixture tests PASS.

- [ ] **Step 6: Commit Task 2**

```bash
git add backend/tests/rehearsal_fixture.py backend/tests/test_rehearsal_fixture.py
git commit -m "test(rehearsal): add loopback-only target fixture"
```

---

### Task 3: Validator injection seam plus redirect/subdomain/429 rehearsal

**Files:**
- Modify: `backend/app/validator.py` in `safe_http_probe`
- Create: `backend/tests/test_self_owned_rehearsal_http.py`
- Modify: `backend/tests/test_validator.py` only if an existing assertion relies on the exact function signature; otherwise leave it untouched.

**Interfaces:**
- Produces changed signature:
  - `safe_http_probe(campaign, finding, *, opener=None, sleep_fn=time.sleep) -> ProbeResult`
- Consumes Task 2 `LocalRehearsalServer`, `MappedLoopbackOpener`.
- Production call sites continue calling `safe_http_probe(campaign, finding)` unchanged.

- [ ] **Step 1: Write failing injection and HTTP-safety tests**

```python
# backend/tests/test_self_owned_rehearsal_http.py
from app.main import Campaign, CampaignState, Finding, ProgramRules, TargetInput
from app.validator import safe_http_probe
from rehearsal_fixture import LocalRehearsalServer, MappedLoopbackOpener


def _campaign(host: str = "allowed.rehearsal.test") -> Campaign:
    return Campaign(
        id="rehearsal-http",
        state=CampaignState.validating,
        target=TargetInput(
            name="rehearsal",
            primary_url=f"http://{host}",
            rules=ProgramRules(
                authorization_reference="self-owned-rehearsal",
                allowed_targets=[host, "*.allowed.rehearsal.test"],
                denied_targets=["denied.allowed.rehearsal.test"],
                max_requests_per_second=20.0,
            ),
        ),
    )


def _finding(endpoint: str) -> Finding:
    return Finding(
        id="finding-http",
        title="fixture",
        severity="low",
        asset="http://allowed.rehearsal.test",
        endpoint=endpoint,
        summary="fixture",
        status="validation_required",
        discovered_by="fixture-scanner",
    )


def test_in_scope_redirect_is_observed_but_not_followed(monkeypatch):
    monkeypatch.setenv("XBOW_ENABLE_HTTP_VALIDATION", "true")
    monkeypatch.delenv("XBOW_ENABLE_DIFFERENTIAL_VALIDATION", raising=False)
    with LocalRehearsalServer() as server:
        opener = MappedLoopbackOpener({"allowed.rehearsal.test": ("127.0.0.1", server.port)})
        result = safe_http_probe(
            _campaign(),
            _finding("http://allowed.rehearsal.test/redirect-in-scope"),
            opener=opener,
            sleep_fn=lambda _: None,
        )
        assert result.status == "observed"
        assert result.http_status == 302
        assert [item.path for item in server.requests] == ["/redirect-in-scope"]


def test_out_of_scope_redirect_receives_zero_followup_requests(monkeypatch):
    monkeypatch.setenv("XBOW_ENABLE_HTTP_VALIDATION", "true")
    with LocalRehearsalServer() as server:
        opener = MappedLoopbackOpener({"allowed.rehearsal.test": ("127.0.0.1", server.port)})
        result = safe_http_probe(
            _campaign(),
            _finding("http://allowed.rehearsal.test/redirect-out-of-scope"),
            opener=opener,
            sleep_fn=lambda _: None,
        )
        assert result.http_status == 302
        assert [item.path for item in server.requests] == ["/redirect-out-of-scope"]
        assert opener.blocked_hosts == []


def test_allowed_subdomain_maps_to_loopback_while_denied_subdomain_is_blocked_before_transport(monkeypatch):
    monkeypatch.setenv("XBOW_ENABLE_HTTP_VALIDATION", "true")
    campaign = _campaign()
    with LocalRehearsalServer() as server:
        opener = MappedLoopbackOpener({"api.allowed.rehearsal.test": ("127.0.0.1", server.port)})
        allowed = safe_http_probe(
            campaign,
            _finding("http://api.allowed.rehearsal.test/ok"),
            opener=opener,
            sleep_fn=lambda _: None,
        )
        denied = safe_http_probe(
            campaign,
            _finding("http://denied.allowed.rehearsal.test/ok"),
            opener=opener,
            sleep_fn=lambda _: None,
        )
        assert allowed.http_status == 200
        assert denied.status == "blocked"
        assert len(server.requests) == 1


def test_429_is_observed_once_without_new_retry_loop(monkeypatch):
    monkeypatch.setenv("XBOW_ENABLE_HTTP_VALIDATION", "true")
    monkeypatch.delenv("XBOW_ENABLE_DIFFERENTIAL_VALIDATION", raising=False)
    with LocalRehearsalServer() as server:
        opener = MappedLoopbackOpener({"allowed.rehearsal.test": ("127.0.0.1", server.port)})
        result = safe_http_probe(
            _campaign(),
            _finding("http://allowed.rehearsal.test/throttle"),
            opener=opener,
            sleep_fn=lambda _: None,
        )
        assert result.status == "observed"
        assert result.http_status == 429
        assert len(server.requests) == 1
```

- [ ] **Step 2: Run HTTP rehearsal tests to verify RED**

Run:
```bash
PYTHONPATH=backend:backend/tests pytest -q backend/tests/test_self_owned_rehearsal_http.py
```
Expected: FAIL with `TypeError` because `safe_http_probe` does not yet accept `opener` / `sleep_fn`.

- [ ] **Step 3: Add the narrow dependency seam without changing production defaults**

Modify only the construction/use points in `safe_http_probe`:

```python
def safe_http_probe(campaign, finding, *, opener=None, sleep_fn=time.sleep) -> ProbeResult:
    # existing gates and URL/scope validation stay unchanged
    request_opener = opener if opener is not None else build_opener(_NoRedirect())
    baseline = _request_get(request_opener, url, timeout=timeout, max_bytes=max_bytes)
    # existing redaction stays unchanged
    if differential_enabled and marker_url is not None:
        sleep_fn(1.0 / campaign.target.rules.max_requests_per_second)
        marker_result = _request_get(
            request_opener,
            marker_url,
            timeout=timeout,
            max_bytes=max_bytes,
        )
        # existing differential metadata stays unchanged
```

Do not add resolver hooks, redirect-following flags, retry flags, or production environment switches.

- [ ] **Step 4: Run existing validator tests and new HTTP rehearsal tests**

Run:
```bash
PYTHONPATH=backend:backend/tests pytest -q \
  backend/tests/test_validator.py \
  backend/tests/test_self_owned_rehearsal_http.py
```
Expected: all selected tests PASS.

- [ ] **Step 5: Commit Task 3**

```bash
git add backend/app/validator.py backend/tests/test_self_owned_rehearsal_http.py backend/tests/test_validator.py
git commit -m "test(rehearsal): exercise local HTTP safety invariants"
```

If `backend/tests/test_validator.py` is unchanged, omit it from `git add`.

---

### Task 4: Worker failure and expired-lease durability scenario

**Files:**
- Create: `backend/tests/test_self_owned_rehearsal_resilience.py`
- No production file change expected.

**Interfaces:**
- Consumes existing `JobQueue.enqueue`, `claim`, `finish`, `recover_expired_leases`, and `worker_service.process_one`.
- Produces test helper `_runtime(tmp_path) -> tuple[Campaign, Storage, JobQueue]` local to the test module.

- [ ] **Step 1: Write a failing durability test that encodes the rehearsal invariant**

Use a real queue row with `max_attempts=2`. Claim it, simulate worker disappearance by expiring its lease directly in the test database, call the public `recover_expired_leases()`, reclaim it, then force the production worker path to fail once. The assertions must prove no false success and bounded attempts.

```python
from datetime import datetime, timedelta, timezone

from app.job_provenance import attach_job_provenance
from app.worker_service import process_one


def test_worker_failure_and_lease_recovery_never_fabricate_success(tmp_path, monkeypatch):
    campaign, store, queue = _runtime(tmp_path)
    payload = attach_job_provenance(
        {"campaign_id": campaign.id, "platform": "generic"},
        campaign,
        job_kind="report",
        action="report",
    )
    job = queue.enqueue(campaign.id, "report", payload, max_attempts=2, dedupe_key="rehearsal-worker-failure")
    claimed = queue.claim("worker-crashed")
    assert claimed is not None and claimed["id"] == job["id"]

    expired = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    with queue.connect() as conn:
        conn.execute("UPDATE jobs SET lease_expires_at=? WHERE id=?", (expired, job["id"]))

    assert queue.recover_expired_leases() == 1
    recovered = queue.get(job["id"])
    assert recovered["status"] == "queued"
    assert recovered["attempts"] == 1

    def fail_report(job, store):
        raise RuntimeError("injected-rehearsal-failure")

    monkeypatch.setattr("app.worker_service.process_report", fail_report)
    monkeypatch.setattr(
        "app.worker_service.advance_campaign",
        lambda campaign, queue, store: {"action": {"kind": "stop"}},
    )
    assert process_one(queue, store, "worker-retry") is True

    final = queue.get(job["id"])
    assert final["status"] == "failed"
    assert final["attempts"] == 2
    events = store.get_campaign(campaign.id)["events"]
    assert not any(
        event.get("type") == "worker_outcome"
        and event.get("job_id") == job["id"]
        and event.get("success") is True
        for event in events
    )
```

The local `_runtime` must create a ready campaign with `example.test`, temp SQLite DB/artifact root, and persist it before returning.

- [ ] **Step 2: Run the new durability test**

Run:
```bash
PYTHONPATH=backend pytest -q backend/tests/test_self_owned_rehearsal_resilience.py::test_worker_failure_and_lease_recovery_never_fabricate_success
```
Expected before any fix: if the existing queue semantics already satisfy the invariant, PASS is acceptable because this task is primarily regression coverage. If it fails, the failure must identify an actual mismatch in existing lease/failure semantics before any production change is made.

- [ ] **Step 3: If RED exposed a real bug, implement only the minimal queue/worker correction**

Allowed production files if required:
- `backend/app/jobqueue.py` only for incorrect expired-lease attempt/status transitions.
- `backend/app/worker_service.py` only for incorrect worker-outcome recording.

Required invariant after any fix:
```text
expired lease with attempts < max_attempts -> queued
next claim increments attempts
failed second attempt at max_attempts -> failed
no success worker_outcome event exists
```

Do not add a retry scheduler or change max-attempt defaults.

- [ ] **Step 4: Run existing queue/watchdog tests plus the rehearsal durability test**

Run:
```bash
PYTHONPATH=backend pytest -q \
  backend/tests/test_jobqueue.py \
  backend/tests/test_worker_watchdog.py \
  backend/tests/test_self_owned_rehearsal_resilience.py
```
Expected: all selected tests PASS.

- [ ] **Step 5: Commit Task 4**

```bash
git add backend/tests/test_self_owned_rehearsal_resilience.py backend/app/jobqueue.py backend/app/worker_service.py
git commit -m "test(rehearsal): cover worker failure durability"
```

Only stage production files if they actually changed.

---

### Task 5: Crash-window outbox recovery without duplicate logical work

**Files:**
- Modify: `backend/tests/test_self_owned_rehearsal_resilience.py`
- No production change expected; use existing `outbox_recovery` / `main.reconcile_campaign_outbox_local` behavior.

**Interfaces:**
- Consumes `append_campaign_event`, `JobQueue.enqueue`, `get_by_dedupe`, and `main.reconcile_campaign_outbox_local`.
- Produces no new application interface.

- [ ] **Step 1: Add the crash-window scenario test**

```python
from app import main
from app.campaign_audit import append_campaign_event


def test_crash_after_enqueue_reconciles_audit_without_duplicate_job(tmp_path, monkeypatch):
    campaign, store, queue = _runtime(tmp_path, campaign_id="rehearsal-outbox", state="running")
    request_id = "rehearsal-report-crash-window"
    document, version = store.get_campaign_record(campaign.id)
    interrupted = main.Campaign.model_validate(document)
    append_campaign_event(
        interrupted.events,
        {
            "type": "report_requested",
            "request_id": request_id,
            "platform": "generic",
            "purpose": "manual",
            "at": main.utcnow(),
        },
    )
    store.save_campaign(interrupted.model_dump(mode="json"), expected_version=version)

    existing = queue.enqueue(
        campaign.id,
        "report",
        {"campaign_id": campaign.id, "platform": "generic"},
        max_attempts=2,
        dedupe_key=f"report:generic:{request_id}",
    )
    assert queue.stats()["total"] == 1

    result = main.reconcile_campaign_outbox_local(campaign.id)

    assert result["repaired"] == 1
    assert result["remaining"] == []
    assert result["automatic_job_creation"] is False
    assert JobQueue(queue.db_path).stats()["total"] == 1
    same = JobQueue(queue.db_path).get_by_dedupe(
        campaign.id,
        "report",
        f"report:generic:{request_id}",
    )
    assert same["id"] == existing["id"]
```

Update `_runtime` to accept explicit `campaign_id` and state using real `CampaignState` values, not raw unvalidated campaign documents.

- [ ] **Step 2: Run crash recovery tests**

Run:
```bash
PYTHONPATH=backend pytest -q \
  backend/tests/test_self_owned_rehearsal_resilience.py::test_crash_after_enqueue_reconciles_audit_without_duplicate_job \
  backend/tests/test_outbox_chaos.py
```
Expected: all tests PASS with the existing local-repair behavior. If the new scenario is RED, diagnose whether the test diverges from the existing outbox contract before modifying production code.

- [ ] **Step 3: Add a negative assertion for missing jobs**

Extend the scenario module with one assertion that an intent with no corresponding queue row stays `job_missing` and does not create work:

```python
assert result["repaired"] == 0
assert result["remaining"][0]["diagnosis"] == "job_missing"
assert result["automatic_job_creation"] is False
assert queue.stats()["total"] == 0
```

This prevents a future implementation from turning rehearsal recovery into automatic job recreation.

- [ ] **Step 4: Re-run resilience/outbox suite**

Run:
```bash
PYTHONPATH=backend pytest -q \
  backend/tests/test_self_owned_rehearsal_resilience.py \
  backend/tests/test_outbox_chaos.py
```
Expected: all selected tests PASS.

- [ ] **Step 5: Commit Task 5**

```bash
git add backend/tests/test_self_owned_rehearsal_resilience.py
git commit -m "test(rehearsal): prove crash-safe outbox recovery"
```

---

### Task 6: Cancellation enforcement scenario

**Files:**
- Create: `backend/tests/test_self_owned_rehearsal_controls.py`
- No production change expected.

**Interfaces:**
- Consumes existing `main.cancel_campaign`, `JobQueue.cancel_queued`, and `worker_service.process_one` behavior.
- Produces test helper `_configured_campaign(tmp_path, monkeypatch, *, campaign_id: str) -> tuple[Campaign, Storage, JobQueue]`.

- [ ] **Step 1: Write cancellation rehearsal test**

```python
from app.job_provenance import attach_job_provenance
from app.main import CampaignState, cancel_campaign
from app.worker_service import process_one


def test_cancellation_cancels_queued_work_and_blocks_new_worker_execution(tmp_path, monkeypatch):
    campaign, store, queue = _configured_campaign(tmp_path, monkeypatch, campaign_id="rehearsal-cancel")
    queued = queue.enqueue(
        campaign.id,
        "report",
        attach_job_provenance(
            {"campaign_id": campaign.id, "platform": "generic"},
            campaign,
            job_kind="report",
            action="report",
        ),
        max_attempts=2,
        dedupe_key="rehearsal-cancel-queued",
    )
    running = queue.enqueue(
        campaign.id,
        "report",
        attach_job_provenance(
            {"campaign_id": campaign.id, "platform": "generic"},
            campaign,
            job_kind="report",
            action="report",
        ),
        max_attempts=2,
        dedupe_key="rehearsal-cancel-running",
    )
    claimed = queue.claim("running-worker")
    assert claimed is not None

    result = cancel_campaign(campaign.id)

    assert result["state"] == CampaignState.cancelled
    assert result["cancelled_queued_jobs"] == 1
    assert result["running_jobs"] == 1
    assert result["running_jobs_not_forcibly_terminated"] is True
    assert queue.get(queued["id"])["status"] == "cancelled"
    assert queue.get(running["id"])["status"] == "running"
```

Ensure enqueue order makes the first claimed row the intended `running` job; if necessary enqueue `running` first, claim it, then enqueue `queued`, matching the established test pattern in `test_campaign_cancel.py`.

- [ ] **Step 2: Add post-cancellation admission/worker assertions**

Continue the same test or a second focused test:

```python
from fastapi import HTTPException
from app.main import queue_report

with pytest.raises(HTTPException) as exc:
    queue_report(campaign.id)
assert exc.value.status_code == 409
assert "cancelled" in str(exc.value.detail).lower()
```

For a previously claimed job that is returned to queued state only to exercise `process_one`, assert the worker cancels it rather than executing report logic, following the existing `test_running_job_becomes_cancelled_when_worker_observes_cancelled_campaign` pattern.

- [ ] **Step 3: Run cancellation regression set**

Run:
```bash
PYTHONPATH=backend pytest -q \
  backend/tests/test_self_owned_rehearsal_controls.py \
  backend/tests/test_campaign_cancel.py
```
Expected: all selected tests PASS.

- [ ] **Step 4: Commit Task 6**

```bash
git add backend/tests/test_self_owned_rehearsal_controls.py
git commit -m "test(rehearsal): prove cancellation enforcement"
```

---

### Task 7: Policy/scope drift must fail before execution

**Files:**
- Modify: `backend/tests/test_self_owned_rehearsal_controls.py`
- No production change expected unless the rehearsal exposes a provenance regression.

**Interfaces:**
- Consumes `attach_job_provenance`, `worker_service.process_one`, and the existing policy fingerprint verification.
- Produces no new application interface.

- [ ] **Step 1: Write the fail-before-dispatch test**

Use a report job because it is governed by provenance and has a safe stub-able processor. The key invariant is that the processor spy remains uncalled after campaign policy drift.

```python
from app import worker_service
from app.job_provenance import attach_job_provenance


def test_scope_or_policy_drift_rejects_stale_job_before_dispatch(tmp_path, monkeypatch):
    campaign, store, queue = _configured_campaign(tmp_path, monkeypatch, campaign_id="rehearsal-drift")
    payload = attach_job_provenance(
        {"campaign_id": campaign.id, "platform": "generic"},
        campaign,
        job_kind="report",
        action="report",
    )
    job = queue.enqueue(campaign.id, "report", payload, max_attempts=1, dedupe_key="rehearsal-drift")

    raw, version = store.get_campaign_record(campaign.id)
    current = worker_service.Campaign.model_validate(raw)
    current.target.rules.allowed_targets = ["changed.rehearsal.test"]
    store.save_campaign(current.model_dump(mode="json"), expected_version=version)

    dispatched = []
    monkeypatch.setattr(worker_service, "process_report", lambda job, store: dispatched.append(job["id"]))
    monkeypatch.setattr(
        worker_service,
        "advance_campaign",
        lambda campaign, queue, store: {"action": {"kind": "stop"}},
    )

    assert worker_service.process_one(queue, store, "worker-drift") is True
    final = queue.get(job["id"])
    assert final["status"] == "failed"
    assert "policy_fingerprint_mismatch" in (final["last_error"] or "")
    assert dispatched == []
```

If replacing `allowed_targets` makes the stored campaign invalid because its primary URL is no longer allowed, mutate `max_requests_per_second` from `2.0` to `3.0` in this test and add a separate pure `is_host_allowed` assertion for scope drift. Do not weaken model validation solely for the rehearsal.

- [ ] **Step 2: Run provenance tests to verify behavior**

Run:
```bash
PYTHONPATH=backend pytest -q \
  backend/tests/test_self_owned_rehearsal_controls.py::test_scope_or_policy_drift_rejects_stale_job_before_dispatch \
  backend/tests/test_worker_job_provenance.py \
  backend/tests/test_job_provenance_integration.py
```
Expected: all selected tests PASS; processor spy remains empty.

- [ ] **Step 3: If RED exposes a provenance ordering regression, fix verification ordering only**

Permitted minimal correction in `backend/app/worker_service.py`:

```python
job = _claim_for_role(queue, worker_id)
if not job:
    return False
try:
    _verify_policy_bound_job(job, store)  # must remain before any process_* dispatch
    with _lease_heartbeat(...):
        ...
```

Do not move verification into individual processors and do not permit stale jobs conditionally.

- [ ] **Step 4: Commit Task 7**

```bash
git add backend/tests/test_self_owned_rehearsal_controls.py backend/app/worker_service.py
git commit -m "test(rehearsal): prove stale provenance blocks dispatch"
```

Only stage `worker_service.py` if it changed.

---

### Task 8: Sentinel-secret confinement across persisted/public surfaces

**Files:**
- Modify: `backend/tests/test_self_owned_rehearsal_controls.py`
- Reuse: `backend/app/self_owned_rehearsal.py::contains_raw_value`
- No production change expected unless a real leak is discovered.

**Interfaces:**
- Consumes existing `secret_vault.set_secret`, `Storage` campaign/observation/artifact APIs, and queue payload inspection.
- Produces no new application interface.

- [ ] **Step 1: Add vault configuration helper and secret-confinement test**

```python
import base64

from app.secret_vault import set_secret
from app.self_owned_rehearsal import contains_raw_value


def _configure_vault(monkeypatch, tmp_path):
    monkeypatch.setenv("XBOW_VAULT_ENABLED", "true")
    monkeypatch.setenv(
        "XBOW_VAULT_MASTER_KEY",
        base64.urlsafe_b64encode(b"r" * 32).decode("ascii"),
    )
    monkeypatch.setenv("XBOW_VAULT_PATH", str(tmp_path / "rehearsal-vault.json"))


def test_secret_sentinel_never_escapes_vault_into_public_or_persisted_surfaces(tmp_path, monkeypatch):
    marker = "REHEARSAL-SENTINEL-7c44f1"
    _configure_vault(monkeypatch, tmp_path)
    set_secret("llm_api_key", marker)
    campaign, store, queue = _configured_campaign(tmp_path, monkeypatch, campaign_id="rehearsal-secret")

    observation = store.put_observation(
        campaign.id,
        {
            "id": "secret-check-observation",
            "kind": "evidence",
            "value": "redacted",
            "source": "self-owned-rehearsal",
            "metadata": {"secret_present": False},
        },
    )
    artifact = store.put_artifact(
        campaign.id,
        "validation",
        b'{"secret":"[redacted]"}',
        media_type="application/json",
        idempotency_key="rehearsal-secret-artifact",
    )
    job = queue.enqueue(
        campaign.id,
        "report",
        {"campaign_id": campaign.id, "platform": "generic"},
        max_attempts=1,
        dedupe_key="rehearsal-secret-job",
    )

    public_surfaces = [
        store.get_campaign(campaign.id),
        store.list_observations(campaign.id),
        observation,
        artifact,
        store.read_artifact(artifact["id"]),
        queue.get(job["id"]),
    ]
    assert contains_raw_value(marker, public_surfaces) is False
```

Use the actual `Storage.read_artifact` signature from `storage.py`. If it accepts `(campaign_id, artifact_id)` rather than one ID, call it with that exact signature; do not bypass storage integrity checks by opening artifact files directly.

- [ ] **Step 2: Add a positive-control assertion for the checker**

```python
assert contains_raw_value(marker, [{"accidental": marker}]) is True
```

This proves the scenario would fail if a raw secret actually appeared.

- [ ] **Step 3: Run secret/vault regressions**

Run:
```bash
PYTHONPATH=backend pytest -q \
  backend/tests/test_self_owned_rehearsal_controls.py \
  backend/tests/test_worker_secrets.py \
  backend/tests/test_secret_vault.py
```
Expected: all selected tests PASS.

- [ ] **Step 4: If a leak is found, fix the producing boundary rather than weakening the checker**

Allowed fix locations depend on the proven leak source:
- validation artifact leak -> `backend/app/validator.py` / validation persistence path;
- observation metadata leak -> `backend/app/observation_writer.py`;
- worker event leak -> `backend/app/worker_audit.py` / `worker_service.py`;
- queue payload leak -> payload construction call site.

The fix must replace/drop the secret before persistence. Do not merely omit that surface from the rehearsal.

- [ ] **Step 5: Commit Task 8**

```bash
git add backend/tests/test_self_owned_rehearsal_controls.py backend/app/validator.py backend/app/observation_writer.py backend/app/worker_audit.py backend/app/worker_service.py
git commit -m "test(rehearsal): enforce sentinel secret confinement"
```

Only stage files that actually changed.

---

### Task 9: Aggregate all eight scenarios into one deterministic rehearsal report

**Files:**
- Modify: `backend/tests/test_self_owned_rehearsal.py`
- Modify: `backend/app/self_owned_rehearsal.py` only for small reference/counter helpers proven necessary by the aggregate test.
- Reuse scenario helper functions from the three rehearsal integration test modules; if importing tests across modules becomes brittle, move only shared scenario builders into `backend/tests/rehearsal_scenarios.py` and keep assertions in the test files.

**Interfaces:**
- Consumes Task 1 `run_rehearsal` and all eight scenario runners.
- Produces one aggregate CI test `test_full_self_owned_rehearsal_report_passes_all_mandatory_scenarios`.

- [ ] **Step 1: Refactor each integration scenario into a callable returning `ScenarioResult` while keeping its direct test**

Each runner must return only stable codes/IDs/counters. Example shape:

```python
return ScenarioResult(
    name="http_429_bounded",
    status="pass" if result.http_status == 429 and len(server.requests) == 1 else "fail",
    reason="http_429_observed_once" if len(server.requests) == 1 else "http_429_request_count_mismatch",
    references=ScenarioReferences(
        campaign_id=campaign.id,
        counters={"requests_observed": len(server.requests)},
    ),
    external_network_used=bool(opener.blocked_hosts),
)
```

Do not put URLs, response bodies, exception text, policy receipts, or secrets in `reason`/references.

- [ ] **Step 2: Add the aggregate report test**

```python
from app.self_owned_rehearsal import MANDATORY_SCENARIOS, run_rehearsal


def test_full_self_owned_rehearsal_report_passes_all_mandatory_scenarios(rehearsal_scenarios):
    report = run_rehearsal(rehearsal_scenarios)
    assert report.status == "pass"
    assert [item.name for item in report.scenarios] == list(MANDATORY_SCENARIOS)
    assert all(item.status == "pass" for item in report.scenarios)
    assert report.external_network_used is False
    assert report.contains_secrets is False
```

Implement `rehearsal_scenarios` as a pytest fixture in `backend/tests/conftest.py` only if it can be built without hidden global state. Otherwise construct the mapping explicitly in this test using factory functions from `rehearsal_scenarios.py`.

- [ ] **Step 3: Add deterministic repeated-run assertion**

Run the scenario set twice with fresh temporary runtime factories and compare only semantic fields, not generated UUIDs:

```python
first = run_rehearsal(build_scenarios("run-a"))
second = run_rehearsal(build_scenarios("run-b"))
assert [(x.name, x.status, x.reason) for x in first.scenarios] == [
    (x.name, x.status, x.reason) for x in second.scenarios
]
```

This guards against wall-clock/random-order instability while allowing campaign/job IDs to differ.

- [ ] **Step 4: Run all rehearsal tests**

Run:
```bash
PYTHONPATH=backend:backend/tests pytest -q \
  backend/tests/test_rehearsal_fixture.py \
  backend/tests/test_self_owned_rehearsal.py \
  backend/tests/test_self_owned_rehearsal_http.py \
  backend/tests/test_self_owned_rehearsal_resilience.py \
  backend/tests/test_self_owned_rehearsal_controls.py
```
Expected: all rehearsal tests PASS, aggregate report status `pass`, external network false, contains secrets false.

- [ ] **Step 5: Commit Task 9**

```bash
git add backend/app/self_owned_rehearsal.py backend/tests/test_self_owned_rehearsal.py backend/tests/test_self_owned_rehearsal_http.py backend/tests/test_self_owned_rehearsal_resilience.py backend/tests/test_self_owned_rehearsal_controls.py backend/tests/rehearsal_scenarios.py backend/tests/conftest.py
git commit -m "test(rehearsal): aggregate self-owned campaign safety scenarios"
```

Stage `rehearsal_scenarios.py` / `conftest.py` only if created or modified.

---

### Task 10: Full regression, security, and CI verification

**Files:**
- No feature file change expected.
- Modify `.github/workflows/ci.yml` only if pytest discovery proves the rehearsal files are not executed by the current existing command; they should already be discovered.

**Interfaces:**
- Consumes the complete implementation.
- Produces verification evidence for PR review/merge.

- [ ] **Step 1: Run compile and lint exactly as CI does**

Run:
```bash
python -m compileall -q backend/app backend/tests
ruff check backend/app backend/tests
```
Expected: compile exits 0 and Ruff prints `All checks passed!`.

- [ ] **Step 2: Run the complete backend test suite with strict settings**

Run:
```bash
PYTHONPATH=backend pytest -q --strict-config --strict-markers backend/tests
```
Expected: all existing and new tests PASS. No rehearsal test may require public Internet access.

- [ ] **Step 3: Run package/readiness checks**

Run:
```bash
python -m pip check
PYTHONPATH=backend \
XBOW_DB_PATH=/tmp/xbow-rehearsal-readiness.sqlite3 \
XBOW_ARTIFACT_ROOT=/tmp/xbow-rehearsal-readiness-artifacts \
python -m app.readiness
pip-audit -r backend/requirements.txt
```
Expected: no broken requirements; readiness exits 0; dependency audit reports no known vulnerable installed requirements according to the repository's existing gate.

- [ ] **Step 4: Verify Docker/config build gates using existing CI commands**

Run:
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

- [ ] **Step 5: Inspect the final diff for forbidden capability expansion**

Run:
```bash
git diff main...HEAD -- backend/app backend/tests .github/workflows
```
Reviewer checklist:
- no new production endpoint for rehearsal;
- no scanner/PentAGI/browser activation;
- no new payload/fuzz/exploit logic;
- no redirect-following enablement;
- no generic retry loop for 429;
- no public DNS fallback in rehearsal fixture;
- provenance verification still precedes worker dispatch;
- raw secret values are not included in report/event additions.

- [ ] **Step 6: Commit any verification-only cleanup**

If formatting/import cleanup was needed:
```bash
git add backend/app backend/tests .github/workflows/ci.yml
git commit -m "chore(rehearsal): finalize CI verification"
```
If no files changed, do not create an empty commit.

- [ ] **Step 7: Open/update PR and require all repository workflows green before merge**

PR summary must state:
- rehearsal is loopback/in-memory only;
- eight scenarios covered;
- no new offensive execution capability;
- no production rehearsal endpoint;
- validator production defaults unchanged;
- exact pytest count from the final CI run;
- security and supply-chain workflow status.

Merge only after CI, security, and supply-chain are green on the exact final head SHA, then verify the corresponding `main` workflows on the merge SHA before declaring completion.
