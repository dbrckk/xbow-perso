from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Callable, Literal
from urllib.parse import parse_qsl, urlsplit, urlunsplit

from fastapi import APIRouter

from .evidence_chain import router as evidence_chain_router
from .observation_graph import ObservationGraph, load_observation_graph
from .validation_state import analyze_validation_state

HypothesisKind = Literal[
    "input_surface_review",
    "authorization_surface_review",
    "form_surface_review",
    "technology_surface_review",
    "protection_surface_review",
    "validation_gap",
]
NextAction = Literal["scan", "validate", "stop"]

router = APIRouter()
router.routes.extend(evidence_chain_router.routes)


@dataclass(frozen=True)
class Hypothesis:
    kind: HypothesisKind
    target: str
    reason: str
    confidence: float
    evidence_ids: tuple[str, ...]
    next_action: NextAction
    parameter_names: tuple[str, ...] = ()
    dependency_depth: int = 0
    read_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["evidence_ids"] = list(self.evidence_ids)
        payload["parameter_names"] = list(self.parameter_names)
        return payload


def _safe_endpoint(value: str) -> tuple[str, tuple[str, ...]] | None:
    """Return a redacted, validated HTTP(S) endpoint or reject bad origins."""
    raw = str(value or "").strip()
    if not raw or any(ord(char) < 32 or ord(char) == 127 for char in raw):
        return None
    try:
        parsed = urlsplit(raw)
        scheme = parsed.scheme.lower()
        host = (parsed.hostname or "").lower().rstrip(".")
        port = parsed.port
    except ValueError:
        return None
    if (
        scheme not in {"http", "https"}
        or not host
        or parsed.username is not None
        or parsed.password is not None
        or port == 0
    ):
        return None
    netloc = f"[{host}]" if ":" in host else host
    if port is not None and not (
        (scheme == "http" and port == 80)
        or (scheme == "https" and port == 443)
    ):
        netloc += f":{port}"
    safe_url = urlunsplit((scheme, netloc, parsed.path or "/", "", ""))
    names = {
        key
        for key, _value in parse_qsl(parsed.query, keep_blank_values=True)
        if key and len(key) <= 80 and all(32 <= ord(char) < 127 for char in key)
    }
    return safe_url, tuple(sorted(names)[:64])


def _lineage_hosts(graph: ObservationGraph, observation_id: str) -> set[str]:
    by_id = {item.id: item for item in graph.values()}
    hosts: set[str] = set()
    seen: set[str] = set()
    stack = [observation_id]
    while stack:
        current_id = stack.pop()
        if current_id in seen:
            continue
        seen.add(current_id)
        current = by_id.get(current_id)
        if current is None:
            continue
        if current.kind == "asset":
            host = current.value.strip().lower().rstrip(".")
            if "://" in host:
                host = (urlsplit(host).hostname or "").lower().rstrip(".")
            if host:
                hosts.add(host)
        elif current.kind in {"endpoint", "form"}:
            host = (urlsplit(current.value).hostname or "").lower().rstrip(".")
            if host:
                hosts.add(host)
        stack.extend(current.parent_ids)
    return hosts


def _scope_allows(
    graph: ObservationGraph,
    observation_id: str,
    scope_checker: Callable[[str], bool] | None,
) -> bool:
    if scope_checker is None:
        return True
    hosts = _lineage_hosts(graph, observation_id)
    # A single permitted ancestor must never launder an out-of-scope
    # parent. Missing origin evidence is not permission to recommend work.
    return bool(hosts) and all(scope_checker(host) for host in hosts)


_REVIEW_PARENT_KINDS = {
    "input_surface_review": "endpoint",
    "authorization_surface_review": "endpoint",
    "form_surface_review": "form",
    "technology_surface_review": "technology",
    "protection_surface_review": "waf",
}


