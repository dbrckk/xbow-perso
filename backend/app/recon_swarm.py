from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Callable, Literal
from urllib.parse import urlsplit, urlunsplit

from fastapi import APIRouter

from .adaptive_cycle import router as adaptive_cycle_router
from .autonomy_gate import router as autonomy_gate_router
from .observation_graph import ObservationGraph, load_observation_graph

ReconTaskKind = Literal[
    "crawl",
    "map_endpoints",
    "detect_technology",
    "map_forms",
    "browser_observe",
]

router = APIRouter()
router.routes.extend(autonomy_gate_router.routes)
router.routes.extend(adaptive_cycle_router.routes)


@dataclass(frozen=True)
class ReconCapability:
    agent: str
    task_kind: ReconTaskKind
    observation_kinds: tuple[str, ...]
    network_access: bool
    same_origin_only: bool
    read_only: bool
    allowed_methods: tuple[str, ...]
    max_targets_per_batch: int
    max_requests_per_target: int

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["observation_kinds"] = list(self.observation_kinds)
        payload["allowed_methods"] = list(self.allowed_methods)
        return payload


@dataclass(frozen=True)
class ReconTask:
    kind: ReconTaskKind
    agent: str
    target: str
    priority: int
    reason: str
    max_requests: int
    allowed_methods: tuple[str, ...] = ("GET", "HEAD")
    same_origin_only: bool = True
    read_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["allowed_methods"] = list(self.allowed_methods)
        return payload


_CAPABILITIES = (
    ReconCapability("crawler-agent", "crawl", ("endpoint", "form"), True, True, True, ("GET", "HEAD"), 5, 40),
    ReconCapability("endpoint-agent", "map_endpoints", ("endpoint",), True, True, True, ("GET", "HEAD"), 10, 20),
    ReconCapability("tech-agent", "detect_technology", ("technology", "waf"), True, True, True, ("GET", "HEAD"), 10, 8),
    ReconCapability("form-agent", "map_forms", ("form",), True, True, True, ("GET", "HEAD"), 10, 12),
    ReconCapability("browser-agent", "browser_observe", ("endpoint", "form", "technology"), True, True, True, ("GET", "HEAD"), 3, 25),
)


def recon_capabilities() -> tuple[ReconCapability, ...]:
    return _CAPABILITIES


def _origin_identity(
    value: str,
    *,
    allow_hostname: bool = False,
) -> tuple[str, str | None, int | None] | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = urlsplit(
            raw if "://" in raw or not allow_hostname else f"//{raw}"
        )
        scheme = parsed.scheme.lower() or None
        host = (parsed.hostname or "").lower().rstrip(".")
        port = parsed.port
        if (
            not host
            or scheme not in {None, "http", "https"}
            or (scheme is None and not allow_hostname)
            or parsed.username is not None
            or parsed.password is not None
        ):
            return None
    except ValueError:
        return None
    if port is None:
        if scheme == "https":
            port = 443
        elif scheme == "http":
            port = 80
    return host, scheme, port


def _safe_target(value: str) -> tuple[str, str]:
    identity = _origin_identity(value)
    if identity is None:
        return "", ""
    host, scheme, port = identity
    if scheme not in {"http", "https"}:
        return "", ""
    raw_host = f"[{host}]" if ":" in host else host
    default_port = 443 if scheme == "https" else 80
    netloc = (
        f"{raw_host}:{port}"
        if port is not None and port != default_port
        else raw_host
    )
    parsed = urlsplit(value)
    return urlunsplit((scheme, netloc, parsed.path or "/", "", "")), host


def _same_origin(value: str, target_origin: tuple[str, str | None, int | None]) -> bool:
    candidate = _origin_identity(value)
    return candidate is not None and candidate == target_origin


def _compatible_asset(
    value: str,
    target_origin: tuple[str, str | None, int | None],
) -> bool:
    identity = _origin_identity(value, allow_hostname=True)
    if identity is None:
        return False
    host, scheme, port = identity
    target_host, target_scheme, target_port = target_origin
    return (
        host == target_host
        and (scheme is None or scheme == target_scheme)
        and (port is None or port == target_port)
    )


def _recon_observation_is_for_target(
    item: Any,
    *,
    target_origin: tuple[str, str | None, int | None],
    observations: dict[str, Any],
    assets: list[Any],
) -> bool:
    if item.kind in {"endpoint", "form"} and not _same_origin(
        item.value, target_origin
    ):
        return False

    pending = list(item.parent_ids)
    seen: set[str] = set()
    linked_assets: list[Any] = []
    while pending:
        parent_id = pending.pop()
        if parent_id in seen:
            continue
        seen.add(parent_id)
        parent = observations.get(parent_id)
        if parent is None:
            return False
        if parent.kind == "asset":
            linked_assets.append(parent)
        else:
            # A compatible asset ancestor cannot legitimize a technology
            # or form discovered through an endpoint/form on another
            # scheme, hostname or port.
            if parent.kind in {"endpoint", "form"} and not _same_origin(
                parent.value, target_origin
            ):
                return False
            pending.extend(parent.parent_ids)
    if linked_assets:
        return all(
            _compatible_asset(asset.value, target_origin)
            for asset in linked_assets
        )
    # Legacy unlinked observations cannot be assigned to one of many assets.
    return len(assets) == 1 and _compatible_asset(
        assets[0].value, target_origin
    )


