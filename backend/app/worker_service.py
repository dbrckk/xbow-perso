from __future__ import annotations

import hashlib
import os
import socket
import threading
import time
from contextlib import contextmanager

from .browser import BrowserPolicyError, execute_browser_flow, persist_browser_result
from .jobqueue import JobQueue
from .main import Campaign, CampaignState, Finding, utcnow
from .observation_graph import Observation
from .orchestrator import advance_campaign
from .recon_worker import ReconPolicyError, execute_recon_task
from .scanner_worker import run_strix_job
from .report import render_markdown
from .storage import CampaignConflictError, Storage
from .validator import ValidationPolicyError, safe_http_probe
from .worker import WorkerPolicyError


class CampaignCancelledError(ValueError):
    pass


def _save(store: Storage, campaign: Campaign, version: int) -> int:
    campaign.updated_at = utcnow()
    return store.save_campaign(campaign.model_dump(mode="json"), expected_version=version)


def _campaign(store: Storage, campaign_id: str) -> tuple[Campaign, int]:
    record = store.get_campaign_record(campaign_id)
    if not record:
        raise KeyError(f"campaign {campaign_id} not found")
    raw, version = record
    campaign = Campaign.model_validate(raw)
    if campaign.state == CampaignState.cancelled:
        raise CampaignCancelledError("campaign is cancelled")
    return campaign, version


def _append_event_once(campaign: Campaign, event: dict) -> None:
    event_type = event.get("type")
    job_id = event.get("job_id")
    if job_id and any(e.get("type") == event_type and e.get("job_id") == job_id for e in campaign.events):
        return
    campaign.events.append(event)


def _observation_id(prefix: str, value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]
    return f"{prefix}:{digest}"


def _record_asset_observation(store: Storage, campaign: Campaign, asset: str, source: str) -> str:
    observation = Observation(
        id=_observation_id("asset", f"{source}\x1f{asset}"),
        kind="asset",
        value=asset,
        source=source,
    )
    store.put_observation(campaign.id, observation.to_dict())
    return observation.id


def _record_endpoint_observation(
    store: Storage,
    campaign: Campaign,
    endpoint: str,
    *,
    source: str,
    parent_id: str,
) -> str:
    observation = Observation(
        id=_observation_id("endpoint", f"{source}\x1f{endpoint}"),
        kind="endpoint",
        value=endpoint,
        source=source,
        parent_ids=(parent_id,),
    )
    store.put_observation(campaign.id, observation.to_dict())
    return observation.id


def _record_finding_observation(store: Storage, campaign: Campaign, finding: Finding) -> str:
    asset_id = _record_asset_observation(
        store,
        campaign,
        finding.asset,
        finding.discovered_by,
    )
    parent_id = asset_id
    if finding.endpoint:
        endpoint_value = str(finding.endpoint)
        if endpoint_value.startswith("/"):
            endpoint_value = str(finding.asset).rstrip("/") + endpoint_value
        parent_id = _record_endpoint_observation(
            store,
            campaign,
            endpoint_value,
            source=finding.discovered_by,
            parent_id=asset_id,
        )

    observation = Observation(
        id=f"finding:{finding.id}",
        kind="finding",
        value=finding.id,
        source=finding.discovered_by,
        parent_ids=(parent_id,),
        metadata={
            "title": finding.title,
            "severity": finding.severity,
            "endpoint": finding.endpoint,
            "cwe": finding.cwe,
            "cvss": finding.cvss,
        },
    )
    store.put_observation(campaign.id, observation.to_dict())

    for index, evidence in enumerate(finding.evidence[:50], start=1):
        evidence_observation = Observation(
            id=_observation_id(
                "evidence",
                f"{finding.discovered_by}\x1f{finding.id}\x1f{index}\x1f{evidence}",
            ),
            kind="evidence",
            value=str(evidence),
            source=finding.discovered_by,
            parent_ids=(observation.id,),
            metadata={
                "finding_id": finding.id,
                "scanner_evidence": True,
                "ordinal": index,
            },
        )
        store.put_observation(campaign.id, evidence_observation.to_dict())

    return observation.id


