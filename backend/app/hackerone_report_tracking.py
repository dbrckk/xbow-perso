from __future__ import annotations

from typing import Any

from fastapi import HTTPException


MAX_ACTIVITY_MESSAGE_CHARS = 8192
NEEDS_MORE_INFO_ACTIVITY_TYPE = "activity-bug-needs-more-info"

TRACKED_TIMESTAMP_FIELDS = (
    "created_at",
    "triaged_at",
    "closed_at",
    "last_program_activity_at",
    "last_reporter_activity_at",
    "last_activity_at",
)


def _campaign_events(campaign: Any) -> list[dict[str, Any]]:
    if isinstance(campaign, dict):
        events = campaign.get("events")
    else:
        events = getattr(campaign, "events", None)
    return events if isinstance(events, list) else []


def latest_remote_submission(campaign: Any, artifact_id: str) -> dict[str, Any] | None:
    matches = [
        event
        for event in _campaign_events(campaign)
        if event.get("type") == "hackerone_report_submitted"
        and event.get("artifact_id") == artifact_id
    ]
    return matches[-1] if matches else None


def remote_submission_for_artifact(
    campaign: Any,
    artifact_id: str,
) -> dict[str, Any]:
    remote = latest_remote_submission(campaign, artifact_id)
    if remote is None:
        raise HTTPException(
            status_code=409,
            detail="Report has no recorded HackerOne remote submission",
        )
    remote_report_id = remote.get("remote_report_id")
    team_handle = remote.get("team_handle")
    if (
        not isinstance(remote_report_id, str)
        or not remote_report_id.isdigit()
        or not isinstance(team_handle, str)
        or not team_handle.strip()
    ):
        raise HTTPException(
            status_code=409,
            detail="Recorded HackerOne submission metadata is invalid",
        )
    return {
        **remote,
        "remote_report_id": remote_report_id,
        "team_handle": team_handle.strip(),
    }


def project_needs_more_info_request(
    document: dict[str, Any],
    *,
    expected_report_id: str,
) -> dict[str, Any] | None:
    data = document.get("data")
    if not isinstance(data, dict):
        raise HTTPException(
            status_code=502,
            detail="HackerOne remote report response is invalid",
        )
    if data.get("type") != "report" or data.get("id") != expected_report_id:
        raise HTTPException(
            status_code=502,
            detail="HackerOne remote report identity mismatch",
        )
    relationships = data.get("relationships")
    if not isinstance(relationships, dict):
        return None
    activities = relationships.get("activities")
    if not isinstance(activities, dict):
        return None
    records = activities.get("data")
    if not isinstance(records, list):
        return None

    for activity in records:
        if not isinstance(activity, dict):
            continue
        if activity.get("type") != NEEDS_MORE_INFO_ACTIVITY_TYPE:
            continue
        activity_id = activity.get("id")
        attributes = activity.get("attributes")
        if not isinstance(activity_id, str) or not activity_id.strip():
            continue
        if not isinstance(attributes, dict):
            continue
        if attributes.get("internal") is not False:
            continue
        report_id = attributes.get("report_id")
        if report_id is not None and str(report_id) != expected_report_id:
            continue
        message = attributes.get("message")
        if not isinstance(message, str) or not message.strip():
            continue
        message = message.strip()[:MAX_ACTIVITY_MESSAGE_CHARS]
        created_at = attributes.get("created_at")
        updated_at = attributes.get("updated_at")
        return {
            "activity_id": activity_id.strip(),
            "activity_type": NEEDS_MORE_INFO_ACTIVITY_TYPE,
            "message": message,
            "created_at": created_at if isinstance(created_at, str) else None,
            "updated_at": updated_at if isinstance(updated_at, str) else None,
            "internal": False,
        }
    return None


def project_remote_report_status(
    document: dict[str, Any],
    *,
    artifact_id: str,
    expected_report_id: str,
    team_handle: str,
) -> dict[str, Any]:
    data = document.get("data")
    if not isinstance(data, dict):
        raise HTTPException(
            status_code=502,
            detail="HackerOne remote report response is invalid",
        )
    if data.get("type") != "report" or data.get("id") != expected_report_id:
        raise HTTPException(
            status_code=502,
            detail="HackerOne remote report identity mismatch",
        )
    attributes = data.get("attributes")
    if not isinstance(attributes, dict):
        raise HTTPException(
            status_code=502,
            detail="HackerOne remote report attributes are invalid",
        )
    state = attributes.get("state")
    if not isinstance(state, str) or not state.strip():
        raise HTTPException(
            status_code=502,
            detail="HackerOne remote report state is invalid",
        )
    projected = {
        "provider": "hackerone",
        "artifact_id": artifact_id,
        "remote_report_id": expected_report_id,
        "team_handle": team_handle,
        "state": state.strip(),
    }
    for key in TRACKED_TIMESTAMP_FIELDS:
        value = attributes.get(key)
        projected[key] = value if value is None or isinstance(value, str) else None
    projected["needs_more_info"] = project_needs_more_info_request(
        document,
        expected_report_id=expected_report_id,
    )
    projected["read_only"] = True
    return projected


def status_fingerprint_fields(status: dict[str, Any]) -> dict[str, Any]:
    return {
        "remote_report_id": status.get("remote_report_id"),
        "team_handle": status.get("team_handle"),
        "state": status.get("state"),
        **{key: status.get(key) for key in TRACKED_TIMESTAMP_FIELDS},
    }
