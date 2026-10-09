from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter

from .attack_surface import build_attack_surface
from .observation_graph import ObservationGraph, load_observation_graph
from .scan_result_integrity import conflicting_scan_terminal_job_ids
from .validation_state import analyze_validation_state

router = APIRouter()


def _completed_scans_with_provenance(
    graph: ObservationGraph,
    surface: dict[str, Any],
    *,
    scope_checker: Callable[[str], bool] | None,
) -> tuple[list[Any], int, int, int]:
    """Deduplicate completed scan jobs and reject untrusted scope or reports."""
    items = {item.id: item for item in graph.values()}
    assets = graph.by_kind("asset")
    approved_asset_ids = {
        item["id"]
        for item in surface["assets"]
        if item["in_scope"] is True
    }
    approved_endpoint_ids = {
        item["id"]
        for item in surface["endpoints"]
        if (
            item["valid"]
            and item["in_scope"] is True
            and not item["host_asset_mismatch"]
            and item["asset_parent_ids"]
        )
    }
    approved_form_ids = {
        item["id"]
        for item in surface["forms"]
        if item["valid"] and item["in_scope"] is True
    }

    def trustworthy_lineage(observation: Any) -> bool:
        if scope_checker is None:
            return True
        # Legacy scans without an asset reference are only assignable
        # when exactly one observed asset exists and it is authorized.
        if not observation.parent_ids:
            return len(assets) == 1 and assets[0].id in approved_asset_ids
        pending = list(observation.parent_ids)
        seen: set[str] = set()
        linked_assets: set[str] = set()
        while pending:
            parent_id = pending.pop()
            if parent_id in seen:
                continue
            seen.add(parent_id)
            parent = items.get(parent_id)
            if parent is None:
                return False
            if parent.kind == "asset":
                linked_assets.add(parent.id)
            else:
                if (
                    parent.kind == "endpoint"
                    and parent.id not in approved_endpoint_ids
                ):
                    # An invalid endpoint cannot gain completion credit via
                    # an otherwise authorized asset ancestor.
                    return False
                if (
                    parent.kind == "form"
                    and parent.id not in approved_form_ids
                ):
                    # Likewise, a malformed or out-of-scope form must not
                    # launder an otherwise in-scope scan completion claim.
                    return False
                pending.extend(parent.parent_ids)
        return bool(linked_assets) and linked_assets <= approved_asset_ids

    jobs: dict[str, list[Any]] = {}
    conflicting_terminal_jobs = conflicting_scan_terminal_job_ids(graph)
    untrusted_job_ids: set[str] = set()
    untrusted = 0
    accepted = 0
    for observation in graph.by_kind("evidence"):
        if (
            observation.metadata.get("phase") != "scan"
            or observation.metadata.get("status") != "completed"
        ):
            continue
        raw_job_id = observation.metadata.get("job_id")
        if raw_job_id is None:
            identity = f"observation:{observation.id}"
        elif (
            isinstance(raw_job_id, str)
            and 0 < len(raw_job_id.strip()) <= 128
            and not any(ord(char) < 32 for char in raw_job_id)
        ):
            identity = f"job:{raw_job_id.strip()}"
        else:
            untrusted += 1
            continue
        if (
            identity.startswith("job:")
            and identity[4:] in conflicting_terminal_jobs
        ):
            # A completed claim contradicted by a failed/cancelled claim
            # for this same worker job does not prove scan completion.
            untrusted += 1
            continue
        if not trustworthy_lineage(observation):
            untrusted += 1
            if identity.startswith("job:"):
                # A job documented on incompatible assets cannot be
                # credited through just its convenient in-scope record.
                untrusted_job_ids.add(identity)
            continue
        accepted += 1
        jobs.setdefault(identity, []).append(observation)

    for identity in untrusted_job_ids:
        if identity in jobs:
            count = len(jobs.pop(identity))
            accepted -= count
            untrusted += count

    representatives: list[Any] = []
    unreconciled = 0
    recorded_findings = len(graph.by_kind("finding"))
    for _identity, records in sorted(jobs.items()):
        # Multiple reporters attached to one execution do not prove
        # independence. Conflicting or missing source labels make the entire
        # job unsuitable for source and coverage metrics.
        sources = {
            item.source.strip() if isinstance(item.source, str) else ""
            for item in records
        }
        if len(sources) != 1 or "" in sources:
            untrusted += len(records)
            accepted -= len(records)
            continue
        reported_findings = [
            item.metadata["findings"]
            for item in records
            if "findings" in item.metadata
        ]
        # A completed scan claiming findings while the graph has none is
        # an ingestion discrepancy, not trustworthy negative-yield evidence.
        # Contradictory or malformed duplicate reports also taint that job.
        malformed = any(
            isinstance(value, bool)
            or not isinstance(value, int)
            or value < 0
            for value in reported_findings
        )
        inconsistent = (
            not malformed and len(set(reported_findings)) > 1
        )
        missing_recorded_findings = (
            not malformed
            and recorded_findings == 0
            and any(value > 0 for value in reported_findings)
        )
        if malformed or inconsistent or missing_recorded_findings:
            unreconciled += len(records)
            untrusted += len(records)
            accepted -= len(records)
            continue
        representatives.append(min(records, key=lambda item: item.id))
    return representatives, accepted - len(representatives), untrusted, unreconciled



