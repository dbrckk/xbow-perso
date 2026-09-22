from fastapi import HTTPException

import app.hackerone_api as hackerone_api
from app.hackerone_api import _hackerone_error_detail, _upstream_error
from app.hackerone_client import HackerOneClientError


def test_hackerone_error_detail_classifies_auth_without_secrets():
    detail = _hackerone_error_detail(
        HackerOneClientError("HackerOne returned HTTP 401", status_code=401)
    )
    assert detail == {
        "message": "HackerOne authentication failed",
        "reason": "hackerone_authentication_failed",
        "upstream_status": 401,
        "retryable": False,
        "contains_secrets": False,
    }


def test_hackerone_error_detail_classifies_retryable_transport():
    detail = _hackerone_error_detail(
        HackerOneClientError("HackerOne transport connection failed")
    )
    assert detail["reason"] == "hackerone_connection_failed"
    assert detail["retryable"] is True
    assert detail["contains_secrets"] is False


def test_hackerone_error_detail_classifies_rate_limit():
    detail = _hackerone_error_detail(
        HackerOneClientError("HackerOne returned HTTP 429", status_code=429)
    )
    assert detail["reason"] == "hackerone_rate_limited"
    assert detail["retryable"] is True
    assert detail["upstream_status"] == 429


def test_upstream_error_preserves_structured_reason_for_frontend_recovery():
    error = _upstream_error(
        HackerOneClientError("HackerOne response contains invalid JSON")
    )
    assert error.status_code == 502
    assert error.detail["reason"] == "hackerone_upstream_request_failed"
    assert error.detail["message"] == "HackerOne upstream request failed"
    assert error.detail["contains_secrets"] is False


def test_upstream_retryable_error_returns_503_with_structured_reason():
    error = _upstream_error(
        HackerOneClientError("HackerOne transport timed out")
    )
    assert error.status_code == 503
    assert error.detail["reason"] == "hackerone_timeout"
    assert error.detail["retryable"] is True


def test_program_specific_422_is_replaceable_review_candidate(monkeypatch):
    def fail(_handle):
        raise HackerOneClientError("HackerOne returned HTTP 422", status_code=422)

    monkeypatch.setattr(hackerone_api, "fetch_hackerone_program_snapshot", fail)
    try:
        hackerone_api.get_hackerone_program_review_draft("example")
    except HTTPException as exc:
        assert exc.status_code == 409
        assert exc.detail["reason"] == "hackerone_program_review_unavailable"
        assert exc.detail["handle"] == "example"
        assert exc.detail["upstream_status"] == 422
    else:
        raise AssertionError("expected HTTPException")
