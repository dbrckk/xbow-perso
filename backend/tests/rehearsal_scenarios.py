from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException

from app import main, worker_service
from app.campaign_audit import append_campaign_event
from app.job_provenance import attach_job_provenance
from app.jobqueue import JobQueue
from app.main import Campaign, CampaignState, Finding, ProgramRules, TargetInput
from app.self_owned_rehearsal import ScenarioReferences, ScenarioResult
from app.storage import Storage
from app.validator import ValidationPolicyError, safe_http_probe
from rehearsal_fixture import LocalRehearsalServer, MappedLoopbackOpener


def _http_campaign() -> Campaign:
    return Campaign(
        id="self-owned-http-rehearsal",
        target=TargetInput(
            name="Self-owned rehearsal fixture",
            primary_url="http://allowed.rehearsal.test/ok",
            rules=ProgramRules(
                authorization_reference="self-owned-rehearsal",
                allowed_targets=[
                    "allowed.rehearsal.test",
                    "*.allowed.rehearsal.test",
                ],
                denied_targets=["denied.allowed.rehearsal.test"],
                max_requests_per_second=2.0,
            ),
        ),
    )


def _durable_campaign(campaign_id: str) -> Campaign:
    return Campaign(
        id=campaign_id,
        state=CampaignState.ready,
        target=TargetInput(
            name="Self-owned durable rehearsal",
            primary_url="https://example.test",
            rules=ProgramRules(
                authorization_reference="self-owned-rehearsal",
                allowed_targets=["example.test"],
                max_requests_per_second=2.0,
            ),
        ),
    )


def _finding(endpoint: str) -> Finding:
    return Finding(
        id="self-owned-http-finding",
        title="Rehearsal candidate",
        severity="info",
        asset="http://allowed.rehearsal.test",
        endpoint=endpoint,
        summary="Deterministic local rehearsal candidate",
        discovered_by="rehearsal",
    )


def _enable_http(monkeypatch) -> None:
    monkeypatch.setenv("XBOW_ENABLE_HTTP_VALIDATION", "true")
    monkeypatch.setenv("XBOW_ENABLE_DIFFERENTIAL_VALIDATION", "false")
    monkeypatch.setenv("XBOW_VALIDATION_TIMEOUT_SECONDS", "1")
    monkeypatch.setenv("XBOW_VALIDATION_MAX_BYTES", "1024")


def run_redirect_scope_scenario(root, monkeypatch) -> ScenarioResult:
    del root
    _enable_http(monkeypatch)
    campaign = _http_campaign()
    with LocalRehearsalServer() as server:
        opener = MappedLoopbackOpener(
            {"allowed.rehearsal.test": ("127.0.0.1", server.port)}
        )
        in_scope = safe_http_probe(
            campaign,
            _finding("http://allowed.rehearsal.test/redirect-in-scope"),
            opener=opener,
        )
        out_of_scope = safe_http_probe(
            campaign,
            _finding("http://allowed.rehearsal.test/redirect-out-of-scope"),
            opener=opener,
        )
        requests_observed = len(server.requests)
        valid = (
            in_scope.status == "observed"
            and in_scope.http_status == 302
            and out_of_scope.status == "observed"
            and out_of_scope.http_status == 302
            and requests_observed == 2
            and opener.blocked_hosts == []
        )
    return ScenarioResult(
        name="redirect_scope_enforcement",
        status="pass" if valid else "fail",
        reason=(
            "redirects_observed_without_followup"
            if valid
            else "redirect_followup_invariant_failed"
        ),
        references=ScenarioReferences(
            campaign_id=campaign.id,
            counters={"requests_observed": requests_observed},
        ),
    )


def run_subdomain_scope_scenario(root, monkeypatch) -> ScenarioResult:
    del root
    _enable_http(monkeypatch)
    campaign = _http_campaign()
    denied_blocked = False
    with LocalRehearsalServer() as server:
        opener = MappedLoopbackOpener(
            {"api.allowed.rehearsal.test": ("127.0.0.1", server.port)}
        )
        allowed = safe_http_probe(
            campaign,
            _finding("http://api.allowed.rehearsal.test/ok"),
            opener=opener,
        )
        try:
            safe_http_probe(
                campaign,
                _finding("http://denied.allowed.rehearsal.test/ok"),
                opener=opener,
            )
        except ValidationPolicyError as exc:
            denied_blocked = str(exc) == "validation URL is outside declared scope"
        requests_observed = len(server.requests)
        valid = (
            allowed.status == "observed"
            and allowed.http_status == 200
            and denied_blocked
            and requests_observed == 1
            and opener.blocked_hosts == []
        )
    return ScenarioResult(
        name="subdomain_scope_enforcement",
        status="pass" if valid else "fail",
        reason=(
            "denied_host_blocked_before_transport"
            if valid
            else "subdomain_scope_invariant_failed"
        ),
        references=ScenarioReferences(
            campaign_id=campaign.id,
            counters={"requests_observed": requests_observed},
        ),
    )


