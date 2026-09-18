from __future__ import annotations

import os
import socket
import time
from typing import Any

from fastapi import HTTPException

from .campaign_audit import append_campaign_event
from .hackerone_client import HackerOneClient, HackerOneClientError
from .hackerone_report_tracking import (
    latest_remote_submission,
    project_needs_more_info_request,
    project_public_report_activities,
    project_remote_report_status,
    status_fingerprint_fields,
)
from .storage import CampaignConflictError
from .storage_backend import create_storage
from .storage_core import utcnow


class HackerOneReportSyncError(RuntimeError):
    pass


def _strict_bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise HackerOneReportSyncError(f"{name} must be a boolean")


def _require_enabled() -> None:
    if not _strict_bool_env("XBOW_ENABLE_HACKERONE_REPORT_SYNC", False):
        raise HackerOneReportSyncError("HackerOne report sync worker is disabled")


def _max_campaigns() -> int:
    raw = (os.getenv("XBOW_HACKERONE_REPORT_SYNC_MAX_CAMPAIGNS") or "100").strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise HackerOneReportSyncError(
            "XBOW_HACKERONE_REPORT_SYNC_MAX_CAMPAIGNS must be an integer"
        ) from exc
    if not 1 <= value <= 500:
        raise HackerOneReportSyncError(
            "XBOW_HACKERONE_REPORT_SYNC_MAX_CAMPAIGNS must be between 1 and 500"
        )
    return value


def _interval_seconds() -> float:
    raw = (os.getenv("XBOW_HACKERONE_REPORT_SYNC_INTERVAL_SECONDS") or "60").strip()
    try:
        value = float(raw)
    except ValueError as exc:
        raise HackerOneReportSyncError(
            "XBOW_HACKERONE_REPORT_SYNC_INTERVAL_SECONDS must be numeric"
        ) from exc
    if not 15 <= value <= 3600:
        raise HackerOneReportSyncError(
            "XBOW_HACKERONE_REPORT_SYNC_INTERVAL_SECONDS must be between 15 and 3600"
        )
    return value


