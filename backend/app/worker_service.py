from __future__ import annotations

import os
import socket
import threading
import time
from contextlib import contextmanager
from pathlib import Path

from .browser import BrowserPolicyError, execute_browser_flow, persist_browser_result
from .jobqueue import JobQueue
from .main import Campaign, CampaignState, Finding, utcnow
from .report import render_markdown
from .storage import CampaignConflictError, Storage
from .validator import ValidationPolicyError, safe_http_probe
from .worker import (
    WorkerPolicyError,
    build_strix_plan,
    execute,
    locate_vulnerabilities_json,
    parse_strix_vulnerabilities,
    persist_execution_artifacts,
)


def _save(store: Storage, campaign: Campaign, version: int) -> int:
    campaign.updated_at = utcnow()
    return store.save_campaign(campaign.model_dump(mode="json"), expected_version=version)


def _campaign(store: Storage, campaign_id: str) -> tuple[Campaign, int]:
    record = store.get_campaign_record(campaign_id)
    if not record:
        raise KeyError(f"campaign {campaign_id} not found")
    raw, version = record
    return Campaign.model_validate(raw), version


def _append_event_once(campaign: Campaign, event: dict) -> None:
    event_type = event.get("type")
    job_id = event.get("job_id")
    if job_id and any(e.get("type") == event_type and e.get("job_id") == job_id for e in campaign.events):
        return
    campaign.events.append(event)


@contextmanager
def _lease_heartbeat(queue: JobQueue, job_id: str, worker_id: str):
    """Keep ownership of a long-running job without hiding lease loss."""
    lease_seconds = int(os.getenv("XBOW_JOB_LEASE_SECONDS", "21600"))
    interval = max(10.0, min(300.0, lease_seconds / 3))
    stop = threading.Event()
    lost = threading.Event()

    def renew() -> None:
        while not stop.wait(interval):
            try:
                if not queue.heartbeat(job_id, worker_id):
                    lost.set()
                    return
            except Exception:
                lost.set()
                return

    thread = threading.Thread(target=renew, name=f"lease-{job_id[:8]}", daemon=True)
    thread.start()
    try:
        yield
        if lost.is_set():
            raise RuntimeError("worker lost job lease during execution")
    finally:
        stop.set()
        thread.join(timeout=1.0)


def process_strix_scan(job: dict, queue: JobQueue, store: Storage) -> None:
    campaign, version = _campaign(store, job["campaign_id"])
    run_dir = str(Path(os.getenv("XBOW_STRIX_RUN_ROOT", "/data/strix_runs")) / job["id"])
    plan = build_strix_plan(campaign, run_dir)
    result = execute(plan)
    persist_execution_artifacts(store, campaign.id, result)

    if result["status"] == "dry_run":
        campaign.state = CampaignState.ready
        _append_event_once(campaign, {"type": "scan_dry_run", "job_id": job["id"], "at": utcnow()})
        _save(store, campaign, version)
        return
    if result["status"] != "completed":
        raise RuntimeError(result.get("stderr") or "Strix execution failed")

    vuln_path = locate_vulnerabilities_json(run_dir)
    findings: list[Finding] = parse_strix_vulnerabilities(vuln_path, campaign) if vuln_path else []
    existing = {f.id for f in campaign.findings}
    queued = 0
    for finding in findings:
        if finding.id in existing:
            continue
        campaign.findings.append(finding)
        queue.enqueue(
            campaign.id,
            "independent_validation",
            {"campaign_id": campaign.id, "finding_id": finding.id, "asset": finding.asset},
            max_attempts=2,
        )
        queued += 1
    campaign.state = CampaignState.validating if queued else CampaignState.completed
    _append_event_once(
        campaign,
        {"type": "strix_results_ingested", "job_id": job["id"], "findings": len(findings), "validation_jobs": queued, "at": utcnow()},
    )
    _save(store, campaign, version)


