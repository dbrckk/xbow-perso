from __future__ import annotations

import os
import socket
import threading
import time
from contextlib import contextmanager

from .browser import BrowserPolicyError, execute_browser_flow, persist_browser_result
from .campaign_audit import append_campaign_event
from .evidence_quality import build_evidence_quality
from .hackerone_batch import reconcile_hackerone_batches
from .hackerone_catalog import maybe_refresh_hackerone_catalog
from .hackerone_intelligence import maybe_refresh_hackerone_intelligence
from .github_learning_sync import sync_completed_learning_batches
from .job_provenance import (
    JobProvenanceError,
    provenance_required_for_job_kind,
    require_job_provenance,
)
from .jobqueue import JobQueue
from .learning_memory import worker_outcome_event
from .queue_backend import create_queue
from .main import Campaign, CampaignState, utcnow
from .observation_graph import ObservationGraph
from .observation_writer import (
    observation_id,
    record_artifact,
    record_asset,
    record_endpoint,
    record_finding_chain,
    record_typed_child,
)
from .orchestrator import advance_campaign
from .planner_lock import campaign_planner_lock
from .recon_worker import ReconPolicyError, execute_recon_task
from .scanner_worker import _state_after_scan as _scanner_state_after_scan, run_nuclei_job, run_strix_job
from .report import render_markdown
from .storage import CampaignConflictError, Storage
from .storage_backend import create_storage
from .validator import ValidationPolicyError, safe_http_probe
from .worker import WorkerPolicyError
from .worker_audit import seal_worker_outcome_event
from .worker_liveness import start_worker_heartbeat


class CampaignCancelledError(ValueError):
    pass


class StaleValidationJobError(ValidationPolicyError):
    pass


class StaleBrowserJobError(BrowserPolicyError):
    pass


# Backward-compatible re-export for existing imports/tests.
_state_after_scan = _scanner_state_after_scan


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
    append_campaign_event(campaign.events, event)


# Backward-compatible aliases for historical imports/tests.
_observation_id = observation_id
_record_asset_observation = record_asset
_record_endpoint_observation = record_endpoint
_record_finding_observation = record_finding_chain
_record_artifact_observation = record_artifact


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


def _process_scanner_job(job: dict, queue: JobQueue, store: Storage, runner) -> None:
    campaign, version = _campaign(store, job["campaign_id"])
    result = runner(job, campaign, queue, store)
    _append_event_once(campaign, result.event)
    _save(store, campaign, version)


def process_strix_scan(job: dict, queue: JobQueue, store: Storage) -> None:
    _process_scanner_job(job, queue, store, run_strix_job)


def process_nuclei_scan(job: dict, queue: JobQueue, store: Storage) -> None:
    _process_scanner_job(job, queue, store, run_nuclei_job)


