from app.main import app
from datetime import datetime, timezone

from app.slo import (
    build_historical_slo_windows,
    build_multiwindow_slo_policy,
    build_platform_slos,
)


def _metrics():
    return {
        "jobs_total": 10,
        "jobs_by_status": {
            "completed": 10,
            "failed": 0,
            "cancelled": 0,
        },
        "queue_transition_audit": {"valid": True},
        "recovery_readiness": {"latest_decision": "READY"},
        "control_plane_health": {"latest_score": 100},
        "pending_outbox_total": 0,
    }


def test_platform_slos_are_healthy_when_signals_are_clean():
    result = build_platform_slos(_metrics())

    assert result["state"] == "HEALTHY"
    assert result["summary"]["healthy"] == 5
    assert result["summary"]["at_risk"] == 0
    assert result["summary"]["exhausted"] == 0
    assert result["read_only"] is True
    assert result["automatic_mutation"] is False
    assert result["automatic_worker_control"] is False


def test_platform_slos_exhaust_queue_integrity_on_invalid_audit():
    metrics = _metrics()
    metrics["queue_transition_audit"]["valid"] = False

    result = build_platform_slos(metrics)
    queue = next(item for item in result["slos"] if item["name"] == "queue_integrity")

    assert queue["state"] == "EXHAUSTED"
    assert queue["observed"] == 0.0
    assert "queue_integrity" in result["summary"]["exhausted_slos"]
    assert result["state"] == "EXHAUSTED"


def test_platform_slos_mark_job_reliability_at_risk():
    metrics = _metrics()
    metrics["jobs_by_status"] = {
        "completed": 98,
        "failed": 1,
        "cancelled": 1,
    }
    metrics["jobs_total"] = 100

    result = build_platform_slos(metrics)
    reliability = next(item for item in result["slos"] if item["name"] == "job_reliability")

    assert reliability["observed"] == 0.98
    assert reliability["budget_consumed"] == 1.0
    assert reliability["state"] == "AT_RISK"


def test_platform_slos_block_recovery_budget_when_gate_blocks():
    metrics = _metrics()
    metrics["recovery_readiness"]["latest_decision"] = "BLOCK"

    result = build_platform_slos(metrics)
    recovery = next(item for item in result["slos"] if item["name"] == "recovery_readiness")

    assert recovery["state"] == "EXHAUSTED"
    assert recovery["observed"] == 0.0


def test_platform_slos_route_is_exposed():
    assert "/api/slo" in app.openapi()["paths"]



def test_historical_slo_windows_use_retained_health_snapshots():
    class Storage:
        def list_control_plane_health_snapshots(self, limit=500):
            return [
                {
                    "score": 80,
                    "state": "DEGRADED",
                    "created_at": "2026-09-14T15:30:00+00:00",
                },
                {
                    "score": 90,
                    "state": "HEALTHY",
                    "created_at": "2026-09-14T14:30:00+00:00",
                },
                {
                    "score": 100,
                    "state": "HEALTHY",
                    "created_at": "2026-09-13T12:00:00+00:00",
                },
            ][:limit]

    result = build_historical_slo_windows(
        Storage(),
        now=datetime(2026, 9, 14, 16, 0, tzinfo=timezone.utc),
    )

    one_hour = result["windows"]["1h"]
    day = result["windows"]["24h"]
    week = result["windows"]["7d"]

    assert result["supported"] is True
    assert one_hour["samples"] == 2
    assert one_hour["observed"] == 0.85
    assert one_hour["state"] == "EXHAUSTED"
    assert one_hour["coverage_ratio"] == 1.0
    assert one_hour["boundary_state_known"] is True
    assert one_hour["data_quality"] == "complete"

    assert day["samples"] == 3
    assert round(day["observed"], 6) == 0.991667
    assert day["coverage_ratio"] == 1.0
    assert day["data_quality"] == "complete"

    assert week["samples"] == 3
    assert round(week["observed"], 6) == 0.992857
    assert round(week["coverage_ratio"], 6) == 0.166667
    assert week["data_quality"] == "partial"


def test_historical_slo_windows_report_unknown_when_no_samples():
    class Storage:
        def list_control_plane_health_snapshots(self, limit=500):
            return []

    result = build_historical_slo_windows(
        Storage(),
        now=datetime(2026, 9, 14, 16, 0, tzinfo=timezone.utc),
    )

    assert result["supported"] is True
    assert result["windows"]["1h"]["available"] is False
    assert result["windows"]["1h"]["state"] == "UNKNOWN"
    assert result["windows"]["24h"]["samples"] == 0
    assert result["windows"]["7d"]["burn_rate"] is None


def test_historical_slo_windows_degrade_gracefully_without_history_backend():
    result = build_historical_slo_windows(
        object(),
        now=datetime(2026, 9, 14, 16, 0, tzinfo=timezone.utc),
    )

    assert result["supported"] is False
    assert result["windows"] == {}
    assert result["reason"] == "control_plane_health_history_unavailable"



def test_historical_slo_windows_mark_partial_coverage():
    class Storage:
        def list_control_plane_health_snapshots(self, limit=500):
            return [
                {
                    "score": 80,
                    "state": "DEGRADED",
                    "created_at": "2026-09-14T15:30:00+00:00",
                }
            ]

    result = build_historical_slo_windows(
        Storage(),
        now=datetime(2026, 9, 14, 16, 0, tzinfo=timezone.utc),
    )

    one_hour = result["windows"]["1h"]

    assert one_hour["available"] is True
    assert one_hour["samples"] == 1
    assert one_hour["observed"] == 0.8
    assert one_hour["covered_seconds"] == 1800
    assert one_hour["window_seconds"] == 3600
    assert one_hour["coverage_ratio"] == 0.5
    assert one_hour["boundary_state_known"] is False
    assert one_hour["data_quality"] == "partial"



def test_multiwindow_slo_policy_requires_complete_windows():
    policy = build_multiwindow_slo_policy(
        {
            "windows": {
                "1h": {
                    "available": True,
                    "burn_rate": 3.0,
                    "data_quality": "partial",
                },
                "24h": {
                    "available": True,
                    "burn_rate": 1.5,
                    "data_quality": "complete",
                },
                "7d": {
                    "available": True,
                    "burn_rate": 1.2,
                    "data_quality": "partial",
                },
            }
        }
    )

    assert policy["state"] == "UNKNOWN"
    assert policy["fast_burn"]["evaluable"] is False
    assert policy["fast_burn"]["triggered"] is False
    assert policy["slow_burn"]["evaluable"] is False
    assert policy["slow_burn"]["triggered"] is False


def test_multiwindow_slo_policy_detects_fast_burn():
    policy = build_multiwindow_slo_policy(
        {
            "windows": {
                "1h": {
                    "available": True,
                    "burn_rate": 2.5,
                    "data_quality": "complete",
                },
                "24h": {
                    "available": True,
                    "burn_rate": 1.2,
                    "data_quality": "complete",
                },
                "7d": {
                    "available": True,
                    "burn_rate": 0.5,
                    "data_quality": "complete",
                },
            }
        }
    )

    assert policy["state"] == "FAST_BURN"
    assert policy["fast_burn"]["evaluable"] is True
    assert policy["fast_burn"]["triggered"] is True
    assert policy["slow_burn"]["triggered"] is False
    assert policy["automatic_worker_control"] is False
