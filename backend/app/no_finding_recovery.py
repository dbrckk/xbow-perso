from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Mapping
from urllib.parse import urlsplit

from .attack_surface import build_attack_surface
from .observation_graph import ObservationGraph
from .review_evidence import is_completed_review_evidence
from .scan_result_integrity import conflicting_scan_terminal_job_ids


NO_FINDING_RECOVERY_SCHEMA = "no-finding-recovery-v1"
_REVISIT_SURFACE_KINDS: dict[str, frozenset[str]] = {
    "crawl": frozenset({"endpoint", "form"}),
    "map_endpoints": frozenset({"endpoint"}),
    "map_forms": frozenset({"endpoint", "form"}),
    "detect_technology": frozenset({"endpoint", "technology", "waf"}),
    "browser_observe": frozenset({"endpoint", "form", "technology"}),
}
_ALLOWED_RECON_KINDS = frozenset(
    {"crawl", "map_endpoints", "map_forms", "detect_technology", "browser_observe"}
)
_ENDPOINT_REVIEW_TYPES = frozenset(
    {"input_surface_review", "authorization_surface_review"}
)
_SUCCESSFUL_RECON_OUTCOMES = frozenset(
    {"completed", "success", "observed", "no_findings", "no_change"}
)


def _is_completed_recon_step(observation: Any) -> bool:
    """Do not exhaust a recovery task on contradictory terminal evidence."""
    metadata = observation.metadata
    if metadata.get("status") != "completed":
        return False
    outcome = metadata.get("outcome")
    return (
        outcome is None
        or (
            isinstance(outcome, str)
            and outcome.strip().lower() in _SUCCESSFUL_RECON_OUTCOMES
        )
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
    exhausted_task_kinds: tuple[str, ...] = ()
    reopened_task_kinds: tuple[str, ...] = ()
    ambiguous_scan_source_jobs: int = 0
    contradictory_scan_terminal_jobs: int = 0
    unreconciled_scan_reports: int = 0
    trusted_completed_scan_count: int = 0
    worker_health_attribution: str = "campaign_aggregate"
    worker_instability_observed: bool = False
    worker_instability_applied: bool = False
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
        result["exhausted_task_kinds"] = list(self.exhausted_task_kinds)
        result["reopened_task_kinds"] = list(self.reopened_task_kinds)
        return result


def _trusted_utc_timestamp(value: object, *, now: datetime) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    parsed = parsed.astimezone(timezone.utc)
    if parsed > now:
        return None
    return parsed


def _origin(value: str) -> tuple[str, str, int] | None:
    """Parse a web origin without accepting credentials or ambiguous ports."""
    raw = str(value or "").strip()
    try:
        parsed = urlsplit(raw)
        scheme = parsed.scheme.lower()
        host = (parsed.hostname or "").lower().rstrip(".")
        if (
            scheme not in {"http", "https"}
            or not host
            or parsed.username is not None
            or parsed.password is not None
        ):
            return None
        port = parsed.port
    except ValueError:
        return None
    if port is None:
        port = 443 if scheme == "https" else 80
    return scheme, host, port


def _asset_matches_origin(
    value: str,
    target: tuple[str, str, int],
) -> bool:
    """Allow legacy hostname-only assets, never incompatible explicit origins."""
    raw = str(value or "").strip()
    if "://" in raw:
        return _origin(raw) == target
    try:
        parsed = urlsplit(f"//{raw}")
        host = (parsed.hostname or "").lower().rstrip(".")
        port = parsed.port
        if parsed.username is not None or parsed.password is not None:
            return False
    except ValueError:
        return False
    return bool(
        host == target[1]
        and (port is None or port == target[2])
    )


def _reviewed_ids(
    graph: ObservationGraph,
    review_types: frozenset[str],
    *,
    allowed_parent_ids: set[str],
) -> set[str]:
    """Only explicit, completed reviews may close in-scope coverage gaps."""
    reviewed: set[str] = set()
    for item in graph.by_kind("evidence"):
        if (
            item.metadata.get("review_type") not in review_types
            or not is_completed_review_evidence(item)
        ):
            continue
        parents = set(item.parent_ids)
        # A mixed-parent review could otherwise close a valid endpoint's
        # gap even when the same record also claims an unrelated asset,
        # endpoint, or finding. Require the *entire* lineage to be a
        # nonempty set of eligible surface observations.
        if parents and parents <= allowed_parent_ids:
            reviewed.update(parents)
    return reviewed


def _completed_scan_evidence(
    graph: ObservationGraph,
    *,
    evidence_filter: Callable[[Any], bool] | None = None,
) -> tuple[int, int, int, int, int]:
    """Count completed jobs without treating duplicate reporters as independent.

    A scanner job contributes an independent source only if *all* completed
    observations for that job name exactly one non-empty source.
    """
    sources_by_job: dict[str, set[str]] = {}
    invalid_jobs: set[str] = {
        f"job:{job_id}"
        for job_id in conflicting_scan_terminal_job_ids(graph)
    }
    rejected_cross_origin_jobs: set[str] = set()
    for item in graph.by_kind("evidence"):
        if (
            item.metadata.get("phase") != "scan"
            or item.metadata.get("status") != "completed"
        ):
            continue
        raw_job_id = item.metadata.get("job_id")
        job_id = raw_job_id.strip() if isinstance(raw_job_id, str) else ""
        if raw_job_id is not None and (
            not isinstance(raw_job_id, str)
            or len(job_id) > 128
        ):
            key = f"invalid:{item.id}"
            invalid_jobs.add(key)
        else:
            key = f"job:{job_id}" if job_id else f"observation:{item.id}"

        if evidence_filter is not None and not evidence_filter(item):
            # A job observed on another origin cannot be credited through
            # a second conveniently in-scope report with the same job ID.
            # Only explicit job IDs can establish cross-observation identity.
            if key.startswith("job:"):
                rejected_cross_origin_jobs.add(key)
            continue
        source = item.source.strip() if isinstance(item.source, str) else ""
        sources_by_job.setdefault(key, set()).add(source)

    # Fail closed on jobs with conflicting target ancestry even if scanner
    # names agree. Other-target-only jobs are not counted as ambiguous for
    # this target because they never entered the candidate set.
    cross_origin_count = sum(
        key in sources_by_job for key in rejected_cross_origin_jobs
    )
    for key in rejected_cross_origin_jobs:
        sources_by_job.pop(key, None)

    trusted_sources: set[str] = set()
    trusted_job_count = 0
    ambiguous = cross_origin_count
    contradictions = sum(job in invalid_jobs and job.startswith("job:")
                         for job in sources_by_job)
    for job, reporters in sources_by_job.items():
        if job in invalid_jobs or len(reporters) != 1 or "" in reporters:
            ambiguous += 1
        else:
            trusted_job_count += 1
            trusted_sources.update(reporters)
    return (len(sources_by_job), len(trusted_sources), ambiguous,
            trusted_job_count, contradictions)

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
    target_host: str | None = None,
    target_url: str | None = None,
) -> NoFindingRecovery:
    """Rank *existing* authorized recon task kinds after evidence-backed null scans.

    This is observation-only feedback, not a scanner/exploit dispatcher. Missing
    findings are not evidence that a target is safe. No new target, capability,
    permission, request or task kind can be minted by this function.
    """
    if campaign_finding_count < 0:
        raise ValueError("campaign_finding_count must not be negative")
    target_origin = _origin(target_url) if target_url is not None else None
    if target_url is not None and target_origin is None:
        raise ValueError("target_url must have a valid HTTP(S) origin")
    normalized_target_host = (
        str(target_host).strip().lower().rstrip(".")
        if target_host is not None
        else (target_origin[1] if target_origin is not None else None)
    )
    if target_host is not None and not normalized_target_host:
        raise ValueError("target_host must not be blank")
    if (
        target_origin is not None
        and normalized_target_host != target_origin[1]
    ):
        raise ValueError("target_host and target_url must refer to one host")
    allowed = {
        kind
        for kind in available_task_kinds
        if kind in _ALLOWED_RECON_KINDS
    }
    finding_count = max(campaign_finding_count, len(graph.by_kind("finding")))
    surface = build_attack_surface(graph, scope_checker=scope_checker)

    endpoints = [
        item for item in surface["endpoints"]
        if (
            item["valid"]
            and item["in_scope"] is True
            and (
                normalized_target_host is None
                or item["host"] == normalized_target_host
            )
            and (
                target_origin is None
                or _origin(item["url"]) == target_origin
            )
            and not item["host_asset_mismatch"]
            and item["asset_parent_ids"]
        )
    ]
    forms = [
        item for item in surface["forms"]
        if (
            item["valid"]
            and item["in_scope"] is True
            and (
                normalized_target_host is None
                or item["host"] == normalized_target_host
            )
            and (
                target_origin is None
                or _origin(item["action"]) == target_origin
            )
        )
    ]
    endpoint_reviewed = _reviewed_ids(
        graph,
        _ENDPOINT_REVIEW_TYPES,
        allowed_parent_ids={item["id"] for item in endpoints},
    )
    uncovered_endpoints = sum(
        item["id"] not in endpoint_reviewed for item in endpoints
    )
    scope_issues = sum(
        item["valid"] and item["in_scope"] is True
        and (
            normalized_target_host is None
            or item["host"] == normalized_target_host
        )
        and (
            target_origin is None
            or _origin(item["url"]) == target_origin
        )
        and (
            item["host_asset_mismatch"] or not item["asset_parent_ids"]
        )
        for item in surface["endpoints"]
    )
    # Technology observations without a trusted in-scope asset ancestor
    # must not count as technology coverage of the authorized target.
    asset_values_by_id = {
        observation.id: observation.value
        for observation in graph.by_kind("asset")
    }
    asset_host_by_id = {
        item["id"]: item["host"]
        for item in surface["assets"]
        if (
            item["in_scope"] is True
            and (
                normalized_target_host is None
                or item["host"] == normalized_target_host
            )
            and (
                target_origin is None
                or _asset_matches_origin(
                    asset_values_by_id[item["id"]],
                    target_origin,
                )
            )
        )
    }
    observations_by_id = {item.id: item for item in graph.values()}

    def has_in_scope_asset_ancestor(observation_id: str) -> bool:
        pending = list(observations_by_id[observation_id].parent_ids)
        seen: set[str] = set()
        ancestor_hosts: set[str] = set()
        while pending:
            parent_id = pending.pop()
            if parent_id in seen:
                continue
            seen.add(parent_id)
            parent = observations_by_id.get(parent_id)
            if parent is None:
                continue
            if parent.kind == "asset":
                host = asset_host_by_id.get(parent.id)
                if not host:
                    return False
                ancestor_hosts.add(host)
            else:
                pending.extend(parent.parent_ids)
        return len(ancestor_hosts) == 1 and (
            normalized_target_host is None
            or normalized_target_host in ancestor_hosts
        )

    if target_origin is not None:
        # Matching the endpoint URL is insufficient if its graph ancestor
        # identifies a different scheme or port on the same host.
        excluded_endpoints = [
            item
            for item in endpoints
            if not has_in_scope_asset_ancestor(item["id"])
        ]
        endpoints = [
            item
            for item in endpoints
            if has_in_scope_asset_ancestor(item["id"])
        ]
        scope_issues += len(excluded_endpoints)
        endpoint_reviewed = _reviewed_ids(
            graph,
            _ENDPOINT_REVIEW_TYPES,
            allowed_parent_ids={item["id"] for item in endpoints},
        )
        uncovered_endpoints = sum(
            item["id"] not in endpoint_reviewed for item in endpoints
        )

    legacy_single_host = False
    scan_filter: Callable[[Any], bool] | None = None
    if normalized_target_host is None:
        (
            completed_scans, scanner_sources, ambiguous_sources,
            trusted_completed_scans, contradictory_scan_jobs,
        ) = _completed_scan_evidence(graph)
    else:
        asset_records = surface["assets"]
        # Legacy scan observations sometimes omit ancestry. They can only
        # be attributed to the target if every observed asset has its host.
        legacy_single_host = bool(asset_records) and all(
            item["host"] == normalized_target_host
            and item["in_scope"] is True
            and (
                target_origin is None
                or _origin(asset_values_by_id[item["id"]]) == target_origin
            )
            for item in asset_records
        )

        def scan_matches_target(item: Any) -> bool:
            if item.parent_ids:
                return has_in_scope_asset_ancestor(item.id)
            return legacy_single_host

        scan_filter = scan_matches_target
        (
            completed_scans, scanner_sources, ambiguous_sources,
            trusted_completed_scans, contradictory_scan_jobs,
        ) = _completed_scan_evidence(
            graph,
            evidence_filter=scan_filter,
        )

    # A completed worker may report findings before their records reach the
    # campaign. Treat an explicitly positive or malformed finding count as
    # an ingestion/reconciliation issue, never as evidence of a null scan.
    # Older evidence without this field remains supported but is not upgraded
    # into proof of safety.
    unreconciled_scan_reports = 0
    if finding_count == 0:
        for item in graph.by_kind("evidence"):
            if (
                item.metadata.get("phase") != "scan"
                or item.metadata.get("status") != "completed"
                or "findings" not in item.metadata
                or (scan_filter is not None and not scan_filter(item))
            ):
                continue
            reported = item.metadata["findings"]
            if (
                isinstance(reported, bool)
                or not isinstance(reported, int)
                or reported < 0
                or reported > 0
            ):
                unreconciled_scan_reports += 1

    # Orphan forms or forms from a different asset do not close a gap.
    forms = [
        item for item in forms
        if has_in_scope_asset_ancestor(item["id"])
    ]
    form_reviewed = _reviewed_ids(
        graph,
        frozenset({"form_surface_review"}),
        allowed_parent_ids={item["id"] for item in forms},
    )
    uncovered_forms = sum(
        item["id"] not in form_reviewed for item in forms
    )
    missing_technology = not any(
        has_in_scope_asset_ancestor(item.id)
        for item in graph.by_kind("technology")
    )
    observed_browser_work = any(
        item.source in {"browser", "browser-agent", "recon:browser_observe"}
        and has_in_scope_asset_ancestor(item.id)
        for kind in ("endpoint", "form", "technology")
        for item in graph.by_kind(kind)
    ) or any(
        item.metadata.get("task_kind") == "browser_observe"
        and _is_completed_recon_step(item)
        and (
            normalized_target_host is None
            or has_in_scope_asset_ancestor(item.id)
            or (legacy_single_host and not item.parent_ids)
        )
        for item in graph.by_kind("evidence")
    )
    browser_job_outcomes = (worker_outcomes or {}).get("by_job_kind")
    if (
        (normalized_target_host is None or legacy_single_host)
        and isinstance(browser_job_outcomes, Mapping)
    ):
        # Worker outcomes have no target lineage. Trust legacy counts only
        # when one observed asset host can be associated with the campaign.
        browser_counts = browser_job_outcomes.get("browser_flow")
        if isinstance(browser_counts, Mapping):
            try:
                observed_browser_work = (
                    observed_browser_work
                    or int(browser_counts.get("completed") or 0) > 0
                )
            except (TypeError, ValueError):
                observed_browser_work = True  # fail closed on invalid worker data

    # A completed, asset-linked recovery step with no new findings should
    # not be repeatedly promoted merely because its coverage gap persists.
    # Evidence from another asset or with missing parent lineage does not
    # exhaust the authorized target's options.
    completed_recovery_evidence: dict[str, list[Any]] = {}
    for item in graph.by_kind("evidence"):
        kind = item.metadata.get("task_kind")
        if (
            kind in _ALLOWED_RECON_KINDS
            and _is_completed_recon_step(item)
            and has_in_scope_asset_ancestor(item.id)
        ):
            completed_recovery_evidence.setdefault(str(kind), []).append(item)
    completed_recovery_kinds = set(completed_recovery_evidence)


    worker_instability_observed = _unstable_scanner_outcomes(worker_outcomes)
    # Worker outcome summaries are campaign-wide and carry no asset identity.
    # Do not attribute a failure on host B to a completed scan of host A.
    worker_health_attributable = (
        normalized_target_host is None or legacy_single_host
    )
    worker_health_attribution = (
        "campaign_aggregate"
        if normalized_target_host is None
        else "single_observed_host"
        if legacy_single_host
        else "unattributed_multi_host"
    )
    worker_instability_applied = (
        worker_instability_observed and worker_health_attributable
    )

    reasons: list[str] = []
    candidates: list[tuple[int, str]] = []
    if ambiguous_sources:
        reasons.append(
            "completed scan jobs have missing or contradictory scanner "
            "source provenance; independent source count is conservative"
        )
    if worker_instability_observed and not worker_health_attributable:
        reasons.append(
            "campaign-wide scanner worker errors cannot be attributed "
            "to the selected target; target-specific health is unknown"
        )

    if finding_count:
        state = "findings_present"
        reasons.append("findings require the normal validation and review path")
    elif scope_checker is None:
        state = "scope_unverified"
        reasons.append("scope verification is required before suggesting recon")
    elif not asset_host_by_id:
        state = "scope_unverified"
        reasons.append("no observed asset matches the authorized target for recovery")
    elif worker_instability_applied:
        state = "execution_unstable"
        reasons.append("repeated scanner worker errors require operator review")
    elif contradictory_scan_jobs:
        state = "scan_status_unreconciled"
        reasons.append(
            "a scan job has contradictory terminal completion and failure "
            "records; reconcile execution state before negative-result learning"
        )
    elif unreconciled_scan_reports:
        state = "scan_findings_unreconciled"
        reasons.append(
            "completed scan reports include positive or invalid finding counts "
            "without matching recorded findings; reconcile ingestion before "
            "interpreting results as negative"
        )
    elif not completed_scans:
        state = "no_completed_scans"
        reasons.append("no successful scan evidence exists; no negative yield can be inferred")
    elif not trusted_completed_scans:
        state = "scan_source_unverified"
        reasons.append(
            "no completed scan has unambiguous source provenance; "
            "manual review is needed before treating scan results as negative"
        )
    else:
        state = "recovery_advisory"
        if scope_issues:
            reasons.append("observed endpoints lack reliable asset lineage")
            candidates.append((100, "map_endpoints"))
        if not endpoints:
            reasons.append("authorized endpoint inventory is missing or untrusted")
            # Existing untrusted endpoints make map_endpoints the available
            # reparative task; a truly empty inventory requires crawl.
            candidates.append((
                95,
                "map_endpoints"
                if (
                    graph.by_kind("endpoint")
                    if normalized_target_host is None
                    else any(
                        item["host"] == normalized_target_host
                        and (
                            target_origin is None
                            or _origin(item["url"]) == target_origin
                        )
                        for item in surface["endpoints"]
                    )
                )
                else "crawl",
            ))
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
            if trusted_completed_scans >= 3:
                reasons.append("repeated completed scans yielded no observed finding; rotate coverage rather than repeat identical tests")
                if not observed_browser_work:
                    candidates.append((55, "browser_observe"))
                else:
                    reasons.append("browser observation already attempted; no automatic repeat of exhausted recovery")
        if not candidates:
            state = "no_supported_recovery_task"
            reasons.append("no evidence-backed recon gap is available")
    candidate_kinds = {kind for _score, kind in candidates} & allowed
    reopened: set[str] = set()
    if state == "recovery_advisory" and completed_recovery_evidence:
        current_time = datetime.now(timezone.utc)
        valid_endpoint_ids = {item["id"] for item in endpoints}
        valid_form_ids = {item["id"] for item in forms}
        surface_times: dict[str, list[datetime]] = {}
        for kind in ("endpoint", "form", "technology", "waf"):
            for item in graph.by_kind(kind):
                if kind == "endpoint" and item.id not in valid_endpoint_ids:
                    continue
                if kind == "form" and item.id not in valid_form_ids:
                    continue
                if kind in {"technology", "waf"} and not (
                    has_in_scope_asset_ancestor(item.id)
                ):
                    continue
                # A fresh observation timestamp may merely be a refresh
                # of an old endpoint. Reconsider an exhausted task only when
                # a trusted first-discovery time proves genuinely new surface.
                first_seen = _trusted_utc_timestamp(
                    item.metadata.get("first_seen_at"),
                    now=current_time,
                )
                observed_at = _trusted_utc_timestamp(
                    item.metadata.get("observed_at"),
                    now=current_time,
                )
                if (
                    first_seen is not None
                    and observed_at is not None
                    and first_seen <= observed_at
                ):
                    surface_times.setdefault(kind, []).append(first_seen)

        for kind in candidate_kinds & completed_recovery_kinds:
            completed_times = [
                _trusted_utc_timestamp(
                    item.metadata.get("completed_at"), now=current_time
                )
                for item in completed_recovery_evidence[kind]
            ]
            # Missing or invalid completion timestamps cannot authorize a
            # retry recommendation based on assumed chronology.
            if not completed_times or any(
                timestamp is None for timestamp in completed_times
            ):
                continue
            latest_completion = max(completed_times)
            if any(
                observed_at > latest_completion
                for surface_kind in _REVISIT_SURFACE_KINDS[kind]
                for observed_at in surface_times.get(surface_kind, ())
            ):
                reopened.add(kind)

    exhausted = tuple(sorted(
        candidate_kinds & completed_recovery_kinds - reopened
    ))
    if reopened and state == "recovery_advisory":
        reasons.append(
            "confirmed first discovery of new in-scope surface after "
            "recorded completion warrants reconsidering read-only tasks"
        )
    if exhausted and state == "recovery_advisory":
        reasons.append(
            "completed in-scope recovery tasks produced no sufficient new evidence; "
            "do not repeat them automatically"
        )
    recommended = tuple(
        kind
        for _score, kind in sorted(set(candidates), key=lambda item: (-item[0], item[1]))
        if kind in allowed and kind not in exhausted
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
        exhausted_task_kinds=exhausted,
        reopened_task_kinds=tuple(sorted(reopened)),
        ambiguous_scan_source_jobs=ambiguous_sources,
        contradictory_scan_terminal_jobs=contradictory_scan_jobs,
        unreconciled_scan_reports=unreconciled_scan_reports,
        trusted_completed_scan_count=trusted_completed_scans,
        worker_health_attribution=worker_health_attribution,
        worker_instability_observed=worker_instability_observed,
        worker_instability_applied=worker_instability_applied,
    )
