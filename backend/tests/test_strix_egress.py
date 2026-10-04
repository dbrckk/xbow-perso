import pytest
from fastapi import HTTPException

from app.main import Campaign, ProgramRules, TargetInput
from app.strix_broker_models import (
    BrokerContractDocument,
    BrokerHttpRequest,
    BrokerHttpResponse,
)
from app.strix_egress import fetch, healthz, readyz
from app.strix_egress_transport import (
    StrixEgressConcurrencyError,
    StrixEgressNetworkError,
    StrixEgressPolicyError,
    StrixEgressRateLimitError,
)
from app.strix_execution_contract import build_strix_execution_contract


def _campaign():
    return Campaign(
        id="egress-service-campaign",
        target=TargetInput(
            name="fixture",
            primary_url="https://app.example.test",
            rules=ProgramRules(
                authorization_reference="AUTH-1",
                allowed_targets=["*.example.test"],
                max_requests_per_second=1.0,
            ),
        ),
    )


def _request(monkeypatch):
    monkeypatch.setenv("XBOW_AUDIT_HMAC_KEY", "egress-service-secret")
    contract = build_strix_execution_contract(_campaign(), job_id="job-1")
    return BrokerHttpRequest(
        contract=BrokerContractDocument.model_validate(contract.to_dict()),
        target="https://app.example.test/",
        requested_rps=1.0,
    )


def test_egress_service_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("XBOW_STRIX_EGRESS_ENABLED", raising=False)
    monkeypatch.delenv("XBOW_STRIX_EGRESS_HMAC_KEY", raising=False)

    result = healthz()

    assert result["ready"] is False
    assert result["mode"] == "read_only_http"
    assert result["methods"] == ["GET", "HEAD"]
    assert result["public_network_only"] is True
    assert result["redirects_followed"] is False

    with pytest.raises(HTTPException) as exc_info:
        readyz()
    assert exc_info.value.status_code == 503


def test_egress_service_requires_verification_key(monkeypatch):
    monkeypatch.setenv("XBOW_STRIX_EGRESS_ENABLED", "true")
    monkeypatch.delenv("XBOW_STRIX_EGRESS_HMAC_KEY", raising=False)

    with pytest.raises(HTTPException) as exc_info:
        readyz()

    assert exc_info.value.status_code == 503


def test_egress_fetch_calls_transport_only_when_enabled(monkeypatch):
    request = _request(monkeypatch)
    monkeypatch.setenv("XBOW_STRIX_EGRESS_ENABLED", "true")
    monkeypatch.setenv("XBOW_STRIX_EGRESS_HMAC_KEY", "egress-service-secret")
    captured = {}

    def fake_perform(value, *, verification_secret):
        captured["request"] = value
        captured["secret"] = verification_secret
        return BrokerHttpResponse(
            status_code=200,
            reason="OK",
            headers=[],
            body_base64="",
            body_bytes=0,
            truncated=False,
            contract_hash=value.contract.contract_hash,
            host="app.example.test",
            method=value.method,
        )

    monkeypatch.setattr(
        "app.strix_egress.perform_bounded_http_request",
        fake_perform,
    )

    result = fetch(request)

    assert captured["request"] is request
    assert captured["secret"] == "egress-service-secret"
    assert result.egress_enforced is True


@pytest.mark.parametrize(
    ("error", "status"),
    [
        (StrixEgressPolicyError("policy-detail"), 403),
        (StrixEgressNetworkError("network-internal-detail"), 502),
    ],
)
def test_egress_fetch_maps_failures_without_internal_details(
    monkeypatch,
    error,
    status,
):
    request = _request(monkeypatch)
    monkeypatch.setenv("XBOW_STRIX_EGRESS_ENABLED", "true")
    monkeypatch.setenv("XBOW_STRIX_EGRESS_HMAC_KEY", "egress-service-secret")
    monkeypatch.setattr(
        "app.strix_egress.perform_bounded_http_request",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(error),
    )

    with pytest.raises(HTTPException) as exc_info:
        fetch(request)

    assert exc_info.value.status_code == status
    if status == 502:
        assert exc_info.value.detail == "Strix egress request failed"
        assert str(error) not in str(exc_info.value.detail)


def test_egress_fetch_returns_retry_after_for_rate_limit(monkeypatch):
    request = _request(monkeypatch)
    monkeypatch.setenv("XBOW_STRIX_EGRESS_ENABLED", "true")
    monkeypatch.setenv("XBOW_STRIX_EGRESS_HMAC_KEY", "egress-service-secret")
    monkeypatch.setattr(
        "app.strix_egress.perform_bounded_http_request",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            StrixEgressRateLimitError(0.75)
        ),
    )

    with pytest.raises(HTTPException) as exc_info:
        fetch(request)

    assert exc_info.value.status_code == 429
    assert exc_info.value.headers == {"Retry-After": "0.750"}


def test_egress_fetch_returns_retry_after_for_concurrency_limit(monkeypatch):
    request = _request(monkeypatch)
    monkeypatch.setenv("XBOW_STRIX_EGRESS_ENABLED", "true")
    monkeypatch.setenv("XBOW_STRIX_EGRESS_HMAC_KEY", "egress-service-secret")
    monkeypatch.setattr(
        "app.strix_egress.perform_bounded_http_request",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            StrixEgressConcurrencyError("already in flight")
        ),
    )

    with pytest.raises(HTTPException) as exc_info:
        fetch(request)

    assert exc_info.value.status_code == 429
    assert exc_info.value.headers == {"Retry-After": "0.100"}
    assert exc_info.value.detail == "Strix egress request already in flight"
