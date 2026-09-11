from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from .jobqueue import JobQueue
from .main import Campaign
from .observation_graph import Observation
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


def _observation_id(prefix: str, value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]
    return f"{prefix}:{digest}"


def _record_finding_chain(
    store: Storage,
    campaign: Campaign,
    finding,
) -> str:
    source = finding.discovered_by
    asset = Observation(
        id=_observation_id("asset", f"{source}\x1f{finding.asset}"),
        kind="asset",
        value=finding.asset,
        source=source,
    )
    store.put_observation(campaign.id, asset.to_dict())

    parent_id = asset.id
    if finding.endpoint:
        endpoint_value = str(finding.endpoint)
        if endpoint_value.startswith("/"):
            endpoint_value = str(finding.asset).rstrip("/") + endpoint_value
        endpoint = Observation(
            id=_observation_id("endpoint", f"{source}\x1f{endpoint_value}"),
            kind="endpoint",
            value=endpoint_value,
            source=source,
            parent_ids=(asset.id,),
        )
        store.put_observation(campaign.id, endpoint.to_dict())
        parent_id = endpoint.id

    finding_observation = Observation(
        id=f"finding:{finding.id}",
        kind="finding",
        value=finding.id,
        source=source,
        parent_ids=(parent_id,),
        metadata={
            "title": finding.title,
            "severity": finding.severity,
            "endpoint": finding.endpoint,
            "cwe": finding.cwe,
            "cvss": finding.cvss,
        },
    )
    store.put_observation(campaign.id, finding_observation.to_dict())

    for index, evidence in enumerate(finding.evidence[:50], start=1):
        item = Observation(
            id=_observation_id(
                "evidence",
                f"{source}\x1f{finding.id}\x1f{index}\x1f{evidence}",
            ),
            kind="evidence",
            value=str(evidence),
            source=source,
            parent_ids=(finding_observation.id,),
            metadata={
                "finding_id": finding.id,
                "scanner_evidence": True,
                "ordinal": index,
            },
        )
        store.put_observation(campaign.id, item.to_dict())

    return finding_observation.id


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
        _record_finding_chain(store, campaign, finding)
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
