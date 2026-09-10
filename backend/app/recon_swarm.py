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


def _safe_target(value: str) -> tuple[str, str]:
    parsed = urlsplit(value)
    scheme = parsed.scheme.lower()
    host = (parsed.hostname or "").lower().rstrip(".")
    if not scheme or not host:
        return "", ""
    try:
        port = parsed.port
    except ValueError:
        return "", ""
    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        netloc = f"{host}:{port}"
    else:
        netloc = host
    return urlunsplit((scheme, netloc, parsed.path or "/", "", "")), host


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

    observed_assets = {
        _safe_target(item.value)[1]
        for item in graph.by_kind("asset")
        if _safe_target(item.value)[1]
    }
    if observed_assets and host not in observed_assets:
        return []

    endpoints = graph.by_kind("endpoint")
    forms = graph.by_kind("form")
    technologies = graph.by_kind("technology")
    wafs = graph.by_kind("waf")
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
    graph = load_observation_graph(storage(), campaign.id)
    rules = campaign.target.rules

    def scope_checker(host: str) -> bool:
        return is_host_allowed(host, rules.allowed_targets, rules.denied_targets)

    tasks = build_recon_plan(
        str(campaign.target.primary_url),
        graph,
        scope_checker=scope_checker,
        limit=limit,
    )
    return {
        "campaign_id": campaign.id,
        "tasks": [item.to_dict() for item in tasks],
        "summary": {"total": len(tasks)},
        "read_only": True,
        "bounded": True,
        "scope_aware": True,
        "execution": "advisory_only",
    }