def _record_artifact_observation(
    store: Storage,
    campaign: Campaign,
    artifact: dict,
    *,
    source: str,
    parent_ids: tuple[str, ...] = (),
    kind: str = "evidence",
    value: str | None = None,
    metadata: dict | None = None,
) -> str:
    observation = Observation(
        id=f"{kind}:{artifact['id']}",
        kind=kind,
        value=value or artifact["id"],
        source=source,
        parent_ids=parent_ids,
        metadata={"artifact_id": artifact["id"], **(metadata or {})},
    )
    store.put_observation(campaign.id, observation.to_dict())
    return observation.id


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
    result = run_strix_job(job, campaign, queue, store)
    _append_event_once(campaign, result.event)
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

    finding_observation_id = _record_finding_observation(store, campaign, finding)
    result = safe_http_probe(campaign, finding)
    artifact = store.put_artifact(
        campaign.id,
        "validation",
        result.json_bytes(),
        media_type="application/json",
        finding_id=finding.id,
        idempotency_key=f"{job['id']}:validation",
    )
    validation_observation_id = _record_artifact_observation(
        store,
        campaign,
        artifact,
        source="independent-http-validator",
        parent_ids=(finding_observation_id,),
        kind="validation",
        value=result.status,
        metadata={"http_status": result.http_status, "finding_id": finding.id},
    )
    _record_artifact_observation(
        store,
        campaign,
        artifact,
        source="independent-http-validator",
        parent_ids=(validation_observation_id,),
        metadata={"artifact_kind": "validation", "finding_id": finding.id},
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
    asset_id = _record_asset_observation(store, campaign, str(campaign.target.primary_url), "browser")
    result = execute_browser_flow(campaign, job["payload"])
    artifacts = persist_browser_result(store, campaign.id, result, idempotency_prefix=job["id"])
    for observation in result.observations:
        operation = observation.get("operation")
        if operation == "navigate" and observation.get("url"):
            _record_endpoint_observation(
                store,
                campaign,
                str(observation["url"]),
                source="browser",
                parent_id=asset_id,
            )
        elif operation == "surface_links":
            for endpoint in observation.get("urls", [])[:100]:
                _record_endpoint_observation(
                    store,
                    campaign,
                    str(endpoint),
                    source="browser",
                    parent_id=asset_id,
                )
        elif operation == "surface_forms":
            for form in observation.get("forms", [])[:50]:
                action = str(form.get("action") or "")
                if not action:
                    continue
                form_observation = Observation(
                    id=_observation_id(
                        "form",
                        f"browser\x1f{action}\x1f{form.get('method', 'GET')}\x1f"
                        + ",".join(str(name) for name in form.get("input_names", [])),
                    ),
                    kind="form",
                    value=action,
                    source="browser",
                    parent_ids=(asset_id,),
                    metadata={
                        "method": str(form.get("method") or "GET"),
                        "input_names": list(form.get("input_names", []))[:100],
                    },
                )
                store.put_observation(campaign.id, form_observation.to_dict())
        elif operation == "surface_technologies":
            for technology in observation.get("technologies", [])[:20]:
                technology_observation = Observation(
                    id=_observation_id("technology", f"browser\x1f{technology}"),
                    kind="technology",
                    value=str(technology),
                    source="browser",
                    parent_ids=(asset_id,),
                )
                store.put_observation(campaign.id, technology_observation.to_dict())
    for artifact in artifacts:
        _record_artifact_observation(
            store,
            campaign,
            artifact,
            source="browser",
            parent_ids=(asset_id,),
            metadata={"browser_status": result.status},
        )
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


def process_recon_task(job: dict, store: Storage) -> None:
    campaign, version = _campaign(store, job["campaign_id"])
    result = execute_recon_task(campaign, job["payload"])
    source = f"recon:{job['payload'].get('kind', 'unknown')}"
    asset_id = _record_asset_observation(
        store,
        campaign,
        str(campaign.target.primary_url),
        source,
    )

    for endpoint in result.endpoints:
        _record_endpoint_observation(
            store,
            campaign,
            endpoint,
            source=source,
            parent_id=asset_id,
        )

    for form in result.forms:
        observation = Observation(
            id=_observation_id("form", f"{source}\x1f{form['action']}\x1f{','.join(form['input_names'])}"),
            kind="form",
            value=form["action"],
            source=source,
            parent_ids=(asset_id,),
            metadata={
                "method": form["method"],
                "input_names": form["input_names"],
            },
        )
        store.put_observation(campaign.id, observation.to_dict())

    for technology in result.technologies:
        observation = Observation(
            id=_observation_id("technology", f"{source}\x1f{technology}"),
            kind="technology",
            value=technology,
            source=source,
            parent_ids=(asset_id,),
        )
        store.put_observation(campaign.id, observation.to_dict())

    for waf in result.waf:
        observation = Observation(
            id=_observation_id("waf", f"{source}\x1f{waf}"),
            kind="waf",
            value=waf,
            source=source,
            parent_ids=(asset_id,),
        )
        store.put_observation(campaign.id, observation.to_dict())

    _append_event_once(
        campaign,
        {
            "type": "recon_task_completed" if result.status == "observed" else "recon_task_dry_run",
            "job_id": job["id"],
            "task_kind": job["payload"].get("kind"),
            "status": result.status,
            "http_status": result.http_status,
            "endpoints": len(result.endpoints),
            "forms": len(result.forms),
            "technologies": len(result.technologies),
            "waf": len(result.waf),
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
    _record_artifact_observation(
        store,
        campaign,
        artifact,
        source="report-engine",
        metadata={"platform": platform, "artifact_kind": "report"},
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
            elif job["kind"] == "recon_task":
                process_recon_task(job, store)
            elif job["kind"] == "report":
                process_report(job, store)
            else:
                raise ValueError("unsupported job kind")

            latest_campaign, _ = _campaign(store, job["campaign_id"])
            advance_campaign(latest_campaign, queue, store)
    except CampaignCancelledError as exc:
        queue.cancel_owned(job["id"], worker_id, str(exc))
    except CampaignConflictError as exc:
        queue.finish(job["id"], worker_id, False, f"campaign state changed concurrently: {exc}")
    except (WorkerPolicyError, ValidationPolicyError, BrowserPolicyError, ReconPolicyError, ValueError, KeyError) as exc:
        queue.finish(job["id"], worker_id, False, str(exc))
    except Exception as exc:
        queue.finish(job["id"], worker_id, False, str(exc))
    else:
        queue.finish(job["id"], worker_id, True)
    return True


def _worker_poll_seconds() -> float:
    raw = os.getenv("XBOW_WORKER_POLL_SECONDS", "1")
    try:
        poll = float(raw)
    except ValueError as exc:
        raise ValueError("XBOW_WORKER_POLL_SECONDS must be a number") from exc
    if not 0.2 <= poll <= 60.0:
        raise ValueError("XBOW_WORKER_POLL_SECONDS must be between 0.2 and 60")
    return poll


def main() -> None:
    queue = JobQueue()
    store = Storage()
    worker_id = os.getenv("XBOW_WORKER_ID", f"{socket.gethostname()}:{os.getpid()}")
    poll = _worker_poll_seconds()
    while True:
        worked = process_one(queue, store, worker_id)
        if not worked:
            time.sleep(poll)


if __name__ == "__main__":
    main()
