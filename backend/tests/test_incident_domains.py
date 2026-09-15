from app.incident_domains import build_domain_incidents


def test_domains_are_independent():
    result = build_domain_incidents(
        {"status": "error"},
        {"state": "degraded"},
        {"state": "healthy"},
        {"state": "critical"},
    )
    assert result["incidents"]["workload"]["severity"] == "degraded"
    assert result["incidents"]["control_plane"]["severity"] == "critical"
    assert result["incidents"]["observability"]["severity"] == "critical"


def test_healthy_domain_has_no_incident():
    result = build_domain_incidents(
        {"status": "ok"},
        {"state": "healthy"},
        {"state": "healthy"},
        {"state": "degraded"},
    )
    assert result["incidents"]["workload"] is None
    assert result["incidents"]["control_plane"] is None
    assert result["incidents"]["observability"] is not None


def test_same_signals_in_different_domains_have_distinct_fingerprints():
    result = build_domain_incidents(
        {"status": "warning"},
        {"state": "healthy"},
        {"state": "healthy"},
        {"state": "degraded"},
    )
    assert (
        result["incidents"]["control_plane"]["fingerprint"]
        != result["incidents"]["observability"]["fingerprint"]
    )


def test_output_is_redacted():
    result = build_domain_incidents(
        {"status": "ok"},
        {"state": "healthy"},
        {"state": "healthy"},
        {"state": "healthy"},
    )
    assert result["contains_targets"] is False
    assert result["contains_payloads"] is False
    assert result["contains_secrets"] is False
