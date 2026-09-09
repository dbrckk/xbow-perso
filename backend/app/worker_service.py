from __future__ import annotations

import os
import socket
import time
from pathlib import Path

from .browser import BrowserPolicyError, execute_browser_flow, persist_browser_result
from .jobqueue import JobQueue
from .main import Campaign, CampaignState, Finding, utcnow
from .report import render_markdown
from .storage import Storage
from .validator import ValidationPolicyError, safe_http_probe
from .worker import (
    WorkerPolicyError,
    build_strix_plan,
    execute,
    locate_vulnerabilities_json,
    parse_strix_vulnerabilities,
    persist_execution_artifacts,
)


def _save(store: Storage, campaign: Campaign) -> None:
    campaign.updated_at = utcnow()
    store.save_campaign(campaign.model_dump(mode="json"))


def _campaign(store: Storage, campaign_id: str) -> Campaign:
    raw = store.get_campaign(campaign_id)
    if not raw:
        raise KeyError(f"campaign {campaign_id} not found")
    return Campaign.model_validate(raw)


def process_strix_scan(job: dict, queue: JobQueue, store: Storage) -> None:
    campaign = _campaign(store, job["campaign_id"])
    run_dir = str(Path(os.getenv("XBOW_STRIX_RUN_ROOT", "/data/strix_runs")) / job["id"])
    plan = build_strix_plan(campaign, run_dir)
    result = execute(plan)
    persist_execution_artifacts(store, campaign.id, result)

    if result["status"] == "dry_run":
        campaign.state = CampaignState.ready
        campaign.events.append({"type": "scan_dry_run", "job_id": job["id"], "at": utcnow()})
        _save(store, campaign)
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
    campaign.events.append(
        {"type": "strix_results_ingested", "job_id": job["id"], "findings": len(findings), "validation_jobs": queued, "at": utcnow()}
    )
    _save(store, campaign)


def process_validation(job: dict, store: Storage) -> None:
    """Capture independent read-only HTTP evidence without self-confirming findings."""
    campaign = _campaign(store, job["campaign_id"])
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
    )
    event = {
        "type": "independent_validation_observation",
        "finding_id": finding.id,
        "job_id": job["id"],
        "validator": "independent-http-validator",
        "probe_status": result.status,
        "http_status": result.http_status,
        "artifact_id": artifact["id"],
        "at": utcnow(),
    }
    campaign.events.append(event)

    # A network observation is evidence, not a vulnerability verdict. Promotion to
    # confirmed still requires an independent semantic validator or explicit review.
    finding.status = "validation_required"
    if result.status == "error":
        campaign.events.append(
            {
                "type": "independent_validation_error",
                "finding_id": finding.id,
                "job_id": job["id"],
                "error": result.error,
                "at": utcnow(),
            }
        )
    _save(store, campaign)


def process_browser_flow(job: dict, store: Storage) -> None:
    campaign = _campaign(store, job["campaign_id"])
    result = execute_browser_flow(campaign, job["payload"])
    artifacts = persist_browser_result(store, campaign.id, result)
    campaign.events.append(
        {
            "type": "browser_flow_completed" if result.status == "completed" else "browser_flow_dry_run",
            "job_id": job["id"],
            "status": result.status,
            "artifact_ids": [artifact["id"] for artifact in artifacts],
            "at": utcnow(),
        }
    )
    _save(store, campaign)


def process_report(job: dict, store: Storage) -> None:
    campaign = _campaign(store, job["campaign_id"])
    platform = str(job.get("payload", {}).get("platform") or "generic")
    if platform not in {"generic", "hackerone", "bugcrowd"}:
        raise ValueError("unsupported report platform")
    report = render_markdown(campaign, platform=platform).encode("utf-8")
    artifact = store.put_artifact(campaign.id, "report", report, media_type="text/markdown")
    campaign.events.append(
        {
            "type": "report_generated",
            "job_id": job["id"],
            "platform": platform,
            "artifact_id": artifact["id"],
            "at": utcnow(),
        }
    )
    _save(store, campaign)


def process_one(queue: JobQueue, store: Storage, worker_id: str) -> bool:
    job = queue.claim(worker_id)
    if not job:
        return False
    try:
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
    except (WorkerPolicyError, ValidationPolicyError, BrowserPolicyError, ValueError, KeyError) as exc:
        queue.finish(job["id"], False, str(exc))
    except Exception as exc:
        queue.finish(job["id"], False, str(exc))
    else:
        queue.finish(job["id"], True)
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
