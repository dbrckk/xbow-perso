from __future__ import annotations

from typing import Any


TERMINAL_BUCKETS = {
    "resolved": "resolved",
    "duplicate": "duplicate",
    "informative": "informative",
    "not-applicable": "closed-other",
    "spam": "closed-other",
}
ACTIVE_STATES = {"new", "pending-program-review", "triaged"}
ACTION_REQUIRED_STATES = {"needs-more-info", "retesting"}


def _events(campaign: dict[str, Any]) -> list[dict[str, Any]]:
    events = campaign.get("events")
    return [event for event in events if isinstance(event, dict)] if isinstance(events, list) else []


def _latest_by(
    events: list[dict[str, Any]],
    *,
    event_type: str,
    artifact_id: str,
) -> dict[str, Any] | None:
    matches = [
        event
        for event in events
        if event.get("type") == event_type
        and event.get("artifact_id") == artifact_id
    ]
    return matches[-1] if matches else None


def _latest_submission_by_artifact(
    events: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    submissions: dict[str, dict[str, Any]] = {}
    for event in events:
        if event.get("type") != "hackerone_report_submitted":
            continue
        artifact_id = event.get("artifact_id")
        remote_report_id = event.get("remote_report_id")
        team_handle = event.get("team_handle")
        if (
            isinstance(artifact_id, str)
            and artifact_id
            and isinstance(remote_report_id, str)
            and remote_report_id.isdigit()
            and isinstance(team_handle, str)
            and team_handle.strip()
        ):
            submissions[artifact_id] = event
    return submissions


def _bucket_for_state(state: str | None) -> str:
    if state in ACTION_REQUIRED_STATES:
        return "action-required"
    if state in TERMINAL_BUCKETS:
        return TERMINAL_BUCKETS[state]
    if state in ACTIVE_STATES:
        return "active"
    if state:
        return "other"
    return "awaiting-sync"


def _latest_public_activity(
    events: list[dict[str, Any]],
    artifact_id: str,
) -> dict[str, Any] | None:
    return _latest_by(
        events,
        event_type="hackerone_public_activity_observed",
        artifact_id=artifact_id,
    )


def _latest_bounty(
    events: list[dict[str, Any]],
    artifact_id: str,
) -> dict[str, Any] | None:
    matches = [
        event
        for event in events
        if event.get("type") == "hackerone_public_activity_observed"
        and event.get("artifact_id") == artifact_id
        and event.get("activity_type") == "activity-bounty-awarded"
    ]
    return matches[-1] if matches else None


def _latest_needs_more_info(
    events: list[dict[str, Any]],
    artifact_id: str,
) -> dict[str, Any] | None:
    return _latest_by(
        events,
        event_type="hackerone_needs_more_info_observed",
        artifact_id=artifact_id,
    )


def _campaign_name(campaign: dict[str, Any]) -> str:
    target = campaign.get("target")
    if isinstance(target, dict):
        name = target.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    campaign_id = campaign.get("id")
    return str(campaign_id or "campaign")


def build_hackerone_attention_center(
    campaigns: list[dict[str, Any]],
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []

    for campaign in campaigns:
        if not isinstance(campaign, dict):
            continue
        campaign_id = campaign.get("id")
        if not isinstance(campaign_id, str) or not campaign_id:
            continue
        events = _events(campaign)
        for artifact_id, submission in _latest_submission_by_artifact(events).items():
            status = _latest_by(
                events,
                event_type="hackerone_report_status_synced",
                artifact_id=artifact_id,
            )
            state = (
                str(status.get("state")).strip()
                if isinstance(status, dict) and status.get("state")
                else None
            )
            bucket = _bucket_for_state(state)
            needs_more_info = _latest_needs_more_info(events, artifact_id)
            bounty = _latest_bounty(events, artifact_id)
            latest_activity = _latest_public_activity(events, artifact_id)

            observed_candidates = [
                status.get("observed_at") if isinstance(status, dict) else None,
                needs_more_info.get("observed_at") if isinstance(needs_more_info, dict) else None,
                latest_activity.get("observed_at") if isinstance(latest_activity, dict) else None,
                submission.get("at"),
            ]
            last_observed_at = next(
                (
                    value
                    for value in observed_candidates
                    if isinstance(value, str) and value
                ),
                None,
            )

            item = {
                "campaign_id": campaign_id,
                "campaign_name": _campaign_name(campaign),
                "artifact_id": artifact_id,
                "remote_report_id": str(submission["remote_report_id"]),
                "team_handle": str(submission["team_handle"]).strip(),
                "state": state,
                "bucket": bucket,
                "action_required": state in ACTION_REQUIRED_STATES,
                "last_observed_at": last_observed_at,
                "needs_more_info": (
                    {
                        "activity_id": needs_more_info.get("activity_id"),
                        "message": needs_more_info.get("message"),
                        "observed_at": needs_more_info.get("observed_at"),
                    }
                    if isinstance(needs_more_info, dict)
                    and state == "needs-more-info"
                    else None
                ),
                "bounty": (
                    {
                        "activity_id": bounty.get("activity_id"),
                        "amount": bounty.get("bounty_amount"),
                        "bonus_amount": bounty.get("bonus_amount"),
                        "observed_at": bounty.get("observed_at"),
                    }
                    if isinstance(bounty, dict)
                    else None
                ),
                "latest_public_activity": (
                    {
                        "activity_id": latest_activity.get("activity_id"),
                        "activity_type": latest_activity.get("activity_type"),
                        "message": latest_activity.get("message"),
                        "observed_at": latest_activity.get("observed_at"),
                    }
                    if isinstance(latest_activity, dict)
                    else None
                ),
            }
            items.append(item)

    bucket_order = {
        "action-required": 0,
        "active": 1,
        "awaiting-sync": 2,
        "resolved": 3,
        "duplicate": 4,
        "informative": 5,
        "closed-other": 6,
        "other": 7,
    }
    items.sort(
        key=lambda item: (
            str(item.get("last_observed_at") or ""),
            str(item.get("campaign_id") or ""),
        ),
        reverse=True,
    )
    items.sort(
        key=lambda item: bucket_order.get(str(item.get("bucket")), 99),
    )

    counts: dict[str, int] = {}
    for item in items:
        bucket = str(item["bucket"])
        counts[bucket] = counts.get(bucket, 0) + 1

    return {
        "summary": {
            "total": len(items),
            "action_required": counts.get("action-required", 0),
            "active": counts.get("active", 0),
            "awaiting_sync": counts.get("awaiting-sync", 0),
            "resolved": counts.get("resolved", 0),
            "duplicate": counts.get("duplicate", 0),
            "informative": counts.get("informative", 0),
            "closed_other": counts.get("closed-other", 0),
            "other": counts.get("other", 0),
            "with_bounty": sum(1 for item in items if item.get("bounty") is not None),
        },
        "items": items,
        "read_only": True,
        "source": "local_audit_events",
    }
