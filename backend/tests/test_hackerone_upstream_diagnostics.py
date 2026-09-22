from app.hackerone_api import _hackerone_error_detail
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