def process_validation(job: dict, store: Storage) -> None:
    """Capture independent read-only HTTP evidence without self-confirming findings."""
    campaign, version = _campaign(store, job["campaign_id"])
    finding_id = str(job["payload"].get("finding_id") or "")
    finding = next((f for f in campaign.findings if f.id == finding_id), None)
    if not finding:
        raise KeyError(f"finding {finding_id} not found")
    if campaign.state == CampaignState.completed:
        raise StaleValidationJobError("completed campaign rejects validation work")
    if finding.status != "validation_required":
        raise StaleValidationJobError(
            f"stale validation job for finding in {finding.status} state"
        )
    if finding.discovered_by == "independent-http-validator":
        raise ValidationPolicyError("discovery agent cannot validate its own finding")

    finding_observation_id = record_finding_chain(store, campaign, finding)
    result = safe_http_probe(campaign, finding)
    artifact = store.put_artifact(
        campaign.id,
        "validation",
        result.json_bytes(),
        media_type="application/json",
        finding_id=finding.id,
        idempotency_key=f"{job['id']}:validation",
    )
    validation_observation_id = record_artifact(
        store,
        campaign,
        artifact,
        source="independent-http-validator",
        parent_ids=(finding_observation_id,),
        kind="validation",
        value=result.status,
        metadata={"http_status": result.http_status, "finding_id": finding.id},
    )
    record_artifact(
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
    if campaign.state == CampaignState.completed:
        raise StaleBrowserJobError("completed campaign rejects browser work")
    asset_id = record_asset(store, campaign, str(campaign.target.primary_url), "browser")
    result = execute_browser_flow(campaign, job["payload"])
    artifacts = persist_browser_result(store, campaign.id, result, idempotency_prefix=job["id"])
    for observation in result.observations:
        operation = observation.get("operation")
        if operation == "navigate" and observation.get("url"):
            endpoint_url = str(observation["url"])
            record_endpoint(
                store,
                campaign,
                endpoint_url,
                source="browser",
                parent_id=asset_id,
            )
            if result.identity_label:
                record_typed_child(
                    store,
                    campaign,
                    kind="access_surface",
                    value=endpoint_url,
                    source="browser",
                    parent_id=asset_id,
                    metadata={
                        "identity_label": result.identity_label,
                        "http_status": observation.get("status"),
                        "content_sha256": observation.get("content_sha256"),
                        "content_bytes": observation.get("content_bytes"),
                        "structure_sha256": observation.get("structure_sha256"),
                        "structure_metrics": observation.get("structure_metrics"),
                    },
                    identity=(
                        f"browser-access\x1f{result.identity_label}\x1f{endpoint_url}"
                    ),
                )
        elif operation == "surface_links":
            for endpoint in observation.get("urls", [])[:100]:
                record_endpoint(
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
                record_typed_child(
                    store,
                    campaign,
                    kind="form",
                    value=action,
                    source="browser",
                    parent_id=asset_id,
                    metadata={
                        "method": str(form.get("method") or "GET"),
                        "input_names": list(form.get("input_names", []))[:100],
                    },
                    identity=(
                        f"browser\x1f{action}\x1f{form.get('method', 'GET')}\x1f"
                        + ",".join(str(name) for name in form.get("input_names", []))
                    ),
                )
        elif operation == "surface_technologies":
            for technology in observation.get("technologies", [])[:20]:
                record_typed_child(
                    store,
                    campaign,
                    kind="technology",
                    value=str(technology),
                    source="browser",
                    parent_id=asset_id,
                )
    for artifact in artifacts:
        record_artifact(
            store,
            campaign,
            artifact,
            source="browser",
            parent_ids=(asset_id,),
            metadata={
                "browser_status": result.status,
                "identity_label": result.identity_label,
            },
        )
    _append_event_once(
        campaign,
        {
            "type": "browser_flow_completed" if result.status == "completed" else "browser_flow_dry_run",
            "job_id": job["id"],
            "status": result.status,
            "identity_label": result.identity_label,
            "artifact_ids": [artifact["id"] for artifact in artifacts],
            "at": utcnow(),
        },
    )
    _save(store, campaign, version)


def process_recon_task(job: dict, store: Storage) -> None:
    campaign, version = _campaign(store, job["campaign_id"])
    result = execute_recon_task(campaign, job["payload"])
    source = f"recon:{job['payload'].get('kind', 'unknown')}"
    asset_id = record_asset(
        store,
        campaign,
        str(campaign.target.primary_url),
        source,
    )

    for discovered_asset in result.assets:
        record_asset(
            store,
            campaign,
            discovered_asset,
            f"{source}:passive",
        )

    for endpoint in result.endpoints:
        record_endpoint(
            store,
            campaign,
            endpoint,
            source=source,
            parent_id=asset_id,
        )

    for form in result.forms:
        record_typed_child(
            store,
            campaign,
            kind="form",
            value=form["action"],
            source=source,
            parent_id=asset_id,
            metadata={
                "method": form["method"],
                "input_names": form["input_names"],
            },
            identity=f"{source}\x1f{form['action']}\x1f{','.join(form['input_names'])}",
        )

    for technology in result.technologies:
        record_typed_child(
            store,
            campaign,
            kind="technology",
            value=technology,
            source=source,
            parent_id=asset_id,
        )

    for waf in result.waf:
        record_typed_child(
            store,
            campaign,
            kind="waf",
            value=waf,
            source=source,
            parent_id=asset_id,
        )

    _append_event_once(
        campaign,
        {
            "type": "recon_task_completed" if result.status == "observed" else "recon_task_dry_run",
            "job_id": job["id"],
            "task_kind": job["payload"].get("kind"),
            "status": result.status,
            "http_status": result.http_status,
            "assets": len(result.assets),
            "endpoints": len(result.endpoints),
            "forms": len(result.forms),
            "technologies": len(result.technologies),
            "waf": len(result.waf),
            "requests_made": result.requests_made,
            "bytes_read": result.bytes_read,
            "max_depth_reached": result.max_depth_reached,
            "skipped_out_of_scope": result.skipped_out_of_scope,
            "skipped_cross_origin": result.skipped_cross_origin,
            "wall_time_seconds": result.wall_time_seconds,
            "stopped_by_time_budget": result.stopped_by_time_budget,
            "request_budget": result.request_budget,
            "frontier_remaining": result.frontier_remaining,
            "stopped_by_request_budget": result.stopped_by_request_budget,
            "deferred_by_request_budget": result.deferred_by_request_budget,
            "coverage_complete": result.coverage_complete,
            "at": utcnow(),
        },
    )
    _save(store, campaign, version)


def process_report(job: dict, store: Storage) -> None:
    campaign, version = _campaign(store, job["campaign_id"])
    platform = str(job.get("payload", {}).get("platform") or "generic")
    if platform not in {"generic", "hackerone", "bugcrowd"}:
        raise ValueError("unsupported report platform")
    graph = ObservationGraph.from_records(store.list_observations(campaign.id))
    quality = {
        item.finding_id: item.to_dict()
        for item in build_evidence_quality(graph)
    }
    report = render_markdown(
        campaign,
        platform=platform,
        evidence_quality=quality,
    ).encode("utf-8")
    artifact = store.put_artifact(
        campaign.id,
        "report",
        report,
        media_type="text/markdown",
        idempotency_key=f"{job['id']}:report:{platform}",
    )
    record_artifact(
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


def _record_worker_outcome(store: Storage, job: dict, *, success: bool, status: str) -> bool:
    """Persist a bounded, idempotent worker outcome without job payloads or errors."""
    event = worker_outcome_event(job, success=success, status=status)
    for _ in range(3):
        record = store.get_campaign_record(job["campaign_id"])
        if not record:
            return False
        raw, version = record
        campaign = Campaign.model_validate(raw)
        if any(
            item.get("type") == "worker_outcome"
            and item.get("job_id") == event["job_id"]
            and item.get("status") == event["status"]
            for item in campaign.events
        ):
            return True
        sealed = seal_worker_outcome_event(
            {**event, "at": utcnow()},
            campaign.events,
        )
        append_campaign_event(campaign.events, sealed)
        campaign.updated_at = utcnow()
        try:
            store.save_campaign(campaign.model_dump(mode="json"), expected_version=version)
            return True
        except CampaignConflictError:
            continue
    return False


def _worker_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean")


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


def _active_scanner_execution_requested() -> bool:
    return (
        _worker_bool("XBOW_ENABLE_ACTIVE_SCANS", False)
        and not _worker_bool("DRY_RUN", True)
    )


def _claim_for_role(queue: JobQueue, worker_id: str):
    role = (os.getenv("XBOW_WORKER_ROLE") or "").strip().lower()
    if not role:
        return queue.claim(worker_id)
    if role == "general":
        kinds = ["independent_validation", "browser_flow", "recon_task", "report"]
        if not _active_scanner_execution_requested():
            kinds.extend(("nuclei_scan", "strix_scan"))
        return queue.claim_allowed(worker_id, kinds)
    if role == "scanner":
        return queue.claim_allowed(worker_id, ("nuclei_scan", "strix_scan"))
    raise ValueError("XBOW_WORKER_ROLE must be general or scanner")


def process_one(queue: JobQueue, store: Storage, worker_id: str) -> bool:
    job = _claim_for_role(queue, worker_id)
    if not job:
        return False
    try:
        _verify_policy_bound_job(job, store)
        with _lease_heartbeat(queue, job["id"], worker_id):
            if job["kind"] == "strix_scan":
                process_strix_scan(job, queue, store)
            elif job["kind"] == "nuclei_scan":
                process_nuclei_scan(job, queue, store)
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

            with campaign_planner_lock(queue, job["campaign_id"]) as planner_acquired:
                if planner_acquired:
                    latest_campaign, _ = _campaign(store, job["campaign_id"])
                    advance_campaign(latest_campaign, queue, store)
    except CampaignCancelledError as exc:
        finished = queue.cancel_owned(job["id"], worker_id, str(exc))
        if finished is not None:
            _record_worker_outcome(store, finished, success=False, status="cancelled")
    except CampaignConflictError as exc:
        finished = queue.finish(job["id"], worker_id, False, f"campaign state changed concurrently: {exc}")
        if finished is not None:
            _record_worker_outcome(store, finished, success=False, status=finished["status"])
    except StaleValidationJobError as exc:
        finished = queue.cancel_owned(job["id"], worker_id, str(exc))
        if finished is not None:
            _record_worker_outcome(store, finished, success=False, status="cancelled")
    except StaleBrowserJobError as exc:
        finished = queue.cancel_owned(job["id"], worker_id, str(exc))
        if finished is not None:
            _record_worker_outcome(store, finished, success=False, status="cancelled")
    except (WorkerPolicyError, ValidationPolicyError, BrowserPolicyError, ReconPolicyError, ValueError, KeyError) as exc:
        finished = queue.finish(job["id"], worker_id, False, str(exc))
        if finished is not None:
            _record_worker_outcome(store, finished, success=False, status=finished["status"])
    except Exception as exc:
        finished = queue.finish(job["id"], worker_id, False, str(exc))
        if finished is not None:
            _record_worker_outcome(store, finished, success=False, status=finished["status"])
    else:
        finished = queue.finish(job["id"], worker_id, True)
        if finished is not None:
            _record_worker_outcome(store, finished, success=True, status=finished["status"])
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
    queue = create_queue()
    store = create_storage()
    worker_id = os.getenv("XBOW_WORKER_ID", f"{socket.gethostname()}:{os.getpid()}")
    poll = _worker_poll_seconds()
    worker_role = (os.getenv("XBOW_WORKER_ROLE") or "").strip().lower()
    heartbeat_role = "general" if worker_role in {"", "general"} else worker_role
    coordinator = heartbeat_role == "general"
    try:
        start_worker_heartbeat(heartbeat_role)
    except ValueError:
        # Invalid role/configuration still fails closed in the normal claim path.
        pass
    while True:
        if coordinator:
            try:
                maybe_refresh_hackerone_catalog(store)
            except Exception:
                # Read-only catalog monitoring must never take down execution workers.
                pass
            try:
                maybe_refresh_hackerone_intelligence(store)
            except Exception:
                # Public Hacktivity learning is advisory and must never stop workers.
                pass
            try:
                reconcile_hackerone_batches(queue, store, limit=20)
            except Exception:
                # Batch scheduling must fail closed without taking down the worker.
                pass
            try:
                sync_completed_learning_batches(store, limit=20)
            except Exception:
                # Learning sync is advisory and must never stop campaign execution.
                pass
        worked = process_one(queue, store, worker_id)
        if not worked:
            time.sleep(poll)


if __name__ == "__main__":
    main()
