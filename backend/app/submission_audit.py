from __future__ import annotations

from typing import Any


def _campaign_events(campaign: Any) -> list[dict[str, Any]]:
    if isinstance(campaign, dict):
        return list(campaign.get("events") or [])
    return list(getattr(campaign, "events", []) or [])


def audit_submission_events(
    campaign: Any,
    artifact_id: str,
) -> dict[str, Any]:
    relevant = [
        event
        for event in _campaign_events(campaign)
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



def audit_campaign_submissions(
    campaign: Any,
    report_artifact_ids: list[str],
) -> dict[str, Any]:
    audits = [
        audit_submission_events(campaign, artifact_id)
        for artifact_id in sorted(set(report_artifact_ids))
    ]
    issue_counts: dict[str, int] = {}
    for audit in audits:
        for issue in audit["issues"]:
            issue_counts[issue] = issue_counts.get(issue, 0) + 1

    invalid = [audit for audit in audits if not audit["valid"]]
    return {
        "valid": not invalid,
        "reports_checked": len(audits),
        "invalid_reports": len(invalid),
        "submissions": sum(int(audit["submissions"]) for audit in audits),
        "active_approvals": sum(
            bool(audit["approval_active"]) for audit in audits
        ),
        "issue_counts": dict(sorted(issue_counts.items())),
        "invalid_artifact_ids": sorted(
            str(audit["artifact_id"]) for audit in invalid
        ),
        "read_only": True,
        "automatic_mutation": False,
    }
