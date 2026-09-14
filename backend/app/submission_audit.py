from __future__ import annotations

from typing import Any


ISSUE_SEVERITY = {
    "structural": "high",
    "metadata": "medium",
    "stale": "low",
    "other": "medium",
}


def _severity_summary(issue_class_counts: dict[str, int]) -> dict[str, Any]:
    weighted = {
        "high": 3,
        "medium": 2,
        "low": 1,
    }
    severity_counts = {
        severity: 0
        for severity in ("high", "medium", "low")
    }
    for category, count in issue_class_counts.items():
        severity = ISSUE_SEVERITY.get(category, "medium")
        severity_counts[severity] += int(count)
    highest = "none"
    for severity in ("high", "medium", "low"):
        if severity_counts[severity]:
            highest = severity
            break
    score = sum(
        weighted[severity] * count
        for severity, count in severity_counts.items()
    )
    return {
        "highest": highest,
        "counts": severity_counts,
        "weighted_score": score,
    }


ISSUE_CLASS = {
    "submission_without_active_approval": "structural",
    "revocation_without_active_approval": "structural",
    "approval_missing_basis_digest": "metadata",
    "approval_missing_artifact_sha256": "metadata",
    "approval_provenance_stale": "stale",
}


def _issue_classes(issues: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for issue in issues:
        category = ISSUE_CLASS.get(issue, "other")
        counts[category] = counts.get(category, 0) + 1
    return dict(sorted(counts.items()))


def _campaign_events(campaign: Any) -> list[dict[str, Any]]:
    if isinstance(campaign, dict):
        return list(campaign.get("events") or [])
    return list(getattr(campaign, "events", []) or [])


def audit_submission_events(
    campaign: Any,
    artifact_id: str,
    *,
    current_provenance_fingerprint: str | None = None,
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

    if (
        approval_active
        and last_approval_provenance is not None
        and current_provenance_fingerprint is not None
        and last_approval_provenance != current_provenance_fingerprint
    ):
        issues.append("approval_provenance_stale")

    return {
        "valid": not issues,
        "artifact_id": artifact_id,
        "events_checked": len(relevant),
        "submissions": submissions,
        "approval_active": approval_active,
        "latest_approval_provenance_fingerprint": last_approval_provenance,
        "current_provenance_fingerprint": current_provenance_fingerprint,
        "issues": sorted(set(issues)),
        "issue_classes": _issue_classes(sorted(set(issues))),
        "severity": _severity_summary(
            _issue_classes(sorted(set(issues)))
        ),
        "read_only": True,
        "automatic_mutation": False,
    }



def audit_campaign_submissions(
    campaign: Any,
    report_artifact_ids: list[str],
    *,
    current_provenance_fingerprint: str | None = None,
) -> dict[str, Any]:
    audits = [
        audit_submission_events(
            campaign,
            artifact_id,
            current_provenance_fingerprint=current_provenance_fingerprint,
        )
        for artifact_id in sorted(set(report_artifact_ids))
    ]
    issue_counts: dict[str, int] = {}
    issue_class_counts: dict[str, int] = {}
    for audit in audits:
        for issue in audit["issues"]:
            issue_counts[issue] = issue_counts.get(issue, 0) + 1
        for category, count in audit["issue_classes"].items():
            issue_class_counts[category] = (
                issue_class_counts.get(category, 0) + int(count)
            )

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
        "issue_class_counts": dict(sorted(issue_class_counts.items())),
        "severity": _severity_summary(issue_class_counts),
        "invalid_artifact_ids": sorted(
            str(audit["artifact_id"]) for audit in invalid
        ),
        "read_only": True,
        "automatic_mutation": False,
    }



def audit_storage_submissions(storage_backend: Any) -> dict[str, Any]:
    list_artifacts = getattr(storage_backend, "list_artifacts", None)
    if not callable(list_artifacts):
        return {
            "supported": False,
            "valid": True,
            "campaigns_checked": 0,
            "reports_checked": 0,
            "invalid_reports": 0,
            "issue_counts": {},
            "issue_class_counts": {},
            "severity": _severity_summary({}),
            "read_only": True,
            "automatic_mutation": False,
        }

    campaigns = list(storage_backend.list_campaigns())
    campaign_audits: list[dict[str, Any]] = []
    issue_counts: dict[str, int] = {}
    issue_class_counts: dict[str, int] = {}
    for campaign in campaigns:
        campaign_id = (
            str(campaign.get("id"))
            if isinstance(campaign, dict)
            else str(getattr(campaign, "id"))
        )
        artifacts = list_artifacts(campaign_id)
        report_ids = [
            str(item["id"])
            for item in artifacts
            if item.get("kind") == "report"
        ]
        audit = audit_campaign_submissions(campaign, report_ids)
        campaign_audits.append(audit)
        for issue, count in audit["issue_counts"].items():
            issue_counts[issue] = issue_counts.get(issue, 0) + int(count)
        for category, count in audit["issue_class_counts"].items():
            issue_class_counts[category] = (
                issue_class_counts.get(category, 0) + int(count)
            )

    return {
        "supported": True,
        "valid": all(item["valid"] for item in campaign_audits),
        "campaigns_checked": len(campaign_audits),
        "reports_checked": sum(
            int(item["reports_checked"]) for item in campaign_audits
        ),
        "invalid_reports": sum(
            int(item["invalid_reports"]) for item in campaign_audits
        ),
        "issue_counts": dict(sorted(issue_counts.items())),
        "issue_class_counts": dict(sorted(issue_class_counts.items())),
        "severity": _severity_summary(issue_class_counts),
        "read_only": True,
        "automatic_mutation": False,
    }
