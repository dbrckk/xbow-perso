from __future__ import annotations

from collections import Counter
from statistics import median
from typing import Any

from .learning_memory import build_learning_memory, summarize_worker_outcomes
from .observation_graph import load_observation_graph


_QUICK_GROUPS = ("easy", "medium", "high_value")


def _ready_candidates(programs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        dict(item)
        for item in programs
        if str(item.get("status") or "") == "READY"
        and item.get("offers_bounties") is True
        and str(item.get("handle") or "").strip()
    ]


def _decorate(item: dict[str, Any], group: str) -> dict[str, Any]:
    decorated = dict(item)
    decorated["quick_group"] = group
    decorated["automatic_launch"] = False
    decorated["requires_launch_revalidation"] = True
    return decorated


def select_quick_six(programs: list[dict[str, Any]]) -> dict[str, Any]:
    """Pick 2 low-effort, 2 medium-effort and 2 historically high-value READY programs.

    Labels are relative ranking heuristics only. They never bypass policy/scope review
    and historical bounty values are not treated as expected payout.
    """
    candidates = _ready_candidates(programs)
    remaining = list(candidates)

    high_ranked = sorted(
        remaining,
        key=lambda item: (
            -float(item.get("historical_usd_awarded_max") or 0.0),
            -float(item.get("historical_value_score") or 0.0),
            -int(item.get("opportunity_score") or 0),
            -int(item.get("value_efficiency_score") or 0),
            str(item.get("handle") or ""),
        ),
    )
    high_value = high_ranked[:2]
    used = {str(item.get("handle")) for item in high_value}
    remaining = [item for item in remaining if str(item.get("handle")) not in used]

    easy_ranked = sorted(
        remaining,
        key=lambda item: (
            float(item.get("effort_factor") or 99.0),
            -int(item.get("value_efficiency_score") or 0),
            -int(item.get("local_cost_efficiency_score") or 0),
            -int(item.get("opportunity_score") or 0),
            str(item.get("handle") or ""),
        ),
    )
    easy = easy_ranked[:2]
    used.update(str(item.get("handle")) for item in easy)
    remaining = [item for item in remaining if str(item.get("handle")) not in used]

    if remaining:
        effort_mid = median(float(item.get("effort_factor") or 1.0) for item in remaining)
    else:
        effort_mid = 1.0
    medium_ranked = sorted(
        remaining,
        key=lambda item: (
            abs(float(item.get("effort_factor") or 1.0) - effort_mid),
            -int(item.get("opportunity_score") or 0),
            -int(item.get("value_efficiency_score") or 0),
            str(item.get("handle") or ""),
        ),
    )
    medium = medium_ranked[:2]

    groups = {
        "easy": [_decorate(item, "easy") for item in easy],
        "medium": [_decorate(item, "medium") for item in medium],
        "high_value": [_decorate(item, "high_value") for item in high_value],
    }
    selection = [*groups["easy"], *groups["medium"], *groups["high_value"]]
    handles = [str(item.get("handle") or "") for item in selection]
    return {
        "strategy": "2_easy_2_medium_2_high_value",
        "groups": groups,
        "selection": selection,
        "handles": handles,
        "ready_candidates": len(candidates),
        "selected": len(selection),
        "complete": all(len(groups[name]) == 2 for name in _QUICK_GROUPS),
        "labels_are_relative_heuristics": True,
        "historical_value_is_not_expected_payout": True,
        "ready_only": True,
        "scope_expansion": False,
        "requires_launch_revalidation": True,
    }


def _campaign_brief(store, campaign_id: str, handle: str, member_status: str) -> dict[str, Any]:
    campaign = store.get_campaign(campaign_id) or {}
    findings = [item for item in list(campaign.get("findings") or []) if isinstance(item, dict)]
    confirmed = [item for item in findings if item.get("status") == "confirmed"]
    event_types = Counter(
        str(item.get("type") or "unknown")
        for item in list(campaign.get("events") or [])
        if isinstance(item, dict)
    )
    techniques: list[dict[str, Any]] = []
    try:
        graph = load_observation_graph(store, campaign_id)
        techniques = [item.to_dict() for item in build_learning_memory(graph, limit=20)]
    except Exception:
        techniques = []

    confirmed_summary = [
        {
            "title": str(item.get("title") or "")[:240],
            "severity": str(item.get("severity") or ""),
            "cwe": item.get("cwe"),
            "cvss": item.get("cvss"),
            "impact": str(item.get("impact") or "")[:1200],
        }
        for item in confirmed[:25]
    ]
    events = [item for item in list(campaign.get("events") or []) if isinstance(item, dict)]
    return {
        "campaign_id": campaign_id,
        "handle": handle,
        "member_status": member_status,
        "name": str((campaign.get("target") or {}).get("name") or handle),
        "state": str(campaign.get("state") or "unknown"),
        "created_at": campaign.get("created_at"),
        "updated_at": campaign.get("updated_at"),
        "finding_summary": {
            "total": len(findings),
            "confirmed": len(confirmed),
            "high_critical_confirmed": sum(
                1
                for item in confirmed
                if str(item.get("severity") or "") in {"high", "critical"}
            ),
            "rejected": sum(1 for item in findings if item.get("status") == "rejected"),
            "validation_required": sum(
                1 for item in findings if item.get("status") == "validation_required"
            ),
        },
        "confirmed_findings": confirmed_summary,
        "event_counts": dict(sorted(event_types.items())),
        "last_event": (
            {
                "type": str(events[-1].get("type") or "unknown"),
                "at": events[-1].get("at"),
            }
            if events
            else None
        ),
        "worker_outcomes": summarize_worker_outcomes(events),
        "technique_memory": techniques,
        "contains_raw_job_payloads": False,
        "contains_secrets": False,
    }


def build_batch_learning_brief(store, batch: dict[str, Any]) -> dict[str, Any]:
    members = [item for item in list(batch.get("members") or []) if isinstance(item, dict)]
    campaigns = [
        _campaign_brief(
            store,
            str(member.get("campaign_id") or ""),
            str(member.get("handle") or ""),
            str(member.get("status") or ""),
        )
        for member in members
        if str(member.get("campaign_id") or "")
    ]
    totals = {
        "campaigns": len(campaigns),
        "confirmed_findings": sum(
            int(item["finding_summary"]["confirmed"]) for item in campaigns
        ),
        "high_critical_confirmed": sum(
            int(item["finding_summary"]["high_critical_confirmed"]) for item in campaigns
        ),
        "worker_completed": sum(
            int(item["worker_outcomes"]["totals"]["completed"]) for item in campaigns
        ),
        "worker_failed": sum(
            int(item["worker_outcomes"]["totals"]["failed"]) for item in campaigns
        ),
    }
    return {
        "schema_version": 1,
        "kind": "xbow_runtime_learning_brief",
        "batch_id": str(batch.get("id") or ""),
        "batch_mode": str(batch.get("mode") or ""),
        "batch_state": str(batch.get("state") or ""),
        "created_at": batch.get("created_at"),
        "updated_at": batch.get("updated_at"),
        "summary": dict(batch.get("summary") or {}),
        "totals": totals,
        "campaigns": campaigns,
        "learning_scope": (
            "Evidence-backed outcomes, worker reliability and confirmed-finding metadata only. "
            "This brief never authorizes new targets, expands scope or changes execution gates."
        ),
        "contains_secrets": False,
        "contains_raw_job_payloads": False,
        "automatic_code_merge": False,
    }
