from rehearsal_scenarios import (
    run_http_429_scenario,
    run_redirect_scope_scenario,
    run_subdomain_scope_scenario,
)


def test_redirect_scope_scenario(tmp_path, monkeypatch):
    result = run_redirect_scope_scenario(tmp_path, monkeypatch)
    assert result.status == "pass"
    assert result.reason == "redirects_observed_without_followup"
    assert result.external_network_used is False
    assert result.references.counters["requests_observed"] == 2


def test_subdomain_scope_scenario(tmp_path, monkeypatch):
    result = run_subdomain_scope_scenario(tmp_path, monkeypatch)
    assert result.status == "pass"
    assert result.reason == "denied_host_blocked_before_transport"
    assert result.references.counters["requests_observed"] == 1


def test_http_429_scenario(tmp_path, monkeypatch):
    result = run_http_429_scenario(tmp_path, monkeypatch)
    assert result.status == "pass"
    assert result.reason == "http_429_observed_once"
    assert result.references.counters["requests_observed"] == 1
