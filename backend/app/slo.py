from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter

from .metrics import build_operational_metrics

router = APIRouter()


@dataclass(frozen=True)
class SLOResult:
    name: str
    target: float
    observed: float
    error_budget: float
    budget_consumed: float
    budget_remaining: float
    burn_rate: float
    state: str
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _bounded_ratio(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _state(burn_rate: float, budget_remaining: float) -> str:
    if burn_rate > 1.0:
        return "EXHAUSTED"
    if burn_rate >= 1.0 or budget_remaining <= 0.25:
        return "AT_RISK"
    return "HEALTHY"


def _evaluate_slo(
    name: str,
    *,
    target: float,
    observed: float,
    reason: str | None = None,
) -> SLOResult:
    target = _bounded_ratio(target)
    observed = _bounded_ratio(observed)
    error_budget = max(0.0, 1.0 - target)
    observed_error = max(0.0, 1.0 - observed)
    if error_budget <= 0:
        budget_consumed = 1.0 if observed_error > 0 else 0.0
        burn_rate = float("inf") if observed_error > 0 else 0.0
    else:
        budget_consumed = observed_error / error_budget
        burn_rate = budget_consumed
    budget_remaining = max(0.0, 1.0 - budget_consumed)
    return SLOResult(
        name=name,
        target=round(target, 6),
        observed=round(observed, 6),
        error_budget=round(error_budget, 6),
        budget_consumed=round(budget_consumed, 6),
        budget_remaining=round(budget_remaining, 6),
        burn_rate=round(burn_rate, 6) if burn_rate != float("inf") else burn_rate,
        state=_state(burn_rate, budget_remaining),
        reason=reason,
    )


def build_platform_slos(metrics: dict[str, Any]) -> dict[str, Any]:
    jobs = metrics.get("jobs_by_status") or {}
    total_jobs = max(1, int(metrics.get("jobs_total") or 0))
    completed = int(jobs.get("completed") or 0)
    failed = int(jobs.get("failed") or 0)
    cancelled = int(jobs.get("cancelled") or 0)
    terminal = completed + failed + cancelled
    success_rate = (
        completed / terminal
        if terminal > 0
        else 1.0
    )

    queue_audit = metrics.get("queue_transition_audit") or {}
    audit_valid = queue_audit.get("valid")
    queue_integrity = 1.0 if audit_valid is not False else 0.0

    recovery = metrics.get("recovery_readiness") or {}
    readiness = recovery.get("latest_decision")
    recovery_observed = {
        "READY": 1.0,
        "REVIEW": 0.995,
        "BLOCK": 0.0,
    }.get(readiness, 0.99)

    health = metrics.get("control_plane_health") or {}
    health_score = health.get("latest_score")
    availability_observed = (
        _bounded_ratio(float(health_score) / 100.0)
        if health_score is not None
        else 1.0
    )

    outbox_pending = int(metrics.get("pending_outbox_total") or 0)
    reporting_observed = 1.0 if outbox_pending == 0 else max(
        0.0,
        1.0 - min(1.0, outbox_pending / max(1, total_jobs)),
    )

    slos = [
        _evaluate_slo(
            "availability",
            target=0.99,
            observed=availability_observed,
            reason="derived_from_control_plane_health",
        ),
        _evaluate_slo(
            "queue_integrity",
            target=0.999,
            observed=queue_integrity,
            reason="derived_from_transition_audit",
        ),
        _evaluate_slo(
            "job_reliability",
            target=0.98,
            observed=success_rate,
            reason="derived_from_terminal_job_outcomes",
        ),
        _evaluate_slo(
            "recovery_readiness",
            target=0.999,
            observed=recovery_observed,
            reason="derived_from_recovery_gate",
        ),
        _evaluate_slo(
            "reporting_pipeline",
            target=0.99,
            observed=reporting_observed,
            reason="derived_from_pending_outbox",
        ),
    ]

    exhausted = [item.name for item in slos if item.state == "EXHAUSTED"]
    at_risk = [item.name for item in slos if item.state == "AT_RISK"]
    if exhausted:
        overall = "EXHAUSTED"
    elif at_risk:
        overall = "AT_RISK"
    else:
        overall = "HEALTHY"

    return {
        "state": overall,
        "slos": [item.to_dict() for item in slos],
        "summary": {
            "healthy": sum(item.state == "HEALTHY" for item in slos),
            "at_risk": len(at_risk),
            "exhausted": len(exhausted),
            "at_risk_slos": at_risk,
            "exhausted_slos": exhausted,
        },
        "windows": {
            "current": "latest aggregate snapshot",
            "historical_windows": ["1h", "24h", "7d"],
            "historical_burn_rate_supported": False,
        },
        "read_only": True,
        "aggregate_only": True,
        "automatic_mutation": False,
        "automatic_worker_control": False,
        "contains_targets": False,
        "contains_payloads": False,
        "contains_secrets": False,
    }


@router.get("/api/slo")
def platform_slos():
    from .main import queue, storage

    store = storage()
    metrics = build_operational_metrics(queue(), store)
    return attach_historical_slo_windows(
        build_platform_slos(metrics),
        store,
    )



def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _window_health_observed(
    snapshots: list[dict[str, Any]],
    *,
    since: datetime,
    until: datetime,
) -> dict[str, Any]:
    points: list[tuple[datetime, int]] = []
    for item in snapshots:
        created_at = _parse_time(item.get("created_at"))
        if created_at is None or created_at > until:
            continue
        try:
            score = int(item.get("score"))
        except (TypeError, ValueError):
            continue
        points.append((created_at, max(0, min(100, score))))

    points.sort(key=lambda item: item[0])
    if not points:
        return {
            "observed": None,
            "samples": 0,
            "covered_seconds": 0,
            "window_seconds": max(0, int((until - since).total_seconds())),
            "coverage_ratio": 0.0,
            "boundary_state_known": False,
        }

    boundary_point = None
    in_window: list[tuple[datetime, int]] = []
    for point in points:
        if point[0] <= since:
            boundary_point = point
        elif point[0] <= until:
            in_window.append(point)

    segments: list[tuple[datetime, int]] = []
    boundary_state_known = boundary_point is not None
    if boundary_point is not None:
        segments.append((since, boundary_point[1]))
    elif in_window:
        segments.append(in_window[0])

    for point in in_window:
        if not segments or point[0] > segments[-1][0]:
            segments.append(point)

    if not segments:
        return {
            "observed": None,
            "samples": 0,
            "covered_seconds": 0,
            "window_seconds": max(0, int((until - since).total_seconds())),
            "coverage_ratio": 0.0,
            "boundary_state_known": boundary_state_known,
        }

    weighted_score_seconds = 0.0
    covered_seconds = 0.0
    for index, (start, score) in enumerate(segments):
        end = (
            segments[index + 1][0]
            if index + 1 < len(segments)
            else until
        )
        duration = max(0.0, (end - start).total_seconds())
        weighted_score_seconds += float(score) * duration
        covered_seconds += duration

    window_seconds = max(0.0, (until - since).total_seconds())
    observed = (
        weighted_score_seconds / (100.0 * covered_seconds)
        if covered_seconds > 0
        else None
    )
    return {
        "observed": observed,
        "samples": len(in_window) + (1 if boundary_point is not None else 0),
        "covered_seconds": int(covered_seconds),
        "window_seconds": int(window_seconds),
        "coverage_ratio": round(
            covered_seconds / window_seconds,
            6,
        )
        if window_seconds > 0
        else 0.0,
        "boundary_state_known": boundary_state_known,
    }


def build_historical_slo_windows(
    storage_backend,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    history_fn = getattr(storage_backend, "list_control_plane_health_snapshots", None)
    if not callable(history_fn):
        return {
            "supported": False,
            "windows": {},
            "reason": "control_plane_health_history_unavailable",
        }

    snapshots = history_fn(limit=500)
    current = now or datetime.now(timezone.utc)
    specs = {
        "1h": timedelta(hours=1),
        "24h": timedelta(hours=24),
        "7d": timedelta(days=7),
    }
    windows: dict[str, Any] = {}
    for name, duration in specs.items():
        window = _window_health_observed(
            snapshots,
            since=current - duration,
            until=current,
        )
        observed = window["observed"]
        if observed is None:
            windows[name] = {
                "available": False,
                "samples": 0,
                "target": 0.99,
                "observed": None,
                "burn_rate": None,
                "budget_remaining": None,
                "state": "UNKNOWN",
                "covered_seconds": window["covered_seconds"],
                "window_seconds": window["window_seconds"],
                "coverage_ratio": window["coverage_ratio"],
                "boundary_state_known": window["boundary_state_known"],
                "data_quality": "insufficient",
            }
            continue
        slo = _evaluate_slo(
            f"availability_{name}",
            target=0.99,
            observed=observed,
            reason="time_weighted_control_plane_health_history",
        )
        coverage_ratio = float(window["coverage_ratio"])
        data_quality = (
            "complete"
            if coverage_ratio >= 0.999 and window["boundary_state_known"]
            else "partial"
        )
        windows[name] = {
            "available": True,
            "samples": window["samples"],
            "target": slo.target,
            "observed": slo.observed,
            "burn_rate": slo.burn_rate,
            "budget_remaining": slo.budget_remaining,
            "state": slo.state,
            "covered_seconds": window["covered_seconds"],
            "window_seconds": window["window_seconds"],
            "coverage_ratio": coverage_ratio,
            "boundary_state_known": window["boundary_state_known"],
            "data_quality": data_quality,
        }

    return {
        "supported": True,
        "windows": windows,
        "read_only": True,
        "aggregate_only": True,
    }


def attach_historical_slo_windows(
    result: dict[str, Any],
    storage_backend,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    historical = build_historical_slo_windows(storage_backend, now=now)
    return {
        **result,
        "historical": historical,
        "windows": {
            "current": "latest aggregate snapshot",
            "historical_windows": ["1h", "24h", "7d"],
            "historical_burn_rate_supported": bool(historical["supported"]),
        },
    }
