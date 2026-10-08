from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Callable, Iterable, Mapping

from .attack_surface import build_attack_surface
from .observation_graph import ObservationGraph


NO_FINDING_RECOVERY_SCHEMA = "no-finding-recovery-v1"
_ALLOWED_RECON_KINDS = frozenset(
    {"crawl", "map_endpoints", "map_forms", "detect_technology", "browser_observe"}
)
_ENDPOINT_REVIEW_TYPES = frozenset(
    {"input_surface_review", "authorization_surface_review"}
)


@dataclass(frozen=True)
class NoFindingRecovery:
    schema: str
    state: str
    completed_scan_count: int
    scanner_source_count: int
    finding_count: int
    in_scope_endpoint_count: int
    in_scope_form_count: int
    uncovered_endpoint_count: int
    uncovered_form_count: int
    missing_technology_context: bool
    scope_integrity_issues: int
    recommended_task_kinds: tuple[str, ...]
    reasons: tuple[str, ...]
    advisory_only: bool = True
    may_expand_scope: bool = False
    may_increase_request_budget: bool = False
    may_enable_exploitation: bool = False
    may_change_execution_gate: bool = False
    negative_result_proves_safe: bool = False

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["recommended_task_kinds"] = list(self.recommended_task_kinds)
        result["reasons"] = list(self.reasons)
        return result


def _reviewed_ids(graph: ObservationGraph, review_types: frozenset[str]) -> set[str]:
    reviewed: set[str] = set()
    for item in graph.by_kind("evidence"):
        if item.metadata.get("review_type") in review_types:
            reviewed.update(item.parent_ids)
    return reviewed


def _completed_scan_evidence(graph: ObservationGraph) -> tuple[int, int]:
    # Multiple observations for one worker job must not inflate negative yield.
    scan_keys: set[str] = set()
    sources: set[str] = set()
    for item in graph.by_kind("evidence"):
        if (
            item.metadata.get("phase") != "scan"
            or item.metadata.get("status") != "completed"
        ):
            continue
        job_id = str(item.metadata.get("job_id") or "").strip()
        key = f"job:{job_id}" if job_id else f"observation:{item.id}"
        scan_keys.add(key)
        if str(item.source).strip():
            sources.add(str(item.source).strip())
    return len(scan_keys), len(sources)


def _unstable_scanner_outcomes(outcomes: Mapping[str, Any] | None) -> bool:
    by_kind = (outcomes or {}).get("by_job_kind")
    if not isinstance(by_kind, Mapping):
        return False
    for kind in ("strix_scan", "nuclei_scan"):
        counts = by_kind.get(kind)
        if not isinstance(counts, Mapping):
            continue
        try:
            completed = int(counts.get("completed") or 0)
            failed = int(counts.get("failed") or 0)
            requeued = int(counts.get("requeued") or 0)
        except (TypeError, ValueError):
            return True
        if completed <= 0 and failed + requeued >= 2:
            return True
    return False


