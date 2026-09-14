from __future__ import annotations

from typing import Any


def audit_submission_events(
    campaign: Any,
    artifact_id: str,
) -> dict[str, Any]:
    relevant = [
        event
        for event in campaign.events
        if event.get("artifact_id") == artifact_id
        and event.get("type")
        in {
            "report_approved",
            "report_approval_revoked",
            "report_submitted",
        }
    ]

    issues: list[str] = []
    approval_active = False
    last_approval_provenance: str | None = None
    submissions = 0

    for event in relevant:
        event_type = event.get("type")
        if event_type == "report_approved":
            approval_active = True
            last_approval_provenance = event.get(
                "report_provenance_fingerprint"
            )
            if not event.get("basis_digest"):
                issues.append("approval_missing_basis_digest")
            if not event.get("artifact_sha256"):
                issues.append("approval_missing_artifact_sha256")
        elif event_type == "report_approval_revoked":
            if not approval_active:
                issues.append("revocation_without_active_approval")
            approval_active = False
        elif event_type == "report_submitted":
            submissions += 1
            if not approval_active:
                issues.append("submission_without_active_approval")

    return {
        "valid": not issues,
        "artifact_id": artifact_id,
        "events_checked": len(relevant),
        "submissions": submissions,
        "approval_active": approval_active,
        "latest_approval_provenance_fingerprint": last_approval_provenance,
        "issues": sorted(set(issues)),
        "read_only": True,
        "automatic_mutation": False,
    }
