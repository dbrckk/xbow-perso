from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class ReportApprovalStatus:
    artifact_id: str
    artifact_sha256: str
    approved: bool
    stale: bool
    reviewer: str | None
    approved_at: str | None
    basis_digest: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _finding_payload(finding: Any) -> dict[str, Any]:
    if hasattr(finding, "model_dump"):
        return finding.model_dump(mode="json")
    return dict(finding)


def report_basis_digest(campaign: Any, artifact: dict[str, Any]) -> str:
    """Bind approval to the exact report artifact and submission-relevant campaign state."""
    confirmed = [
        _finding_payload(finding)
        for finding in campaign.findings
        if getattr(finding, "status", None) == "confirmed"
    ]
    confirmed.sort(key=lambda item: str(item.get("id", "")))
    rules = campaign.target.rules
    payload = {
        "artifact": {
            "id": artifact["id"],
            "sha256": artifact["sha256"],
            "kind": artifact.get("kind"),
        },
        "target": str(campaign.target.primary_url),
        "authorization_reference": rules.authorization_reference,
        "allowed_targets": sorted(rules.allowed_targets),
        "denied_targets": sorted(rules.denied_targets),
        "confirmed_findings": confirmed,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def approval_event(campaign: Any, artifact: dict[str, Any], reviewer: str, at: str) -> dict[str, Any]:
    reviewer = reviewer.strip()
    if not reviewer:
        raise ValueError("reviewer is required")
    if artifact.get("kind") != "report":
        raise ValueError("only report artifacts can be approved")
    return {
        "type": "report_approved",
        "artifact_id": artifact["id"],
        "artifact_sha256": artifact["sha256"],
        "basis_digest": report_basis_digest(campaign, artifact),
        "reviewer": reviewer,
        "at": at,
    }


def revocation_event(artifact_id: str, reviewer: str, at: str) -> dict[str, Any]:
    reviewer = reviewer.strip()
    if not reviewer:
        raise ValueError("reviewer is required")
    return {
        "type": "report_approval_revoked",
        "artifact_id": artifact_id,
        "reviewer": reviewer,
        "at": at,
    }


def approval_status(campaign: Any, artifact: dict[str, Any]) -> ReportApprovalStatus:
    current_digest = report_basis_digest(campaign, artifact)
    relevant = [
        event
        for event in campaign.events
        if event.get("artifact_id") == artifact["id"]
        and event.get("type") in {"report_approved", "report_approval_revoked"}
    ]
    if not relevant:
        return ReportApprovalStatus(
            artifact_id=artifact["id"],
            artifact_sha256=artifact["sha256"],
            approved=False,
            stale=False,
            reviewer=None,
            approved_at=None,
            basis_digest=current_digest,
        )

    latest = relevant[-1]
    if latest.get("type") == "report_approval_revoked":
        return ReportApprovalStatus(
            artifact_id=artifact["id"],
            artifact_sha256=artifact["sha256"],
            approved=False,
            stale=False,
            reviewer=latest.get("reviewer"),
            approved_at=None,
            basis_digest=current_digest,
        )

    stale = (
        latest.get("artifact_sha256") != artifact["sha256"]
        or latest.get("basis_digest") != current_digest
    )
    return ReportApprovalStatus(
        artifact_id=artifact["id"],
        artifact_sha256=artifact["sha256"],
        approved=not stale,
        stale=stale,
        reviewer=latest.get("reviewer"),
        approved_at=latest.get("at"),
        basis_digest=current_digest,
    )
