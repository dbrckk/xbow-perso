import json

import pytest

from app.main import Campaign, Finding, ProgramRules, TargetInput
from app.validator import ValidationPolicyError, build_probe_url, safe_http_probe


def campaign() -> Campaign:
    return Campaign(
        target=TargetInput(
            name="Local authorized target",
            primary_url="https://app.example.test/base",
            rules=ProgramRules(
                authorization_reference="test-program",
                allowed_targets=["app.example.test", "api.example.test"],
                denied_targets=["admin.example.test"],
            ),
        )
    )


def finding(**kwargs) -> Finding:
    data = {
        "title": "Candidate",
        "severity": "medium",
        "asset": "https://app.example.test",
        "endpoint": "/account",
        "summary": "Synthetic test finding",
        "discovered_by": "strix",
    }
    data.update(kwargs)
    return Finding(**data)


def test_probe_resolves_relative_endpoint_inside_scope():
    assert build_probe_url(campaign(), finding()) == "https://app.example.test/account"


def test_probe_rejects_out_of_scope_endpoint():
    with pytest.raises(ValidationPolicyError, match="outside declared scope"):
        build_probe_url(campaign(), finding(endpoint="https://evil.invalid/x"))


def test_probe_rejects_denied_host_even_if_related():
    with pytest.raises(ValidationPolicyError, match="outside declared scope"):
        build_probe_url(campaign(), finding(endpoint="https://admin.example.test/x"))


def test_http_validation_is_dry_run_by_default(monkeypatch):
    monkeypatch.delenv("XBOW_ENABLE_HTTP_VALIDATION", raising=False)
    result = safe_http_probe(campaign(), finding())
    assert result.status == "dry_run"
    payload = json.loads(result.json_bytes())
    assert payload["url"] == "https://app.example.test/account"
    assert payload["http_status"] is None