def build_recon_plan(
    target: str,
    graph: ObservationGraph,
    *,
    scope_checker: Callable[[str], bool],
    limit: int = 10,
) -> list[ReconTask]:
    """Build a bounded passive/low-impact recon plan without executing requests."""
    if not 1 <= limit <= 25:
        raise ValueError("recon plan limit must be between 1 and 25")

    safe_target, host = _safe_target(target)
    if not safe_target or not scope_checker(host):
        return []

    assets = graph.by_kind("asset")
    target_origin = _origin_identity(safe_target)
    if target_origin is None:
        return []
    if assets and not any(
        _compatible_asset(item.value, target_origin)
        for item in assets
    ):
        return []

    observations = {item.id: item for item in graph.values()}

    def matching(kind: str) -> list[Any]:
        return [
            item
            for item in graph.by_kind(kind)
            if _recon_observation_is_for_target(
                item,
                target_origin=target_origin,
                observations=observations,
                assets=assets,
            )
        ]

    endpoints = matching("endpoint")
    forms = matching("form")
    technologies = matching("technology")
    wafs = matching("waf")
    tasks: list[ReconTask] = []

    if not endpoints:
        tasks.append(ReconTask("crawl", "crawler-agent", safe_target, 100, "endpoint inventory is missing", 40))
    else:
        tasks.append(ReconTask("map_endpoints", "endpoint-agent", safe_target, 80, "refresh bounded endpoint inventory", 20))

    if not technologies or not wafs:
        tasks.append(
            ReconTask(
                "detect_technology",
                "tech-agent",
                safe_target,
                75,
                "technology or edge-protection context is incomplete",
                8,
            )
        )
    if endpoints and not forms:
        tasks.append(ReconTask("map_forms", "form-agent", safe_target, 70, "form surface is not yet mapped", 12))
    if endpoints:
        tasks.append(
            ReconTask(
                "browser_observe",
                "browser-agent",
                safe_target,
                60,
                "browser-rendered surface may add read-only observations",
                25,
            )
        )

    return sorted(tasks, key=lambda item: (-item.priority, item.kind))[:limit]


@router.get("/api/recon-swarm/capabilities")
def recon_swarm_capabilities():
    return {
        "capabilities": [item.to_dict() for item in recon_capabilities()],
        "read_only": True,
        "bounded": True,
    }


@router.get("/api/campaigns/{campaign_id}/recon-plan")
def campaign_recon_plan(campaign_id: str, limit: int = 10):
    from .main import assert_campaign_exists, is_host_allowed, storage

    campaign = assert_campaign_exists(campaign_id)
    graph = load_observation_graph(
        storage(), campaign.id, include_persisted_discovery_times=True
    )
    rules = campaign.target.rules

    def scope_checker(host: str) -> bool:
        return is_host_allowed(host, rules.allowed_targets, rules.denied_targets)

    tasks = build_recon_plan(
        str(campaign.target.primary_url),
        graph,
        scope_checker=scope_checker,
        limit=limit,
    )

    from .learning_memory import summarize_worker_outcomes
    from .no_finding_recovery import build_no_finding_recovery
    from .recon_priority import prioritize_recon_tasks
    from .surface_confidence import build_surface_confidence
    from .surface_diff import build_surface_diff_intelligence
    from .surface_temporal import build_temporal_surface_profile
    from .target_memory import build_target_memory

    store = storage()
    campaign_doc = campaign.model_dump(mode="json")
    memory = build_target_memory(store, campaign_doc)
    surface_diff = build_surface_diff_intelligence(memory)
    surface_temporal = build_temporal_surface_profile(store, campaign_doc)
    surface_confidence = build_surface_confidence(memory, surface_temporal)
    feedback = build_no_finding_recovery(
        graph,
        scope_checker=scope_checker,
        available_task_kinds=(
            (task.kind for task in tasks)
            if rules.automated_scanning
            else ()
        ),
        campaign_finding_count=len(campaign.findings),
        worker_outcomes=summarize_worker_outcomes(campaign.events),
        target_host=urlsplit(str(campaign.target.primary_url)).hostname,
        target_url=str(campaign.target.primary_url),
    )
    priority = prioritize_recon_tasks(
        tasks,
        surface_diff,
        memory,
        surface_temporal,
        surface_confidence,
        no_finding_feedback=feedback.to_dict(),
    )

    return {
        "campaign_id": campaign.id,
        "tasks": [item.to_dict() for item in priority.tasks],
        "summary": {"total": len(priority.tasks)},
        "diff_priority": priority.to_dict(),
        "no_finding_feedback": feedback.to_dict(),
        "surface_diff": surface_diff,
        "surface_temporal": surface_temporal,
        "surface_confidence": surface_confidence,
        "read_only": True,
        "bounded": True,
        "scope_aware": True,
        "execution": "advisory_only",
    }
