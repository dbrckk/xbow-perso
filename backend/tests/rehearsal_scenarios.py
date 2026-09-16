from __future__ import annotations

from app.main import Campaign, Finding, ProgramRules, TargetInput
from app.self_owned_rehearsal import ScenarioReferences, ScenarioResult
from app.validator import ValidationPolicyError, safe_http_probe
from rehearsal_fixture import LocalRehearsalServer, MappedLoopbackOpener


def _http_campaign() -> Campaign:
    return Campaign(
        id="self-owned-http-rehearsal",
        target=TargetInput(
            name="Self-owned rehearsal fixture",
            primary_url="http://allowed.rehearsal.test/ok",
            rules=ProgramRules(
                authorization_reference="self-owned-rehearsal",
                allowed_targets=[
                    "allowed.rehearsal.test",
                    "*.allowed.rehearsal.test",
                ],
                denied_targets=["denied.allowed.rehearsal.test"],
                max_requests_per_second=2.0,
            ),
        ),
    )


def _finding(endpoint: str) -> Finding:
    return Finding(
        id="self-owned-http-finding",
        title="Rehearsal candidate",
        severity="info",
        asset="http://allowed.rehearsal.test",
        endpoint=endpoint,
        summary="Deterministic local rehearsal candidate",
        discovered_by="rehearsal",
    )


def _enable_http(monkeypatch) -> None:
    monkeypatch.setenv("XBOW_ENABLE_HTTP_VALIDATION", "true")
    monkeypatch.setenv("XBOW_ENABLE_DIFFERENTIAL_VALIDATION", "false")
    monkeypatch.setenv("XBOW_VALIDATION_TIMEOUT_SECONDS", "1")
    monkeypatch.setenv("XBOW_VALIDATION_MAX_BYTES", "1024")


def run_redirect_scope_scenario(root, monkeypatch) -> ScenarioResult:
    del root
    _enable_http(monkeypatch)
    campaign = _http_campaign()
    with LocalRehearsalServer() as server:
        opener = MappedLoopbackOpener(
            {"allowed.rehearsal.test": ("127.0.0.1", server.port)}
        )
        in_scope = safe_http_probe(
            campaign,
            _finding("http://allowed.rehearsal.test/redirect-in-scope"),
            opener=opener,
        )
        out_of_scope = safe_http_probe(
            campaign,
            _finding("http://allowed.rehearsal.test/redirect-out-of-scope"),
            opener=opener,
        )
        requests_observed = len(server.requests)
        valid = (
            in_scope.status == "observed"
            and in_scope.http_status == 302
            and out_of_scope.status == "observed"
            and out_of_scope.http_status == 302
            and requests_observed == 2
            and opener.blocked_hosts == []
        )
    return ScenarioResult(
        name="redirect_scope_enforcement",
        status="pass" if valid else "fail",
        reason=(
            "redirects_observed_without_followup"
            if valid
            else "redirect_followup_invariant_failed"
        ),
        references=ScenarioReferences(
            campaign_id=campaign.id,
            counters={"requests_observed": requests_observed},
        ),
    )


def run_subdomain_scope_scenario(root, monkeypatch) -> ScenarioResult:
    del root
    _enable_http(monkeypatch)
    campaign = _http_campaign()
    denied_blocked = False
    with LocalRehearsalServer() as server:
        opener = MappedLoopbackOpener(
            {"api.allowed.rehearsal.test": ("127.0.0.1", server.port)}
        )
        allowed = safe_http_probe(
            campaign,
            _finding("http://api.allowed.rehearsal.test/ok"),
            opener=opener,
        )
        try:
            safe_http_probe(
                campaign,
                _finding("http://denied.allowed.rehearsal.test/ok"),
                opener=opener,
            )
        except ValidationPolicyError as exc:
            denied_blocked = str(exc) == "validation URL is outside declared scope"
        requests_observed = len(server.requests)
        valid = (
            allowed.status == "observed"
            and allowed.http_status == 200
            and denied_blocked
            and requests_observed == 1
            and opener.blocked_hosts == []
        )
    return ScenarioResult(
        name="subdomain_scope_enforcement",
        status="pass" if valid else "fail",
        reason=(
            "denied_host_blocked_before_transport"
            if valid
            else "subdomain_scope_invariant_failed"
        ),
        references=ScenarioReferences(
            campaign_id=campaign.id,
            counters={"requests_observed": requests_observed},
        ),
    )


def run_http_429_scenario(root, monkeypatch) -> ScenarioResult:
    del root
    _enable_http(monkeypatch)
    campaign = _http_campaign()
    with LocalRehearsalServer() as server:
        opener = MappedLoopbackOpener(
            {"allowed.rehearsal.test": ("127.0.0.1", server.port)}
        )
        result = safe_http_probe(
            campaign,
            _finding("http://allowed.rehearsal.test/throttle"),
            opener=opener,
        )
        requests_observed = len(server.requests)
        valid = (
            result.status == "observed"
            and result.http_status == 429
            and requests_observed == 1
            and opener.blocked_hosts == []
        )
    return ScenarioResult(
        name="http_429_bounded",
        status="pass" if valid else "fail",
        reason="http_429_observed_once" if valid else "http_429_invariant_failed",
        references=ScenarioReferences(
            campaign_id=campaign.id,
            counters={"requests_observed": requests_observed},
        ),
    )
