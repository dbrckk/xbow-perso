from app.incident_engine import build_incident_snapshot


def test_healthy_sources_produce_no_incident():
    result = build_incident_snapshot(
        {"status": "ok"}, {"state": "healthy"}, {"state": "healthy"}
    )
    assert result["state"] == "healthy"
    assert result["incident"] is None


def test_degraded_source_produces_degraded_incident():
    result = build_incident_snapshot(
        {"status": "warning"}, {"state": "healthy"}, {"state": "healthy"}
    )
    assert result["state"] == "degraded"
    assert result["incident"]["severity"] == "degraded"


def test_critical_source_dominates():
    result = build_incident_snapshot(
        {"status": "warning"}, {"state": "critical"}, {"state": "degraded"}
    )
    assert result["state"] == "critical"
    assert result["incident"]["severity"] == "critical"


def test_fingerprint_is_deterministic_and_redacted():
    a = build_incident_snapshot(
        {"status": "error"}, {"state": "degraded"}, {"state": "healthy"}
    )
    b = build_incident_snapshot(
        {"status": "error"}, {"state": "degraded"}, {"state": "healthy"}
    )
    assert a["incident"]["fingerprint"] == b["incident"]["fingerprint"]
    assert len(a["incident"]["fingerprint"]) == 24
    assert a["contains_targets"] is False
    assert a["contains_payloads"] is False
    assert a["contains_secrets"] is False


def test_incident_engine_never_enables_recovery_or_retry():
    result = build_incident_snapshot(
        {"status": "error"}, {"state": "critical"}, {"state": "critical"}
    )
    assert result["automatic_recovery"] is False
    assert result["automatic_retry"] is False