def _completed_reviews(
    graph: ObservationGraph,
    scope_checker: Callable[[str], bool] | None,
) -> dict[str, set[str]]:
    """Credit only completed reviews with unambiguous same-kind parents."""
    indexed = {item.id: item for item in graph.values()}
    reviewed: dict[str, set[str]] = {
        kind: set() for kind in _REVIEW_PARENT_KINDS
    }
    for evidence in graph.by_kind("evidence"):
        kind = evidence.metadata.get("review_type")
        status = evidence.metadata.get("status")
        if (
            not isinstance(kind, str)
            or kind not in _REVIEW_PARENT_KINDS
            or not isinstance(status, str)
            or status not in {"completed", "reviewed"}
            or not evidence.parent_ids
            or not _scope_allows(graph, evidence.id, scope_checker)
        ):
            continue
        parent_kind = _REVIEW_PARENT_KINDS[kind]
        if any(
            parent_id not in indexed or indexed[parent_id].kind != parent_kind
            for parent_id in evidence.parent_ids
        ):
            # A mixed-type or inconsistent review cannot close a gap by
            # borrowing the convenient subset of linked observations.
            continue
        reviewed[kind].update(evidence.parent_ids)
    return reviewed


def build_hypotheses(
    graph: ObservationGraph,
    *,
    limit: int = 20,
    scope_checker: Callable[[str], bool] | None = None,
) -> list[Hypothesis]:
    """Derive bounded, scope-aware review hypotheses from existing observations.

    This layer never emits payloads, exploit instructions, shell commands, or new
    network capabilities. When a scope checker is supplied, observations whose
    known lineage is entirely outside scope are excluded from review suggestions.
    """
    if not 1 <= limit <= 100:
        raise ValueError("hypothesis limit must be between 1 and 100")

    hypotheses: list[Hypothesis] = []
    validation_state = analyze_validation_state(graph)
    reviewed = _completed_reviews(graph, scope_checker)

    for endpoint in graph.by_kind("endpoint"):
        if not _scope_allows(graph, endpoint.id, scope_checker):
            continue
        safe = _safe_endpoint(endpoint.value)
        if safe is None:
            continue
        safe_target, parameter_names = safe
        path = urlsplit(safe_target).path.lower()
        if parameter_names and endpoint.id not in reviewed["input_surface_review"]:
            hypotheses.append(
                Hypothesis(
                    kind="input_surface_review",
                    target=safe_target,
                    reason="endpoint exposes named query inputs that merit bounded review",
                    confidence=0.55,
                    evidence_ids=(endpoint.id,),
                    next_action="scan",
                    parameter_names=parameter_names,
                    dependency_depth=len(endpoint.parent_ids),
                )
            )
        if (
            endpoint.id not in reviewed["authorization_surface_review"]
            and any(token in path for token in ("/account", "/profile", "/user", "/admin"))
        ):
            hypotheses.append(
                Hypothesis(
                    kind="authorization_surface_review",
                    target=safe_target,
                    reason="endpoint path suggests an authorization-sensitive surface",
                    confidence=0.60,
                    evidence_ids=(endpoint.id,),
                    next_action="scan",
                    parameter_names=parameter_names,
                    dependency_depth=len(endpoint.parent_ids),
                )
            )

    for form in graph.by_kind("form"):
        if not _scope_allows(graph, form.id, scope_checker):
            continue
        safe = _safe_endpoint(form.value)
        if safe is None:
            continue
        safe_target, _query_names = safe
        if form.id in reviewed["form_surface_review"]:
            continue
        input_names = tuple(
            sorted({str(name).strip() for name in form.metadata.get("input_names", ()) if str(name).strip()})
        )
        hypotheses.append(
            Hypothesis(
                kind="form_surface_review",
                target=safe_target,
                reason="observed form surface merits bounded, non-destructive review",
                confidence=0.58 if input_names else 0.50,
                evidence_ids=(form.id,),
                next_action="scan",
                parameter_names=input_names,
                dependency_depth=len(form.parent_ids),
            )
        )

    for technology in graph.by_kind("technology"):
        if (
            not _scope_allows(graph, technology.id, scope_checker)
            or technology.id in reviewed["technology_surface_review"]
        ):
            continue
        hypotheses.append(
            Hypothesis(
                kind="technology_surface_review",
                target=technology.value,
                reason="observed technology can guide bounded, version-aware review",
                confidence=0.45,
                evidence_ids=(technology.id,),
                next_action="scan",
                dependency_depth=len(technology.parent_ids),
            )
        )

    for waf in graph.by_kind("waf"):
        if (
            not _scope_allows(graph, waf.id, scope_checker)
            or waf.id in reviewed["protection_surface_review"]
        ):
            continue
        confidence = float(waf.metadata.get("confidence", 0.5))
        confidence = max(0.0, min(1.0, confidence))
        hypotheses.append(
            Hypothesis(
                kind="protection_surface_review",
                target=waf.value,
                reason="observed protection layer should inform conservative review planning",
                confidence=round(0.35 + confidence * 0.20, 4),
                evidence_ids=(waf.id,),
                next_action="scan",
                dependency_depth=len(waf.parent_ids),
            )
        )

    for finding in graph.by_kind("finding"):
        if not _scope_allows(graph, finding.id, scope_checker):
            continue
        if finding.id not in validation_state.observed_independent_finding_ids:
            hypotheses.append(
                Hypothesis(
                    kind="validation_gap",
                    target=finding.value,
                    reason="finding lacks observed independent validation evidence",
                    confidence=0.90,
                    evidence_ids=(finding.id,),
                    next_action="validate",
                    dependency_depth=len(finding.parent_ids),
                )
            )

    deduped: dict[tuple[str, str], Hypothesis] = {}
    for item in hypotheses:
        key = (item.kind, item.target)
        previous = deduped.get(key)
        if previous is None:
            deduped[key] = item
            continue
        # Multiple observations of the same safe URL can expose different
        # input names. Keep their union and provenance instead of silently
        # discarding all but one while redacting their query values.
        preferred = (
            item if item.confidence > previous.confidence else previous
        )
        deduped[key] = Hypothesis(
            kind=preferred.kind,
            target=preferred.target,
            reason=preferred.reason,
            confidence=max(previous.confidence, item.confidence),
            evidence_ids=tuple(sorted(
                set(previous.evidence_ids) | set(item.evidence_ids)
            )[:32]),
            next_action=preferred.next_action,
            parameter_names=tuple(sorted(
                set(previous.parameter_names) | set(item.parameter_names)
            )[:64]),
            dependency_depth=max(
                previous.dependency_depth, item.dependency_depth
            ),
        )

    return sorted(
        deduped.values(),
        key=lambda item: (-item.confidence, item.kind, item.target),
    )[:limit]


@router.get("/api/campaigns/{campaign_id}/hypotheses")
def campaign_hypotheses(campaign_id: str, limit: int = 20):
    from .main import assert_campaign_exists, is_host_allowed, storage

    campaign = assert_campaign_exists(campaign_id)
    graph = load_observation_graph(storage(), campaign.id)
    rules = campaign.target.rules
    hypotheses = build_hypotheses(
        graph,
        limit=limit,
        scope_checker=lambda host: is_host_allowed(host, rules.allowed_targets, rules.denied_targets),
    )
    counts: dict[str, int] = {}
    for item in hypotheses:
        counts[item.kind] = counts.get(item.kind, 0) + 1
    return {
        "campaign_id": campaign.id,
        "hypotheses": [item.to_dict() for item in hypotheses],
        "summary": {
            "total": len(hypotheses),
            "by_kind": dict(sorted(counts.items())),
        },
        "read_only": True,
        "safe_validation_only": True,
        "scope_aware": True,
    }
