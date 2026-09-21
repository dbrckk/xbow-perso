from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_TERMINAL_CAMPAIGN_STATES = {"completed", "failed", "cancelled"}


def _num(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def select_quick_portfolio(programs: list[dict[str, Any]]) -> dict[str, Any]:
    """Pick six unique READY bounty programs: 2 easy, 2 medium, 2 high-value."""
    ready = [
        dict(item)
        for item in programs
        if str(item.get("status") or "") == "READY"
        and item.get("offers_bounties") is True
    ]
    picked: list[dict[str, Any]] = []
    used: set[str] = set()

    def take(items: list[dict[str, Any]], label: str, count: int = 2) -> None:
        for item in items:
            handle = str(item.get("handle") or "")
            if not handle or handle in used:
                continue
            enriched = dict(item)
            enriched["quick_bucket"] = label
            picked.append(enriched)
            used.add(handle)
            if sum(1 for row in picked if row["quick_bucket"] == label) >= count:
                break

    easy = sorted(
        ready,
        key=lambda item: (
            _num(item.get("effort_factor")),
            -int(item.get("value_efficiency_score") or 0),
            -int(item.get("opportunity_score") or 0),
            str(item.get("handle") or ""),
        ),
    )
    take(easy, "easy")

    medium = sorted(
        ready,
        key=lambda item: (
            abs(_num(item.get("effort_factor")) - 1.5),
            -int(item.get("opportunity_score") or 0),
            -int(item.get("value_efficiency_score") or 0),
            str(item.get("handle") or ""),
        ),
    )
    take(medium, "medium")

    high_value = sorted(
        ready,
        key=lambda item: (
            -_num(item.get("historical_usd_awarded_max")),
            -_num(item.get("historical_value_score")),
            -int(item.get("opportunity_score") or 0),
            str(item.get("handle") or ""),
        ),
    )
    take(high_value, "high_value")

    counts = Counter(str(item["quick_bucket"]) for item in picked)
    shortages = {
        key: max(0, 2 - int(counts.get(key, 0)))
        for key in ("easy", "medium", "high_value")
    }
    return {
        "selection": picked,
        "handles": [str(item["handle"]) for item in picked],
        "summary": {
            "total": len(picked),
            "easy": int(counts.get("easy", 0)),
            "medium": int(counts.get("medium", 0)),
            "high_value": int(counts.get("high_value", 0)),
            "shortages": shortages,
        },
        "ready_pool": len(ready),
        "requires_exact_review_profile": True,
        "automatic_scope_expansion": False,
        "historical_reward_is_advisory": True,
    }


def _duration_seconds(campaign: dict[str, Any]) -> int | None:
    try:
        created = datetime.fromisoformat(str(campaign.get("created_at") or "").replace("Z", "+00:00"))
        updated = datetime.fromisoformat(str(campaign.get("updated_at") or "").replace("Z", "+00:00"))
    except ValueError:
        return None
    if created.tzinfo is None or updated.tzinfo is None:
        return None
    return max(0, int((updated - created).total_seconds()))


def campaign_brief(campaign: dict[str, Any]) -> dict[str, Any]:
    findings = [item for item in list(campaign.get("findings") or []) if isinstance(item, dict)]
    events = [item for item in list(campaign.get("events") or []) if isinstance(item, dict)]
    event_counts = Counter(str(item.get("type") or "unknown") for item in events)
    confirmed = [item for item in findings if item.get("status") == "confirmed"]
    severities = Counter(str(item.get("severity") or "unknown") for item in confirmed)
    confirmed_summary = [
        {
            "title": str(item.get("title") or "")[:240],
            "severity": str(item.get("severity") or "unknown"),
            "cwe": str(item.get("cwe") or "")[:32] or None,
            "discovered_by": str(item.get("discovered_by") or "")[:120] or None,
            "validated_by": str(item.get("validated_by") or "")[:120] or None,
        }
        for item in confirmed[:50]
    ]
    return {
        "campaign_id": str(campaign.get("id") or ""),
        "name": str((campaign.get("target") or {}).get("name") or ""),
        "state": str(campaign.get("state") or ""),
        "created_at": campaign.get("created_at"),
        "updated_at": campaign.get("updated_at"),
        "duration_seconds": _duration_seconds(campaign),
        "findings_total": len(findings),
        "findings_confirmed": len(confirmed),
        "confirmed_by_severity": dict(severities),
        "confirmed_findings": confirmed_summary,
        "events_total": len(events),
        "event_type_counts": dict(event_counts),
        "activity": {
            key: int(value)
            for key, value in event_counts.items()
            if key in {
                "campaign_started",
                "recon_task_completed",
                "browser_flow_completed",
                "scan_completed",
                "validation_completed",
                "finding_confirmed",
                "report_generated",
                "hackerone_report_submitted",
                "worker_outcome",
            }
        },
        "terminal": str(campaign.get("state") or "") in _TERMINAL_CAMPAIGN_STATES,
    }


def batch_journal_entry(
    batch: dict[str, Any],
    campaigns_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    members = []
    for member in list(batch.get("members") or []):
        campaign_id = str(member.get("campaign_id") or "")
        campaign = campaigns_by_id.get(campaign_id)
        members.append({
            "handle": str(member.get("handle") or ""),
            "status": str(member.get("status") or ""),
            "reason": member.get("reason"),
            "campaign": campaign_brief(campaign) if campaign else None,
        })
    return {
        "batch_id": str(batch.get("id") or ""),
        "mode": str(batch.get("mode") or ""),
        "state": str(batch.get("state") or ""),
        "created_at": batch.get("created_at"),
        "updated_at": batch.get("updated_at"),
        "continues_without_dashboard": bool(batch.get("continues_without_dashboard")),
        "summary": dict(batch.get("summary") or {}),
        "members": members,
    }


def learning_digest(
    batch: dict[str, Any],
    campaigns_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    journal = batch_journal_entry(batch, campaigns_by_id)
    totals = Counter()
    event_totals = Counter()
    for member in journal["members"]:
        campaign = member.get("campaign") or {}
        totals["campaigns"] += 1
        totals["findings_total"] += int(campaign.get("findings_total") or 0)
        totals["findings_confirmed"] += int(campaign.get("findings_confirmed") or 0)
        for key, value in dict(campaign.get("activity") or {}).items():
            event_totals[key] += int(value or 0)
    return {
        "schema_version": 1,
        "kind": "xbow_runtime_learning_digest",
        "batch_id": journal["batch_id"],
        "mode": journal["mode"],
        "state": journal["state"],
        "created_at": journal["created_at"],
        "updated_at": journal["updated_at"],
        "totals": dict(totals),
        "activity_totals": dict(event_totals),
        "campaigns": journal["members"],
        "sanitized": True,
        "contains_secrets": False,
        "contains_evidence_bodies": False,
        "contains_target_urls": False,
        "advisory_only": True,
        "may_inform_future_prioritization": True,
        "may_not_expand_scope": True,
        "may_not_enable_tools": True,
    }


def persist_learning_digest(
    batch: dict[str, Any],
    campaigns_by_id: dict[str, dict[str, Any]],
    *,
    root: str = "/data/learning_exports",
) -> str | None:
    if str(batch.get("state") or "") != "completed":
        return None
    digest = learning_digest(batch, campaigns_by_id)
    batch_id = str(batch.get("id") or "").strip()
    if not batch_id:
        return None
    directory = Path(root)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{batch_id}.json"
    payload = json.dumps(digest, sort_keys=True, ensure_ascii=False, indent=2) + "\n"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(path)
    return str(path)