def build_no_finding_recovery(
    graph: ObservationGraph,
    *,
    scope_checker: Callable[[str], bool] | None,
    available_task_kinds: Iterable[str] = (),
    campaign_finding_count: int = 0,
    worker_outcomes: Mapping[str, Any] | None = None,
) -> NoFindingRecovery:
    """Rank *existing* authorized recon task kinds after evidence-backed null scans.

    This is observation-only feedback, not a scanner/exploit dispatcher. Missing
    findings are not evidence that a target is safe. No new target, capability,
    permission, request or task kind can be minted by this function.
    """
    if campaign_finding_count < 0:
        raise ValueError("campaign_finding_count must not be negative")
    allowed = {
        kind
        for kind in available_task_kinds
        if kind in _ALLOWED_RECON_KINDS
    }
    completed_scans, scanner_sources = _completed_scan_evidence(graph)
    finding_count = max(campaign_finding_count, len(graph.by_kind("finding")))
    surface = build_attack_surface(graph, scope_checker=scope_checker)

    endpoints = [
        item for item in surface["endpoints"]
        if (
            item["valid"]
            and item["in_scope"] is True
            and not item["host_asset_mismatch"]
            and item["asset_parent_ids"]
        )
    ]
    forms = [
        item for item in surface["forms"]
        if item["valid"] and item["in_scope"] is True
    ]
    endpoint_reviewed = _reviewed_ids(graph, _ENDPOINT_REVIEW_TYPES)
    form_reviewed = _reviewed_ids(graph, frozenset({"form_surface_review"}))
    uncovered_endpoints = sum(
        item["id"] not in endpoint_reviewed for item in endpoints
    )
    uncovered_forms = sum(item["id"] not in form_reviewed for item in forms)
    scope_issues = sum(
        item["valid"] and item["in_scope"] is True
        and (
            item["host_asset_mismatch"] or not item["asset_parent_ids"]
        )
        for item in surface["endpoints"]
    )
    missing_technology = not bool(graph.by_kind("technology"))
    reasons: list[str] = []
    candidates: list[tuple[int, str]] = []

    if finding_count:
        state = "findings_present"
        reasons.append("findings require the normal validation and review path")
    elif scope_checker is None:
        state = "scope_unverified"
        reasons.append("scope verification is required before suggesting recon")
    elif _unstable_scanner_outcomes(worker_outcomes):
        state = "execution_unstable"
        reasons.append("repeated scanner worker errors require operator review")
    elif not completed_scans:
        state = "no_completed_scans"
        reasons.append("no successful scan evidence exists; no negative yield can be inferred")
    elif not surface["summary"]["in_scope_asset_count"]:
        state = "scope_unverified"
        reasons.append("no authorized observed asset is available for a safe recon plan")
    else:
        state = "recovery_advisory"
        if scope_issues:
            reasons.append("observed endpoints lack reliable asset lineage")
            candidates.append((100, "map_endpoints"))
        if not endpoints:
            reasons.append("authorized endpoint inventory is missing or untrusted")
            candidates.append((95, "crawl"))
        else:
            if not forms:
                reasons.append("form surface has not been observed")
                candidates.append((85, "map_forms"))
            elif uncovered_forms:
                reasons.append("some observed forms lack recorded review evidence")
                candidates.append((83, "browser_observe"))
            if missing_technology:
                reasons.append("technology inventory is missing")
                candidates.append((80, "detect_technology"))
            if uncovered_endpoints:
                reasons.append("observed endpoints lack recorded review evidence")
                candidates.append((75, "map_endpoints"))
            if completed_scans >= 3:
                reasons.append("repeated completed scans yielded no observed finding; rotate coverage rather than repeat identical tests")
                candidates.append((55, "browser_observe"))
                candidates.append((50, "map_endpoints"))
        if not candidates:
            state = "no_supported_recovery_task"
            reasons.append("no evidence-backed recon gap is available")
    recommended = tuple(
        kind
        for _score, kind in sorted(set(candidates), key=lambda item: (-item[0], item[1]))
        if kind in allowed
    )
    # A kind may appear with different scores; never recommend it twice.
    recommended = tuple(dict.fromkeys(recommended))[:3]
    if state == "recovery_advisory" and not recommended:
        state = "no_supported_recovery_task"
        reasons.append("no currently authorized recon task matches the evidence gaps")

    return NoFindingRecovery(
        schema=NO_FINDING_RECOVERY_SCHEMA,
        state=state,
        completed_scan_count=completed_scans,
        scanner_source_count=scanner_sources,
        finding_count=finding_count,
        in_scope_endpoint_count=len(endpoints),
        in_scope_form_count=len(forms),
        uncovered_endpoint_count=uncovered_endpoints,
        uncovered_form_count=uncovered_forms,
        missing_technology_context=missing_technology,
        scope_integrity_issues=scope_issues,
        recommended_task_kinds=recommended,
        reasons=tuple(dict.fromkeys(reasons)),
    )
