import json
import time
from urllib.parse import parse_qsl, urlparse

import pytest

import app.validator as validator
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
                max_requests_per_second=2.0,
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


class _Response:
    def __init__(self, body: bytes, *, status: int = 200, content_type: str = "text/plain"):
        self._body = body
        self.status = status
        self.headers = {"Content-Type": content_type}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self, _limit: int) -> bytes:
        return self._body


class _EchoingOpener:
    def __init__(self):
        self.urls: list[str] = []

    def open(self, request, timeout=None):
        del timeout
        url = request.full_url
        self.urls.append(url)
        if len(self.urls) == 1:
            return _Response(b"baseline")
        values = dict(parse_qsl(urlparse(url).query, keep_blank_values=True))
        return _Response(f"echo:{values.get('q', '')}".encode())


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


def test_differential_validation_uses_inert_marker_on_existing_query_parameter(monkeypatch):
    monkeypatch.setenv("XBOW_ENABLE_HTTP_VALIDATION", "true")
    monkeypatch.setenv("XBOW_ENABLE_DIFFERENTIAL_VALIDATION", "true")
    opener = _EchoingOpener()
    monkeypatch.setattr(validator, "build_opener", lambda *_handlers: opener)
    sleeps: list[float] = []
    monkeypatch.setattr(time, "sleep", lambda seconds: sleeps.append(seconds))

    result = safe_http_probe(
        campaign(),
        finding(endpoint="https://app.example.test/search?q=private-value#fragment"),
    )
    payload = json.loads(result.json_bytes())

    assert len(opener.urls) == 2
    assert opener.urls[0] == "https://app.example.test/search?q=private-value#fragment"
    assert opener.urls[1].startswith("https://app.example.test/search?q=xbowv1-")
    assert sleeps == [pytest.approx(0.5)]
    assert payload["url"] == "https://app.example.test/search"
    assert payload["parameter_names"] == ["q"]
    assert payload["differential"] == {
        "eligible": True,
        "parameter": "q",
        "baseline_status": 200,
        "marker_status": 200,
        "status_changed": False,
        "body_changed": True,
        "marker_reflected": True,
    }
    serialized = json.dumps(payload, sort_keys=True)
    assert "private-value" not in serialized
    assert "fragment" not in serialized
    assert "xbowv1-" not in serialized


def test_differential_validation_does_not_invent_query_parameters(monkeypatch):
    monkeypatch.setenv("XBOW_ENABLE_HTTP_VALIDATION", "true")
    monkeypatch.setenv("XBOW_ENABLE_DIFFERENTIAL_VALIDATION", "true")
    opener = _EchoingOpener()
    monkeypatch.setattr(validator, "build_opener", lambda *_handlers: opener)

    result = safe_http_probe(campaign(), finding(endpoint="/account"))
    payload = json.loads(result.json_bytes())

    assert len(opener.urls) == 1
    assert payload["differential"] == {
        "eligible": False,
        "reason": "no_existing_query_parameter",
    }


def test_invalid_differential_validation_gate_fails_closed_before_network(monkeypatch):
    monkeypatch.setenv("XBOW_ENABLE_HTTP_VALIDATION", "true")
    monkeypatch.setenv("XBOW_ENABLE_DIFFERENTIAL_VALIDATION", "sometimes")
    opener = _EchoingOpener()
    monkeypatch.setattr(validator, "build_opener", lambda *_handlers: opener)

    with pytest.raises(ValidationPolicyError, match="XBOW_ENABLE_DIFFERENTIAL_VALIDATION"):
        safe_http_probe(
            campaign(),
            finding(endpoint="https://app.example.test/search?q=value"),
        )

    assert opener.urls == []
