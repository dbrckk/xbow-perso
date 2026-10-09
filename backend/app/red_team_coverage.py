from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Callable

from fastapi import APIRouter

from .attack_surface import build_attack_surface
from .coverage import (
    _endpoint_has_consistent_asset_origins,
    _form_has_consistent_asset_origins,
)
from .evidence_chain import build_evidence_chains
from .hypothesis_engine import build_hypotheses
from .review_evidence import is_completed_review_evidence
from .observation_graph import ObservationGraph, load_observation_graph
from .validation_state import analyze_validation_state

router = APIRouter()


@dataclass(frozen=True)
class CoverageDomain:
    name: str
    observed: int
    reviewed: int
    validated: int
    gaps: int
    score: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _ratio(numerator: int, denominator: int) -> float:
    # Missing observations are unknown coverage, not 100% reviewed.
    return round(numerator / denominator, 4) if denominator else 0.0


def _reviewed_parent_ids(
    graph: ObservationGraph,
    review_types: set[str],
    *,
    eligible_ids: set[str],
) -> set[str]:
    """Credit a review only when all direct parents are eligible surfaces.

    A record linking an in-scope endpoint and an unrelated asset/finding (or
    out-of-scope endpoint) must not close the endpoint's review gap.
    """
    reviewed: set[str] = set()
    for item in graph.by_kind("evidence"):
        if (
            item.metadata.get("review_type") not in review_types
            or not is_completed_review_evidence(item)
        ):
            continue
        parents = set(item.parent_ids)
        if parents and parents <= eligible_ids:
            reviewed.update(parents)
    return reviewed


