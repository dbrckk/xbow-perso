from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .jobqueue import JobQueue
from .main import Campaign, CampaignState, utcnow
from .observation_graph import Observation
from .observation_writer import record_asset
from .scanner_ingestion import ScannerIngestionResult, ingest_scanner_run
from .storage import Storage
from .worker import build_nuclei_plan, build_strix_plan, execute, persist_execution_artifacts


@dataclass(frozen=True)
class ScannerJobResult:
    engine: str
    status: str
    ingestion: ScannerIngestionResult | None
    event: dict


def _record_scan_observation(
    store: Storage,
    campaign: Campaign,
    *,
    engine: str,
    job_id: str,
    findings: int,
) -> None:
    store.put_observation(
        campaign.id,
        Observation(
            id=f"scan:{job_id}",
            kind="evidence",
            value="completed",
            source=engine,
            metadata={
                "phase": "scan",
                "status": "completed",
                "findings": findings,
                "job_id": job_id,
                "engine": engine,
            },
        ).to_dict(),
    )


def _state_after_scan(campaign: Campaign) -> CampaignState:
    unresolved = any(
        finding.status not in {"confirmed", "rejected"}
        for finding in campaign.findings
    )
    return CampaignState.validating if unresolved else CampaignState.completed


def run_strix_job(
    job: dict,
    campaign: Campaign,
    queue: JobQueue,
    store: Storage,
) -> ScannerJobResult:
    run_dir = str(
        Path(os.getenv("XBOW_STRIX_RUN_ROOT", "/data/strix_runs")) / job["id"]
    )
    plan = build_strix_plan(campaign, run_dir)
    execution = execute(plan)
    persist_execution_artifacts(store, campaign.id, execution)

    if execution["status"] == "dry_run":
        record_asset(
            store,
            campaign,
            str(campaign.target.primary_url),
            "strix-dry-run",
        )
        campaign.state = CampaignState.ready
        event = {
            "type": "scan_dry_run",
            "engine": "strix",
            "job_id": job["id"],
            "at": utcnow(),
        }
        return ScannerJobResult(
            engine="strix",
            status="dry_run",
            ingestion=None,
            event=event,
        )

    if execution["status"] != "completed":
        raise RuntimeError(execution.get("stderr") or "Strix execution failed")

    ingestion = ingest_scanner_run(
        "strix",
        run_dir,
        campaign,
        queue,
        store,
    )
    _record_scan_observation(
        store,
        campaign,
        engine="strix",
        job_id=job["id"],
        findings=ingestion.findings_seen,
    )
    campaign.state = _state_after_scan(campaign)
    event = {
        "type": "scanner_results_ingested",
        "engine": ingestion.engine,
        "job_id": job["id"],
        "findings": ingestion.findings_seen,
        "findings_added": ingestion.findings_added,
        "validation_jobs": ingestion.validation_jobs,
        "at": utcnow(),
    }
    return ScannerJobResult(
        engine="strix",
        status="completed",
        ingestion=ingestion,
        event=event,
    )


def run_nuclei_job(
    job: dict,
    campaign: Campaign,
    queue: JobQueue,
    store: Storage,
) -> ScannerJobResult:
    run_dir = str(
        Path(os.getenv("XBOW_NUCLEI_RUN_ROOT", "/data/nuclei_runs")) / job["id"]
    )
    plan = build_nuclei_plan(campaign, run_dir)
    execution = execute(plan)
    persist_execution_artifacts(store, campaign.id, execution)

    if execution["status"] == "dry_run":
        record_asset(
            store,
            campaign,
            str(campaign.target.primary_url),
            "nuclei-dry-run",
        )
        campaign.state = CampaignState.ready
        event = {
            "type": "scan_dry_run",
            "engine": "nuclei",
            "job_id": job["id"],
            "at": utcnow(),
        }
        return ScannerJobResult(
            engine="nuclei",
            status="dry_run",
            ingestion=None,
            event=event,
        )

    if execution["status"] != "completed":
        raise RuntimeError(execution.get("stderr") or "Nuclei execution failed")

    ingestion = ingest_scanner_run(
        "nuclei",
        run_dir,
        campaign,
        queue,
        store,
    )
    _record_scan_observation(
        store,
        campaign,
        engine="nuclei",
        job_id=job["id"],
        findings=ingestion.findings_seen,
    )
    campaign.state = _state_after_scan(campaign)
    event = {
        "type": "scanner_results_ingested",
        "engine": ingestion.engine,
        "job_id": job["id"],
        "findings": ingestion.findings_seen,
        "findings_added": ingestion.findings_added,
        "validation_jobs": ingestion.validation_jobs,
        "at": utcnow(),
    }
    return ScannerJobResult(
        engine="nuclei",
        status="completed",
        ingestion=ingestion,
        event=event,
    )
