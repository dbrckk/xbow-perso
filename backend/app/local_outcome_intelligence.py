from __future__ import annotations

from typing import Any


_TERMINAL_STATES = {"completed", "failed", "cancelled"}


def _verified_hackerone_handle(campaign: dict[str, Any]) -> str | None:
    for event in reversed(list(campaign.get("events") or [])):
        if not isinstance(event, dict) or event.get("type") != "hackerone_policy_bound":
            continue
        binding = event.get("remote_binding")
        if (
            isinstance(binding, dict)
            and binding.get("verified") is True
            and isinstance(binding.get("handle"), str)
            and binding["handle"].strip()
        ):
            return binding["handle"].strip()
        return None
    return None


def build_local_outcome_signals(
    campaigns: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Learn bounded advisory signals from this repo's own HackerOne outcomes."""
    raw: dict[str, dict[str, Any]] = {}

    for campaign in campaigns:
        if not isinstance(campaign, dict):
            continue
        handle = _verified_hackerone_handle(campaign)
        if not handle:
            continue

        record = raw.setdefault(
            handle,
            {
                "campaign_count": 0,
                "terminal_campaign_count": 0,
                "successful_campaign_count": 0,
                "confirmed_finding_count": 0,
                "high_critical_confirmed_count": 0,
                "submitted_report_count": 0,
            },
        )
        record["campaign_count"] += 1

        findings = [
            item
            for item in list(campaign.get("findings") or [])
            if isinstance(item, dict) and item.get("status") == "confirmed"
        ]
        confirmed_count = len(findings)
        high_critical = sum(
            1 for item in findings if str(item.get("severity") or "") in {"high", "critical"}
        )
        submitted = sum(
            1
            for event in list(campaign.get("events") or [])
            if isinstance(event, dict) and event.get("type") == "hackerone_report_submitted"
        )

        record["confirmed_finding_count"] += confirmed_count
        record["high_critical_confirmed_count"] += high_critical
        record["submitted_report_count"] += submitted

        if str(campaign.get("state") or "") in _TERMINAL_STATES:
            record["terminal_campaign_count"] += 1
            if confirmed_count:
                record["successful_campaign_count"] += 1

    result: dict[str, dict[str, Any]] = {}
    for handle, record in raw.items():
        terminal = int(record["terminal_campaign_count"])
        successes = int(record["successful_campaign_count"])
        # Beta(1,3) prior keeps tiny samples from dominating ranking.
        smoothed_success_rate = (successes + 1.0) / (terminal + 4.0)
        evidence_points = (
            min(4, int(record["confirmed_finding_count"]))
            + min(3, int(record["high_critical_confirmed_count"]))
            + min(3, int(record["submitted_report_count"]))
        )
        confidence = min(1.0, terminal / 5.0)
        local_score = int(round(evidence_points * confidence))
        result[handle] = {
            **record,
            "smoothed_success_rate": round(smoothed_success_rate, 3),
            "local_outcome_score": min(10, local_score),
            "advisory_only": True,
            "automatic_launch": False,
            "scope_expansion": False,
        }

    return result