def _submissions(document: dict[str, Any]) -> list[dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    events = document.get("events")
    if not isinstance(events, list):
        return []
    for event in events:
        if not isinstance(event, dict) or event.get("type") != "hackerone_report_submitted":
            continue
        artifact_id = event.get("artifact_id")
        remote_report_id = event.get("remote_report_id")
        team_handle = event.get("team_handle")
        if (
            isinstance(artifact_id, str)
            and artifact_id.strip()
            and isinstance(remote_report_id, str)
            and remote_report_id.isdigit()
            and isinstance(team_handle, str)
            and team_handle.strip()
        ):
            latest[artifact_id] = event
    return list(latest.values())


def _last_synced(document: dict[str, Any], artifact_id: str) -> dict[str, Any] | None:
    events = document.get("events")
    if not isinstance(events, list):
        return None
    matches = [
        event
        for event in events
        if isinstance(event, dict)
        and event.get("type") == "hackerone_report_status_synced"
        and event.get("artifact_id") == artifact_id
    ]
    return matches[-1] if matches else None


def _last_needs_more_info(
    document: dict[str, Any],
    artifact_id: str,
) -> dict[str, Any] | None:
    events = document.get("events")
    if not isinstance(events, list):
        return None
    matches = [
        event
        for event in events
        if isinstance(event, dict)
        and event.get("type") == "hackerone_needs_more_info_observed"
        and event.get("artifact_id") == artifact_id
    ]
    return matches[-1] if matches else None


def _observed_public_activity_ids(
    document: dict[str, Any],
    artifact_id: str,
) -> set[str]:
    events = document.get("events")
    if not isinstance(events, list):
        return set()
    return {
        str(event.get("activity_id"))
        for event in events
        if isinstance(event, dict)
        and event.get("type") == "hackerone_public_activity_observed"
        and event.get("artifact_id") == artifact_id
        and isinstance(event.get("activity_id"), str)
    }


def _changed(previous: dict[str, Any] | None, current: dict[str, Any]) -> bool:
    if previous is None:
        return True
    return status_fingerprint_fields(previous) != status_fingerprint_fields(current)


def _sync_submission(store, client: HackerOneClient, campaign_id: str, submission: dict[str, Any]) -> bool:
    artifact_id = str(submission["artifact_id"])
    remote_report_id = str(submission["remote_report_id"])
    team_handle = str(submission["team_handle"]).strip()

    document = client.get_json(f"hackers/reports/{remote_report_id}")
    status = project_remote_report_status(
        document,
        artifact_id=artifact_id,
        expected_report_id=remote_report_id,
        team_handle=team_handle,
    )
    needs_more_info = project_needs_more_info_request(
        document,
        expected_report_id=remote_report_id,
    )
    public_activities = project_public_report_activities(
        document,
        expected_report_id=remote_report_id,
    )

    record = store.get_campaign_record(campaign_id)
    if not record:
        return False
    current, version = record
    latest_submission = latest_remote_submission(current, artifact_id)
    if (
        latest_submission is None
        or latest_submission.get("remote_report_id") != remote_report_id
    ):
        return False
    events = current.setdefault("events", [])
    observed_at = utcnow()
    changed = False

    previous = _last_synced(current, artifact_id)
    if _changed(previous, status):
        append_campaign_event(
            events,
            {
                "type": "hackerone_report_status_synced",
                **status_fingerprint_fields(status),
                "artifact_id": artifact_id,
                "observed_at": observed_at,
            },
        )
        changed = True

    if needs_more_info is not None:
        previous_nmi = _last_needs_more_info(current, artifact_id)
        if (
            previous_nmi is None
            or previous_nmi.get("activity_id")
            != needs_more_info.get("activity_id")
        ):
            append_campaign_event(
                events,
                {
                    "type": "hackerone_needs_more_info_observed",
                    "artifact_id": artifact_id,
                    "remote_report_id": remote_report_id,
                    "activity_id": needs_more_info["activity_id"],
                    "message": needs_more_info["message"],
                    "created_at": needs_more_info.get("created_at"),
                    "updated_at": needs_more_info.get("updated_at"),
                    "observed_at": observed_at,
                },
            )
            changed = True

    observed_activity_ids = _observed_public_activity_ids(
        current,
        artifact_id,
    )
    for activity in reversed(public_activities):
        activity_id = str(activity["activity_id"])
        if activity_id in observed_activity_ids:
            continue
        event = {
            "type": "hackerone_public_activity_observed",
            "artifact_id": artifact_id,
            "remote_report_id": remote_report_id,
            "activity_id": activity_id,
            "activity_type": activity["activity_type"],
            "created_at": activity.get("created_at"),
            "updated_at": activity.get("updated_at"),
            "observed_at": observed_at,
        }
        for key in (
            "message",
            "bounty_amount",
            "bonus_amount",
            "original_report_id",
        ):
            if key in activity:
                event[key] = activity[key]
        append_campaign_event(events, event)
        observed_activity_ids.add(activity_id)
        changed = True

    if not changed:
        return False

    current["updated_at"] = observed_at
    try:
        store.save_campaign(current, expected_version=version)
    except CampaignConflictError:
        return False
    return True


def sync_once(store=None, client: HackerOneClient | None = None) -> dict[str, int]:
    _require_enabled()
    store = store or create_storage()
    client = client or HackerOneClient()

    campaigns = store.list_campaigns(limit=_max_campaigns())
    stats = {
        "campaigns_checked": 0,
        "reports_checked": 0,
        "changes_recorded": 0,
        "errors": 0,
    }
    for document in campaigns:
        campaign_id = document.get("id")
        if not isinstance(campaign_id, str) or not campaign_id.strip():
            continue
        submissions = _submissions(document)
        if not submissions:
            continue
        stats["campaigns_checked"] += 1
        for submission in submissions:
            stats["reports_checked"] += 1
            try:
                if _sync_submission(store, client, campaign_id, submission):
                    stats["changes_recorded"] += 1
            except (HackerOneClientError, HTTPException, ValueError):
                stats["errors"] += 1
    return stats


def main() -> None:
    _require_enabled()
    worker_id = os.getenv(
        "XBOW_HACKERONE_REPORT_SYNC_WORKER_ID",
        f"hackerone-report-sync:{socket.gethostname()}:{os.getpid()}",
    )
    interval = _interval_seconds()
    while True:
        stats = sync_once()
        print(
            f"hackerone_report_sync worker_id={worker_id} "
            f"campaigns={stats['campaigns_checked']} "
            f"reports={stats['reports_checked']} "
            f"changes={stats['changes_recorded']} errors={stats['errors']}"
        )
        time.sleep(interval)


if __name__ == "__main__":
    main()