def _endpoint_scan_attribution(
    graph: ObservationGraph,
    surface: dict[str, Any],
    scan_evidence: list[Any],
    *,
    scope_checker: Callable[[str], bool] | None,
) -> dict[str, Any]:
    """Describe observed endpoint-level evidence, never infer unseen coverage.

    A completed scan linked only to an asset is not proof of which of the
    asset's individual endpoints the scanner checked. Only explicit
    endpoint ancestry of a trusted completed scan contributes here.
    """
    eligible_ids = {
        row["id"]
        for row in surface["endpoints"]
        if (
            row["valid"]
            and row["in_scope"] is not False
            and (scope_checker is None or row["in_scope"] is True)
            and not row["host_asset_mismatch"]
            and row["asset_parent_ids"]
        )
    }
    items = {item.id: item for item in graph.values()}

    def explicit_endpoint_ancestry(scan: Any) -> frozenset[str]:
        pending = list(scan.parent_ids)
        visited: set[str] = set()
        endpoints: set[str] = set()
        while pending:
            parent_id = pending.pop()
            if parent_id in visited:
                continue
            visited.add(parent_id)
            parent = items.get(parent_id)
            if parent is None:
                continue
            if parent.kind == "endpoint":
                endpoints.add(parent.id)
                # Do not infer another endpoint from the same asset.
                continue
            if parent.kind != "asset":
                pending.extend(parent.parent_ids)
        return frozenset(endpoints)

    reports_by_job: dict[str, list[Any]] = {}
    for observation in graph.by_kind("evidence"):
        if (
            observation.metadata.get("phase") != "scan"
            or observation.metadata.get("status") != "completed"
        ):
            continue
        job_id = observation.metadata.get("job_id")
        if (
            isinstance(job_id, str)
            and 0 < len(job_id.strip()) <= 128
            and not any(ord(char) < 32 for char in job_id)
        ):
            reports_by_job.setdefault(job_id.strip(), []).append(observation)

    documented_ids: set[str] = set()
    ambiguous_scope_jobs = 0
    ineligible_scope_jobs = 0
    for scan in scan_evidence:
        job_id = scan.metadata.get("job_id")
        reports = (
            reports_by_job.get(job_id.strip(), [scan])
            if isinstance(job_id, str)
            else [scan]
        )
        # Job-level completion has already been reconciled. Endpoint scope
        # is a separate claim: conflicting duplicate reports cannot prove
        # either endpoint set, nor can an asset-only report corroborate
        # a report asserting an individual endpoint.
        endpoint_claims = {
            explicit_endpoint_ancestry(item) for item in reports
        }
        if len(endpoint_claims) != 1:
            ambiguous_scope_jobs += 1
            continue
        claimed_ids = next(iter(endpoint_claims))
        if not claimed_ids <= eligible_ids:
            # Do not credit the convenient in-scope subset of a scan job
            # that simultaneously asserts other, ineligible endpoints.
            ineligible_scope_jobs += 1
            continue
        documented_ids.update(claimed_ids)

    if not scan_evidence:
        state = "no_completed_scan_evidence"
        fraction = None
    elif not eligible_ids:
        state = "no_eligible_observed_endpoints"
        fraction = None
    elif not documented_ids:
        state = "endpoint_scope_unrecorded"
        fraction = None
    else:
        fraction = round(len(documented_ids) / len(eligible_ids), 4)
        state = (
            "all_observed_endpoints_documented"
            if len(documented_ids) == len(eligible_ids)
            else "partial_endpoint_documentation"
        )
    return {
        "state": state,
        "eligible_observed_endpoints": len(eligible_ids),
        "documented_scanned_endpoints": len(documented_ids),
        "documented_fraction": fraction,
        "ambiguous_endpoint_scope_jobs": ambiguous_scope_jobs,
        "ineligible_endpoint_scope_jobs": ineligible_scope_jobs,
        "not_proof_of_complete_scanning": True,
    }


