from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter

from .attack_surface import build_attack_surface
from .observation_graph import ObservationGraph, load_observation_graph
from .validation_state import analyze_validation_state

router = APIRouter()


def build_evidence_coverage(
    graph: ObservationGraph,
    *,
    scope_checker: Callable[[str], bool] | None = None,
) -> dict[str, Any]:
    surface = build_attack_surface(graph, scope_checker=scope_checker)
    summary = surface["summary"]
    discovery = float(summary["enrichment_score"])

    scan_evidence = [
        item
        for item in graph.by_kind("evidence")
        if item.metadata.get("phase") == "scan"
        and item.metadata.get("status") == "completed"
    ]
    scanner_sources = sorted({item.source for item in scan_evidence})
    scan_count = len(scan_evidence)
    scan_score = 1.0 if scan_evidence else 0.0

    validation = analyze_validation_state(graph)
    finding_count = len(validation.finding_ids)
    validated_count = len(validation.observed_independent_finding_ids)
    validation_score = (
        round(validated_count / finding_count, 4) if finding_count else None
    )
    findings_per_scan = (
        round(finding_count / scan_count, 4) if scan_count else None
    )
    validated_per_scan = (
        round(validated_count / scan_count, 4) if scan_count else None
    )
    if scan_count >= 3 and finding_count == 0:
        diminishing_returns = min(1.0, round(scan_count / 6.0, 4))
    elif scan_count >= 6 and finding_count:
        diminishing_returns = min(
            1.0,
            round(scan_count / max(1.0, finding_count * 8.0), 4),
        )
    else:
        diminishing_returns = 0.0

    if validation_score is None:
        overall = round(discovery * 0.625 + scan_score * 0.375, 4)
    else:
        overall = round(
            discovery * 0.5 + scan_score * 0.3 + validation_score * 0.2,
            4,
        )

    return {
        "score": overall,
        "dimensions": {
            "surface_discovery": discovery,
            "scanner_execution": scan_score,
            "independent_validation": validation_score,
            "marginal_scan_yield": findings_per_scan,
            "validated_yield_per_scan": validated_per_scan,
            "diminishing_returns": diminishing_returns,
        },
        "evidence": {
            "assets": int(summary["asset_count"]),
            "endpoints": int(summary["valid_endpoint_count"]),
            "forms": int(summary["valid_form_count"]),
            "technologies": int(summary["technology_count"]),
            "waf_signals": int(summary["waf_count"]),
            "surface_source_diversity": int(summary["source_diversity"]),
            "scanner_sources": scanner_sources,
            "completed_scans": scan_count,
            "findings": finding_count,
            "independently_observed_findings": validated_count,
        },
        "interpretation": "evidence_coverage_not_unknown_surface_completeness",
        "read_only": True,
    }


@router.get("/api/campaigns/{campaign_id}/coverage")
def campaign_coverage(campaign_id: str):
    from .main import assert_campaign_exists, is_host_allowed, storage

    campaign = assert_campaign_exists(campaign_id)
    graph = load_observation_graph(storage(), campaign.id)
    rules = campaign.target.rules
    coverage = build_evidence_coverage(
        graph,
        scope_checker=lambda host: is_host_allowed(
            host,
            rules.allowed_targets,
            rules.denied_targets,
        ),
    )
    return {"campaign_id": campaign.id, **coverage}


def build_coverage_guidance(coverage: dict[str, Any]) -> dict[str, Any]:
    dimensions = coverage.get("dimensions") or {}
    discovery = float(dimensions.get("surface_discovery") or 0.0)
    scanner = float(dimensions.get("scanner_execution") or 0.0)
    validation = dimensions.get("independent_validation")
    diminishing_returns = float(dimensions.get("diminishing_returns") or 0.0)
    marginal_yield = dimensions.get("marginal_scan_yield")

    if discovery < 0.40:
        focus = "surface_discovery"
        reason = "surface evidence is still sparse"
    elif scanner < 1.0:
        focus = "scanner_execution"
        reason = "surface evidence exists but no completed scanner evidence is recorded"
    elif validation is not None and float(validation) < 1.0:
        focus = "independent_validation"
        reason = "not all observed findings have independent validation evidence"
    elif diminishing_returns >= 0.5:
        focus = "surface_rotation"
        reason = "repeated completed scans show low marginal finding yield; prefer an underexplored in-scope surface"
    else:
        focus = "none"
        reason = "no evidence-coverage gap requires advisory emphasis"

    return {
        "focus": focus,
        "reason": reason,
        "coverage_score": float(coverage.get("score") or 0.0),
        "marginal_scan_yield": marginal_yield,
        "diminishing_returns": diminishing_returns,
        "recommended_strategy": (
            "rotate_to_underexplored_in_scope_surface"
            if focus == "surface_rotation"
            else "continue_current_coverage_plan"
        ),
        "advisory_only": True,
        "may_unlock_actions": False,
        "interpretation": "evidence_guidance_not_security_assurance",
    }



def prioritize_action_with_coverage(
    action,
    guidance: dict[str, Any],
):
    """Bound priority of repetitive scans without changing action kind or target."""
    from .observation_graph import PlannedAction

    if not isinstance(action, PlannedAction):
        raise TypeError("action must be PlannedAction")

    signal = {
        "applied": False,
        "priority_delta": 0,
        "focus": str(guidance.get("focus") or "none"),
        "advisory_only": True,
        "action_kind_unchanged": True,
        "target_unchanged": True,
    }
    if action.kind != "scan" or signal["focus"] != "surface_rotation":
        return action, signal

    diminishing = max(0.0, min(1.0, float(guidance.get("diminishing_returns") or 0.0)))
    penalty = min(15, max(5, int(round(diminishing * 15))))
    adjusted = PlannedAction(
        kind=action.kind,
        target=action.target,
        reason=action.reason + "; marginal scan yield is low, deprioritized versus fresh in-scope surface work",
        priority=max(0, int(action.priority) - penalty),
    )
    signal.update({
        "applied": True,
        "priority_delta": -penalty,
        "diminishing_returns": diminishing,
    })
    return adjusted, signal