def run_http_429_scenario(root, monkeypatch) -> ScenarioResult:
    del root
    _enable_http(monkeypatch)
    campaign = _http_campaign()
    with LocalRehearsalServer() as server:
        opener = MappedLoopbackOpener(
            {"allowed.rehearsal.test": ("127.0.0.1", server.port)}
        )
        result = safe_http_probe(
            campaign,
            _finding("http://allowed.rehearsal.test/throttle"),
            opener=opener,
        )
        requests_observed = len(server.requests)
        valid = (
            result.status == "observed"
            and result.http_status == 429
            and requests_observed == 1
            and opener.blocked_hosts == []
        )
    return ScenarioResult(
        name="http_429_bounded",
        status="pass" if valid else "fail",
        reason="http_429_observed_once" if valid else "http_429_invariant_failed",
        references=ScenarioReferences(
            campaign_id=campaign.id,
            counters={"requests_observed": requests_observed},
        ),
    )


def run_worker_failure_scenario(root, monkeypatch) -> ScenarioResult:
    db_path = str(root / "worker-failure.sqlite3")
    artifact_root = str(root / "worker-failure-artifacts")
    monkeypatch.setenv("XBOW_DB_PATH", db_path)
    monkeypatch.setenv("XBOW_ARTIFACT_ROOT", artifact_root)
    monkeypatch.setenv("XBOW_JOB_LEASE_SECONDS", "60")
    monkeypatch.delenv("XBOW_WORKER_ROLE", raising=False)

    store = Storage(db_path, artifact_root)
    queue = JobQueue(db_path)
    campaign = _durable_campaign("self-owned-worker-failure")
    store.save_campaign(campaign.model_dump(mode="json"), expected_version=0)

    payload = attach_job_provenance(
        {"campaign_id": campaign.id, "platform": "generic"},
        campaign,
        job_kind="report",
        action="report",
    )
    job = queue.enqueue(
        campaign.id,
        "report",
        payload,
        max_attempts=2,
        dedupe_key="rehearsal-worker-failure",
    )
    first_claim = queue.claim("worker-crashed")
    if first_claim is None or first_claim["id"] != job["id"]:
        return ScenarioResult(
            name="worker_failure_durability",
            status="fail",
            reason="initial_claim_failed",
        )

    expired_at = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    with queue.connect() as conn:
        conn.execute(
            "UPDATE jobs SET claimed_at=?, updated_at=? WHERE id=?",
            (expired_at, expired_at, job["id"]),
        )

    if queue.recover_expired_leases() != 1:
        return ScenarioResult(
            name="worker_failure_durability",
            status="fail",
            reason="lease_not_requeued",
            references=ScenarioReferences(campaign_id=campaign.id, job_ids=(job["id"],)),
        )

    recovered = queue.get(job["id"])
    if recovered is None or recovered["status"] != "queued":
        return ScenarioResult(
            name="worker_failure_durability",
            status="fail",
            reason="lease_not_requeued",
            references=ScenarioReferences(campaign_id=campaign.id, job_ids=(job["id"],)),
        )

    def injected_failure(_job, _store):
        raise RuntimeError("injected-rehearsal-failure")

    monkeypatch.setattr(worker_service, "process_report", injected_failure)
    monkeypatch.setattr(
        worker_service,
        "advance_campaign",
        lambda campaign, queue, store: {"action": {"kind": "stop"}},
    )

    worker_service.process_one(queue, store, "worker-retry")
    final = queue.get(job["id"])
    persisted = store.get_campaign(campaign.id) or {}
    successful_outcomes = sum(
        1
        for event in persisted.get("events", [])
        if event.get("type") == "worker_outcome"
        and event.get("job_id") == job["id"]
        and event.get("success") is True
    )
    attempts = int(final["attempts"]) if final is not None else -1

    if final is None or final["status"] != "failed" or attempts != 2:
        reason = "attempt_limit_mismatch"
        valid = False
    elif successful_outcomes != 0:
        reason = "false_success_recorded"
        valid = False
    else:
        reason = "expired_lease_recovered_then_failed_at_attempt_limit"
        valid = True

    return ScenarioResult(
        name="worker_failure_durability",
        status="pass" if valid else "fail",
        reason=reason,
        references=ScenarioReferences(
            campaign_id=campaign.id,
            job_ids=(job["id"],),
            counters={
                "attempts": attempts,
                "successful_outcomes": successful_outcomes,
            },
        ),
    )


