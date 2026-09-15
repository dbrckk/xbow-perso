from datetime import datetime, timedelta, timezone

from app.incident_lifecycle import (
    acknowledge_incident,
    apply_incident_snapshot,
    incident_reliability_stats,
)


T0 = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)


def snap(fingerprint="abc", severity="degraded"):
    return {
        "incident": {
            "fingerprint": fingerprint,
            "dedupe_key": "operational:" + fingerprint,
            "severity": severity,
        }
    }


def test_opens_and_deduplicates_same_incident():
    history = apply_incident_snapshot([], snap(), now=T0)
    history = apply_incident_snapshot(history, snap(), now=T0 + timedelta(minutes=1))
    assert len(history) == 1
    assert history[0]["status"] == "opened"
    assert history[0]["last_seen_at"] == (T0 + timedelta(minutes=1)).isoformat()


def test_acknowledges_open_incident():
    history = apply_incident_snapshot([], snap(), now=T0)
    history = acknowledge_incident(history, "abc", now=T0 + timedelta(minutes=2))
    assert history[0]["status"] == "acknowledged"
    assert history[0]["acknowledged_at"] is not None


def test_healthy_snapshot_resolves_active_incident():
    history = apply_incident_snapshot([], snap(), now=T0)
    history = apply_incident_snapshot(history, {"incident": None}, now=T0 + timedelta(minutes=3))
    assert history[0]["status"] == "resolved"
    assert history[0]["resolved_at"] is not None


def test_new_fingerprint_resolves_previous_and_opens_new():
    history = apply_incident_snapshot([], snap("one"), now=T0)
    history = apply_incident_snapshot(history, snap("two", "critical"), now=T0 + timedelta(minutes=1))
    assert history[0]["status"] == "resolved"
    assert history[1]["status"] == "opened"
    assert history[1]["severity"] == "critical"


def test_reliability_stats_compute_mttr_and_mtbf():
    history = apply_incident_snapshot([], snap("one"), now=T0)
    history = apply_incident_snapshot(history, {"incident": None}, now=T0 + timedelta(seconds=30))
    history = apply_incident_snapshot(history, snap("two"), now=T0 + timedelta(seconds=120))
    history = apply_incident_snapshot(history, {"incident": None}, now=T0 + timedelta(seconds=180))
    stats = incident_reliability_stats(history)
    assert stats["mttr_seconds"] == 45.0
    assert stats["mtbf_seconds"] == 120.0
