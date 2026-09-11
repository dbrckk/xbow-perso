from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .jobqueue import JobQueue
from .main import Campaign
from .observation_writer import record_finding_chain
from .scanner_registry import latest_scanner_artifact, parse_scanner_artifact
from .storage import Storage


@dataclass(frozen=True)
class ScannerIngestionResult:
    engine: str
    artifact_path: str | None
    findings_seen: int
    findings_added: int
    validation_jobs: int

    def to_dict(self) -> dict:
        return {
            "engine": self.engine,
            "artifact_path": self.artifact_path,
            "findings_seen": self.findings_seen,
            "findings_added": self.findings_added,
            "validation_jobs": self.validation_jobs,
        }


def ingest_scanner_run(
    engine: str,
    run_dir: str | Path,
    campaign: Campaign,
    queue: JobQueue,
    store: Storage,
) -> ScannerIngestionResult:
    artifact = latest_scanner_artifact(engine, run_dir)
    if artifact is None:
        return ScannerIngestionResult(
            engine=engine,
            artifact_path=None,
            findings_seen=0,
            findings_added=0,
            validation_jobs=0,
        )

    findings = parse_scanner_artifact(engine, artifact, campaign)
    existing = {finding.id for finding in campaign.findings}
    added = 0
    queued = 0

    for finding in findings:
        record_finding_chain(store, campaign, finding)
        if finding.id in existing:
            continue

        campaign.findings.append(finding)
        existing.add(finding.id)
        added += 1

        queue.enqueue(
            campaign.id,
            "independent_validation",
            {
                "campaign_id": campaign.id,
                "finding_id": finding.id,
                "asset": finding.asset,
            },
            max_attempts=2,
            dedupe_key=f"validation:{finding.id}",
        )
        queued += 1

    return ScannerIngestionResult(
        engine=engine,
        artifact_path=str(artifact),
        findings_seen=len(findings),
        findings_added=added,
        validation_jobs=queued,
    )
