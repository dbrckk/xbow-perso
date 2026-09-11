import json

import pytest

from app.main import Campaign, Finding, ProgramRules, TargetInput
from app.validator import ValidationPolicyError, _preview_body, build_probe_url, safe_http_probe


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


def test_invalid_http_validation_flag_fails_closed(monkeypatch):
    monkeypatch.setenv("XBOW_ENABLE_HTTP_VALIDATION", "sometimes")

    with pytest.raises(ValidationPolicyError, match="must be a boolean"):
        safe_http_probe(campaign(), finding())


@pytest.mark.parametrize(
    ("name", "value", "message"),
    (
        ("XBOW_VALIDATION_TIMEOUT_SECONDS", "NaN", "must be a number"),
        ("XBOW_VALIDATION_TIMEOUT_SECONDS", "0.5", "between 1 and 30"),
        ("XBOW_VALIDATION_MAX_BYTES", "NaN", "must be an integer"),
        ("XBOW_VALIDATION_MAX_BYTES", "512", "between 1 KiB and 1 MiB"),
    ),
)
def test_invalid_http_validator_limits_fail_closed(monkeypatch, name, value, message):
    monkeypatch.setenv("XBOW_ENABLE_HTTP_VALIDATION", "true")
    monkeypatch.setenv(name, value)

    with pytest.raises(ValidationPolicyError, match=message):
        safe_http_probe(campaign(), finding())


def test_explicit_false_http_validation_flag_remains_dry_run(monkeypatch):
    monkeypatch.setenv("XBOW_ENABLE_HTTP_VALIDATION", "OFF")

    result = safe_http_probe(campaign(), finding())

    assert result.status == "dry_run"


def test_validation_evidence_redacts_query_values(monkeypatch):
    monkeypatch.delenv("XBOW_ENABLE_HTTP_VALIDATION", raising=False)
    result = safe_http_probe(
        campaign(),
        finding(endpoint="https://app.example.test/account?token=super-secret&id=42#private"),
    )

    payload = json.loads(result.json_bytes())

    assert payload["url"] == "https://app.example.test/account"
    assert payload["parameter_names"] == ["id", "token"]
    assert "super-secret" not in str(payload)
    assert "42" not in str(payload)
    assert "private" not in str(payload)


def test_validation_preview_is_text_only_and_bounded(monkeypatch):
    monkeypatch.setenv("XBOW_VALIDATION_PREVIEW_CHARS", "5")

    assert _preview_body(b"abcdefgh", "text/plain; charset=utf-8") == "abcde"
    assert _preview_body(b'{"x":1}', "application/json") == '{"x":'
    assert _preview_body(b"\x89PNGbinary", "image/png") == ""


def test_invalid_validation_preview_limit_fails_closed(monkeypatch):
    for value in ("not-an-int", "-1", "20000"):
        monkeypatch.setenv("XBOW_VALIDATION_PREVIEW_CHARS", value)
        with pytest.raises(ValidationPolicyError, match="XBOW_VALIDATION_PREVIEW_CHARS"):
            _preview_body(b"text", "text/plain")
