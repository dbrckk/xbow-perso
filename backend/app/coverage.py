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
    scan_score = 1.0 if scan_evidence else 0.0

    validation = analyze_validation_state(graph)
    finding_count = len(validation.finding_ids)
    validated_count = len(validation.observed_independent_finding_ids)
    validation_score = (
        round(validated_count / finding_count, 4) if finding_count else None
    )

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
        },
        "evidence": {
            "assets": int(summary["asset_count"]),
            "endpoints": int(summary["valid_endpoint_count"]),
            "forms": int(summary["valid_form_count"]),
            "technologies": int(summary["technology_count"]),
            "waf_signals": int(summary["waf_count"]),
            "surface_source_diversity": int(summary["source_diversity"]),
            "scanner_sources": scanner_sources,
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