def build_evidence_coverage(
    graph: ObservationGraph,
    *,
    scope_checker: Callable[[str], bool] | None = None,
) -> dict[str, Any]:
    surface = build_attack_surface(graph, scope_checker=scope_checker)
    summary = surface["summary"]
    discovery = float(summary["enrichment_score"])

    (
        scan_evidence,
        duplicate_scans,
        untrusted_scans,
        unreconciled_scans,
    ) = _completed_scans_with_provenance(
        graph,
        surface,
        scope_checker=scope_checker,
    )
    scanner_sources = sorted({
        str(item.source).strip()
        for item in scan_evidence
        if str(item.source).strip()
    })
    scan_count = len(scan_evidence)
    scan_score = 1.0 if scan_evidence else 0.0
    endpoint_attribution = _endpoint_scan_attribution(
        graph, surface, scan_evidence, scope_checker=scope_checker
    )

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
            "documented_endpoint_scan_fraction": endpoint_attribution[
                "documented_fraction"
            ],
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
            "endpoint_scan_attribution": endpoint_attribution,
            "completed_scans": scan_count,
            "duplicate_scan_observations": duplicate_scans,
            "untrusted_scan_observations": untrusted_scans,
            "unreconciled_scan_observations": unreconciled_scans,
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
    endpoint_attribution = (coverage.get("evidence") or {}).get(
        "endpoint_scan_attribution"
    ) or {}
    if not isinstance(endpoint_attribution, dict):
        endpoint_attribution = {}
    endpoint_state = str(endpoint_attribution.get("state") or "unknown")
    suspect_endpoint_claims = (
        max(0, int(endpoint_attribution.get("ambiguous_endpoint_scope_jobs") or 0))
        + max(0, int(endpoint_attribution.get("ineligible_endpoint_scope_jobs") or 0))
    )
    # This is documented evidence, not a completeness claim. Do not infer
    # endpoint-wide coverage from a completed asset-level scan.
    endpoint_fraction = dimensions.get("documented_endpoint_scan_fraction")
    unreconciled = max(
        0, int((coverage.get("evidence") or {}).get(
            "unreconciled_scan_observations"
        ) or 0),
    )
    untrusted = max(
        0, int((coverage.get("evidence") or {}).get(
            "untrusted_scan_observations"
        ) or 0),
    )

    if unreconciled:
        focus = "scan_result_reconciliation"
        reason = (
            "completed scan reports disagree with recorded findings; "
            "reconcile evidence before interpreting negative scan yield"
        )
    elif untrusted:
        focus = "scan_provenance_reconciliation"
        reason = (
            "recorded completed scans failed trust or scope verification; "
            "review existing scan provenance before recommending more scans"
        )
    elif discovery < 0.40:
        focus = "surface_discovery"
        reason = "surface evidence is still sparse"
    elif scanner < 1.0:
        focus = "scanner_execution"
        reason = "surface evidence exists but no completed scanner evidence is recorded"
    elif validation is not None and float(validation) < 1.0:
        focus = "independent_validation"
        reason = "not all observed findings have independent validation evidence"
    elif diminishing_returns >= 0.5 and (
        suspect_endpoint_claims
        or endpoint_state in {
            "endpoint_scope_unrecorded",
            "partial_endpoint_documentation",
        }
    ):
        focus = "endpoint_scan_scope_review"
        reason = (
            "repeated completed scans produced low finding yield, but "
            "their recorded endpoint scope is missing or incomplete; "
            "review existing in-scope endpoint scan provenance before "
            "interpreting the negative result"
        )
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
        "endpoint_scan_attribution_state": endpoint_state,
        "documented_endpoint_scan_fraction": endpoint_fraction,
        "recommended_strategy": (
            "review_endpoint_scan_provenance_before_more_scans"
            if focus == "endpoint_scan_scope_review"
            else "reconcile_scan_reports_before_replanning"
            if focus == "scan_result_reconciliation"
            else "review_untrusted_scan_provenance_before_more_scans"
            if focus == "scan_provenance_reconciliation"
            else "rotate_to_underexplored_in_scope_surface"
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