def process_validation(job: dict, store: Storage) -> None:
    """Capture independent read-only HTTP evidence without self-confirming findings."""
    campaign, version = _campaign(store, job["campaign_id"])
    finding_id = str(job["payload"].get("finding_id") or "")
    finding = next((f for f in campaign.findings if f.id == finding_id), None)
    if not finding:
        raise KeyError(f"finding {finding_id} not found")
    if finding.discovered_by == "independent-http-validator":
        raise ValidationPolicyError("discovery agent cannot validate its own finding")

    result = safe_http_probe(campaign, finding)
    artifact = store.put_artifact(
        campaign.id,
        "validation",
        result.json_bytes(),
        media_type="application/json",
        finding_id=finding.id,
        idempotency_key=f"{job['id']}:validation",
    )
    _append_event_once(
        campaign,
        {
            "type": "independent_validation_observation",
            "finding_id": finding.id,
            "job_id": job["id"],
            "validator": "independent-http-validator",
            "probe_status": result.status,
            "http_status": result.http_status,
            "artifact_id": artifact["id"],
            "at": utcnow(),
        },
    )

    finding.status = "validation_required"
    if result.status == "error":
        _append_event_once(
            campaign,
            {
                "type": "independent_validation_error",
                "finding_id": finding.id,
                "job_id": job["id"],
                "error": result.error,
                "at": utcnow(),
            },
        )
    _save(store, campaign, version)


def process_browser_flow(job: dict, store: Storage) -> None:
    campaign, version = _campaign(store, job["campaign_id"])
    result = execute_browser_flow(campaign, job["payload"])
    artifacts = persist_browser_result(store, campaign.id, result)
    _append_event_once(
        campaign,
        {
            "type": "browser_flow_completed" if result.status == "completed" else "browser_flow_dry_run",
            "job_id": job["id"],
            "status": result.status,
            "artifact_ids": [artifact["id"] for artifact in artifacts],
            "at": utcnow(),
        },
    )
    _save(store, campaign, version)


def process_report(job: dict, store: Storage) -> None:
    campaign, version = _campaign(store, job["campaign_id"])
    platform = str(job.get("payload", {}).get("platform") or "generic")
    if platform not in {"generic", "hackerone", "bugcrowd"}:
        raise ValueError("unsupported report platform")
    report = render_markdown(campaign, platform=platform).encode("utf-8")
    artifact = store.put_artifact(
        campaign.id,
        "report",
        report,
        media_type="text/markdown",
        idempotency_key=f"{job['id']}:report:{platform}",
    )
    _append_event_once(
        campaign,
        {
            "type": "report_generated",
            "job_id": job["id"],
            "platform": platform,
            "artifact_id": artifact["id"],
            "at": utcnow(),
        },
    )
    _save(store, campaign, version)


def process_one(queue: JobQueue, store: Storage, worker_id: str) -> bool:
    job = queue.claim(worker_id)
    if not job:
        return False
    try:
        with _lease_heartbeat(queue, job["id"], worker_id):
            if job["kind"] == "strix_scan":
                process_strix_scan(job, queue, store)
            elif job["kind"] == "independent_validation":
                process_validation(job, store)
            elif job["kind"] == "browser_flow":
                process_browser_flow(job, store)
            elif job["kind"] == "report":
                process_report(job, store)
            else:
                raise ValueError("unsupported job kind")
    except CampaignConflictError as exc:
        queue.finish(job["id"], worker_id, False, f"campaign state changed concurrently: {exc}")
    except (WorkerPolicyError, ValidationPolicyError, BrowserPolicyError, ValueError, KeyError) as exc:
        queue.finish(job["id"], worker_id, False, str(exc))
    except Exception as exc:
        queue.finish(job["id"], worker_id, False, str(exc))
    else:
        queue.finish(job["id"], worker_id, True)
    return True


def main() -> None:
    queue = JobQueue()
    store = Storage()
    worker_id = os.getenv("XBOW_WORKER_ID", f"{socket.gethostname()}:{os.getpid()}")
    poll = max(0.2, float(os.getenv("XBOW_WORKER_POLL_SECONDS", "1")))
    while True:
        worked = process_one(queue, store, worker_id)
        if not worked:
            time.sleep(poll)


if __name__ == "__main__":
    main()