def run_outbox_recovery_scenario(root, monkeypatch) -> ScenarioResult:
    db_path = str(root / "outbox.sqlite3")
    artifact_root = str(root / "outbox-artifacts")
    monkeypatch.setenv("XBOW_DB_PATH", db_path)
    monkeypatch.setenv("XBOW_ARTIFACT_ROOT", artifact_root)

    store = Storage(db_path, artifact_root)
    queue = JobQueue(db_path)

    campaign = _durable_campaign("self-owned-outbox-repair")
    campaign.state = CampaignState.running
    request_id = "rehearsal-report-after-enqueue"
    append_campaign_event(
        campaign.events,
        {
            "type": "report_requested",
            "request_id": request_id,
            "platform": "generic",
            "purpose": "manual",
            "at": main.utcnow(),
        },
    )
    store.save_campaign(campaign.model_dump(mode="json"), expected_version=0)

    existing = queue.enqueue(
        campaign.id,
        "report",
        {"campaign_id": campaign.id, "platform": "generic"},
        max_attempts=2,
        dedupe_key=f"report:generic:{request_id}",
    )
    jobs_before = int(queue.stats()["total"])
    repair = main.reconcile_campaign_outbox_local(campaign.id)
    jobs_after_repair = int(queue.stats()["total"])
    persisted = store.get_campaign(campaign.id) or {}
    queued_events = [
        event
        for event in persisted.get("events", [])
        if event.get("type") == "report_queued"
        and event.get("request_id") == request_id
    ]

    missing = _durable_campaign("self-owned-outbox-missing")
    missing.state = CampaignState.validating
    append_campaign_event(
        missing.events,
        {
            "type": "validation_requested",
            "request_id": "validation:missing-rehearsal",
            "finding_id": "missing-rehearsal",
            "at": main.utcnow(),
        },
    )
    store.save_campaign(missing.model_dump(mode="json"), expected_version=0)
    missing_result = main.reconcile_campaign_outbox_local(missing.id)
    jobs_after = int(queue.stats()["total"])

    repaired_events = int(repair.get("repaired", 0))
    valid = (
        jobs_before == 1
        and jobs_after_repair == 1
        and jobs_after == 1
        and repaired_events == 1
        and repair.get("remaining") == []
        and len(queued_events) == 1
        and queued_events[0].get("job_id") == existing["id"]
        and queued_events[0].get("reconciled_locally") is True
        and missing_result.get("repaired") == 0
        and bool(missing_result.get("remaining"))
        and missing_result["remaining"][0].get("diagnosis") == "job_missing"
        and missing_result.get("automatic_job_creation") is False
    )
    return ScenarioResult(
        name="crash_window_outbox_recovery",
        status="pass" if valid else "fail",
        reason=(
            "audit_reconciled_without_job_recreation"
            if valid
            else "outbox_recovery_invariant_failed"
        ),
        references=ScenarioReferences(
            campaign_id=campaign.id,
            job_ids=(existing["id"],),
            event_types=("report_requested", "report_queued"),
            counters={
                "jobs_before": jobs_before,
                "jobs_after": jobs_after,
                "repaired_events": repaired_events,
            },
        ),
    )


def run_cancellation_scenario(root, monkeypatch) -> ScenarioResult:
    db_path = str(root / "cancel.sqlite3")
    artifact_root = str(root / "cancel-artifacts")
    monkeypatch.setenv("XBOW_DB_PATH", db_path)
    monkeypatch.setenv("XBOW_ARTIFACT_ROOT", artifact_root)

    store = Storage(db_path, artifact_root)
    queue = JobQueue(db_path)
    campaign = _durable_campaign("self-owned-cancellation")
    campaign.state = CampaignState.running
    store.save_campaign(campaign.model_dump(mode="json"), expected_version=0)

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
    claimed = queue.claim("worker-cancel-rehearsal")
    if claimed is None or claimed["id"] != running["id"]:
        return ScenarioResult(
            name="cancellation_enforcement",
            status="fail",
            reason="running_job_claim_failed",
        )

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
    before_admission = int(queue.stats()["total"])
    cancelled = main.cancel_campaign(campaign.id)

    admission_blocked = False
    try:
        main.queue_report(campaign.id)
    except HTTPException as exc:
        admission_blocked = exc.status_code == 409 and "cancelled" in str(exc.detail).lower()
    after_admission = int(queue.stats()["total"])

    running_final = queue.get(running["id"])
    queued_final = queue.get(queued["id"])
    persisted = store.get_campaign(campaign.id) or {}
    post_cancel_admissions = max(0, after_admission - before_admission)
    valid = (
        cancelled.get("state") == CampaignState.cancelled
        and cancelled.get("cancelled_queued_jobs") == 1
        and cancelled.get("running_jobs") == 1
        and cancelled.get("running_jobs_not_forcibly_terminated") is True
        and running_final is not None
        and running_final.get("status") == "running"
        and queued_final is not None
        and queued_final.get("status") == "cancelled"
        and persisted.get("state") == "cancelled"
        and admission_blocked
        and post_cancel_admissions == 0
    )
    return ScenarioResult(
        name="cancellation_enforcement",
        status="pass" if valid else "fail",
        reason=(
            "queued_cancelled_running_reported_new_work_blocked"
            if valid
            else "cancellation_invariant_failed"
        ),
        references=ScenarioReferences(
            campaign_id=campaign.id,
            job_ids=(running["id"], queued["id"]),
            event_types=("campaign_cancelled",),
            counters={
                "queued_cancelled": int(cancelled.get("cancelled_queued_jobs", -1)),
                "running_jobs": int(cancelled.get("running_jobs", -1)),
                "post_cancel_admissions": post_cancel_admissions,
            },
        ),
    )