def build_red_team_coverage(
    graph: ObservationGraph,
    *,
    scope_checker: Callable[[str], bool] | None = None,
) -> dict[str, Any]:
    """Summarize bounded, evidence-backed and optionally scope-aware coverage."""
    surface = build_attack_surface(graph, scope_checker=scope_checker)
    hypotheses = build_hypotheses(graph, limit=100, scope_checker=scope_checker)
    chains = build_evidence_chains(graph)
    validation = analyze_validation_state(graph)

    valid_endpoint_ids = {
        item["id"]
        for item in surface["endpoints"]
        if item["valid"] and item["in_scope"] is not False
    }
    valid_form_ids = {
        item["id"]
        for item in surface["forms"]
        if item["valid"] and item["in_scope"] is not False
    }
    # Keep observed-but-untrusted surfaces in the denominator as gaps.
    # Only review attribution is gated on verified in-scope ancestry.
    if scope_checker is None:
        reviewable_endpoint_ids = set(valid_endpoint_ids)
        reviewable_form_ids = set(valid_form_ids)
    else:
        observations = {item.id: item for item in graph.values()}
        asset_values = {
            item.id: item.value for item in graph.by_kind("asset")
        }
        reviewable_endpoint_ids = {
            item["id"]
            for item in surface["endpoints"]
            if (
                item["id"] in valid_endpoint_ids
                and item["in_scope"] is True
                and not item["host_asset_mismatch"]
                and _endpoint_has_consistent_asset_origins(
                    item, asset_values
                )
            )
        }
        reviewable_form_ids = {
            item["id"]
            for item in surface["forms"]
            if (
                item["id"] in valid_form_ids
                and item["in_scope"] is True
                and _form_has_consistent_asset_origins(
                    item["id"],
                    item["action"],
                    observations,
                    asset_values,
                    reviewable_endpoint_ids,
                )
            )
        }

    technology_ids = {
        item["id"]
        for item in surface["technologies"]
        if scope_checker is None
        or any(
            hypothesis.evidence_ids == (item["id"],)
            for hypothesis in hypotheses
            if hypothesis.kind == "technology_surface_review"
        )
    }
    waf_ids = {
        item["id"]
        for item in surface["wafs"]
        if scope_checker is None
        or any(
            hypothesis.evidence_ids == (item["id"],)
            for hypothesis in hypotheses
            if hypothesis.kind == "protection_surface_review"
        )
    }
    endpoints = len(valid_endpoint_ids)
    forms = len(valid_form_ids)
    technologies = len(technology_ids)
    wafs = len(waf_ids)

    in_scope_finding_ids = {
        hypothesis.evidence_ids[0]
        for hypothesis in hypotheses
        if hypothesis.kind == "validation_gap"
    }
    if scope_checker is None:
        finding_ids = set(validation.finding_ids)
    else:
        finding_ids = set(validation.observed_independent_finding_ids) | in_scope_finding_ids
    findings = len(finding_ids)

    input_reviews = sum(item.kind == "input_surface_review" for item in hypotheses)
    authorization_reviews = sum(item.kind == "authorization_surface_review" for item in hypotheses)
    form_reviews = sum(item.kind == "form_surface_review" for item in hypotheses)
    technology_reviews = sum(item.kind == "technology_surface_review" for item in hypotheses)
    protection_reviews = sum(item.kind == "protection_surface_review" for item in hypotheses)
    validation_gaps = sum(item.kind == "validation_gap" for item in hypotheses)
    complete_chain_ids = {item.finding_id for item in chains if item.complete}
    complete_chains = len(complete_chain_ids & finding_ids)

    endpoint_reviewed_ids = _reviewed_parent_ids(
        graph,
        {"input_surface_review", "authorization_surface_review"},
        eligible_ids=reviewable_endpoint_ids,
    )
    form_reviewed_ids = _reviewed_parent_ids(
        graph,
        {"form_surface_review"},
        eligible_ids=reviewable_form_ids,
    )
    technology_reviewed_ids = _reviewed_parent_ids(
        graph,
        {"technology_surface_review"},
        eligible_ids=technology_ids,
    )
    waf_reviewed_ids = _reviewed_parent_ids(
        graph,
        {"protection_surface_review"},
        eligible_ids=waf_ids,
    )
    validated_finding_ids = set(validation.observed_independent_finding_ids) & finding_ids
    attempted_finding_ids = set(validation.attempted_finding_ids) & finding_ids

    domains = (
        CoverageDomain(
            name="endpoint_surface",
            observed=endpoints,
            reviewed=len(endpoint_reviewed_ids),
            validated=0,
            gaps=max(0, endpoints - len(endpoint_reviewed_ids)),
            score=_ratio(len(endpoint_reviewed_ids), endpoints),
        ),
        CoverageDomain(
            name="form_surface",
            observed=forms,
            reviewed=len(form_reviewed_ids),
            validated=0,
            gaps=max(0, forms - len(form_reviewed_ids)),
            score=_ratio(len(form_reviewed_ids), forms),
        ),
        CoverageDomain(
            name="technology_surface",
            observed=technologies,
            reviewed=len(technology_reviewed_ids),
            validated=0,
            gaps=max(0, technologies - len(technology_reviewed_ids)),
            score=_ratio(len(technology_reviewed_ids), technologies),
        ),
        CoverageDomain(
            name="protection_surface",
            observed=wafs,
            reviewed=len(waf_reviewed_ids),
            validated=0,
            gaps=max(0, wafs - len(waf_reviewed_ids)),
            score=_ratio(len(waf_reviewed_ids), wafs),
        ),
        CoverageDomain(
            name="finding_validation",
            observed=findings,
            reviewed=len(attempted_finding_ids),
            validated=len(validated_finding_ids),
            gaps=validation_gaps,
            score=_ratio(len(validated_finding_ids), findings),
        ),
        CoverageDomain(
            name="evidence_quality",
            observed=findings,
            reviewed=findings,
            validated=complete_chains,
            gaps=max(0, findings - complete_chains),
            score=_ratio(complete_chains, findings),
        ),
    )

    observed_domains = tuple(item for item in domains if item.observed > 0)
    unobserved_domains = tuple(
        item.name for item in domains if item.observed == 0
    )
    weighted_denominator = sum(item.observed for item in observed_domains)
    weighted_score = (
        round(
            sum(item.score * item.observed for item in observed_domains)
            / weighted_denominator,
            4,
        )
        if weighted_denominator
        else 0.0
    )

    gaps = []
    if surface["summary"]["invalid_endpoint_count"]:
        gaps.append("invalid_endpoints")
    if surface["summary"]["orphan_endpoint_count"]:
        gaps.append("orphan_endpoints")
    if surface["summary"]["host_asset_mismatch_count"]:
        gaps.append("host_asset_mismatch")
    if valid_endpoint_ids - reviewable_endpoint_ids:
        gaps.append("untrusted_endpoint_origin")
    if valid_form_ids - reviewable_form_ids:
        gaps.append("untrusted_form_origin")
    if input_reviews:
        gaps.append("input_review_pending")
    if authorization_reviews:
        gaps.append("authorization_review_pending")
    if form_reviews:
        gaps.append("form_review_pending")
    if technology_reviews:
        gaps.append("technology_review_pending")
    if protection_reviews:
        gaps.append("protection_review_pending")
    if validation_gaps:
        gaps.append("independent_validation_pending")
    if findings - complete_chains:
        gaps.append("evidence_chain_incomplete")

    return {
        "score": weighted_score,
        "domains": [item.to_dict() for item in domains],
        "gaps": gaps,
        "observation_state": (
            "observed_surface_only" if observed_domains else "no_observed_surface"
        ),
        "unobserved_domains": list(unobserved_domains),
        "score_interpretation": "review_coverage_of_observed_surface_not_security_assurance",
        "summary": {
            "observed_domain_count": len(observed_domains),
            "unobserved_domain_count": len(unobserved_domains),
            "observed_endpoints": endpoints,
            "reviewed_endpoints": len(endpoint_reviewed_ids),
            "untrusted_endpoint_origins": len(
                valid_endpoint_ids - reviewable_endpoint_ids
            ),
            "observed_forms": forms,
            "reviewed_forms": len(form_reviewed_ids),
            "untrusted_form_origins": len(
                valid_form_ids - reviewable_form_ids
            ),
            "observed_technologies": technologies,
            "reviewed_technologies": len(technology_reviewed_ids),
            "observed_wafs": wafs,
            "reviewed_wafs": len(waf_reviewed_ids),
            "observed_findings": findings,
            "independently_validated_findings": len(validated_finding_ids),
            "complete_evidence_chains": complete_chains,
            "pending_hypotheses": len(hypotheses),
        },
        "read_only": True,
        "safe_validation_only": True,
        "scope_aware": scope_checker is not None,
    }


@router.get("/api/campaigns/{campaign_id}/red-team-coverage")
def campaign_red_team_coverage(campaign_id: str):
    from .main import assert_campaign_exists, is_host_allowed, storage

    campaign = assert_campaign_exists(campaign_id)
    graph = load_observation_graph(storage(), campaign.id)
    rules = campaign.target.rules
    return {
        "campaign_id": campaign.id,
        **build_red_team_coverage(
            graph,
            scope_checker=lambda host: is_host_allowed(host, rules.allowed_targets, rules.denied_targets),
        ),
    }
