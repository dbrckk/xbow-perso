import json
from email.message import Message

import pytest

from app.main import Campaign, ProgramRules, TargetInput
from app.strix_broker_client import (
    StrixBrokerClientError,
    forward_read_only_request,
)
from app.strix_broker_models import BrokerContractDocument, BrokerHttpRequest
from app.strix_execution_contract import build_strix_execution_contract


class _Response:
    def __init__(self, payload: bytes, *, status=200):
        self.payload = payload
        self.status = status
        self.offset = 0
        self.headers = Message()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, amount):
        chunk = self.payload[self.offset:self.offset + amount]
        self.offset += len(chunk)
        return chunk


class _Opener:
    def __init__(self, response):
        self.response = response
        self.request = None
        self.timeout = None

    def open(self, request, timeout):
        self.request = request
        self.timeout = timeout
        return self.response


def _request(monkeypatch):
    monkeypatch.setenv("XBOW_AUDIT_HMAC_KEY", "client-secret")
    campaign = Campaign(
        id="client-campaign",
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
    contract = build_strix_execution_contract(campaign, job_id="job-1")
    return BrokerHttpRequest(
        contract=BrokerContractDocument.model_validate(contract.to_dict()),
        target="https://app.example.test/path",
        requested_rps=1.0,
    )


def test_client_posts_only_to_fixed_internal_egress_endpoint(monkeypatch):
    request = _request(monkeypatch)
    payload = {
        "status_code": 200,
        "reason": "OK",
        "headers": [],
        "body_base64": "",
        "body_bytes": 0,
        "truncated": False,
        "contract_hash": request.contract.contract_hash,
        "host": "app.example.test",
        "method": "GET",
        "mode": "read_only_http",
        "egress_enforced": True,
        "network_io_performed": True,
        "redirect_followed": False,
    }
    opener = _Opener(_Response(json.dumps(payload).encode()))
    monkeypatch.setattr("app.strix_broker_client._opener", lambda: opener)

    result = forward_read_only_request(request)

    assert result.status_code == 200
    assert opener.request.full_url == "http://strix-egress:8091/v1/fetch"
    assert opener.request.get_method() == "POST"
    assert opener.timeout == 15.0
    sent = json.loads(opener.request.data.decode())
    assert sent["contract"]["contract_hash"] == request.contract.contract_hash
    assert sent["target"] == request.target


@pytest.mark.parametrize(
    "url",
    [
        "https://strix-egress:8091/v1/fetch",
        "http://127.0.0.1:8091/v1/fetch",
        "http://strix-egress:8092/v1/fetch",
        "http://strix-egress:8091/other",
        "http://user:pass@strix-egress:8091/v1/fetch",
        "http://strix-egress:8091/v1/fetch?debug=1",
    ],
)
def test_client_rejects_non_internal_endpoint_configuration(monkeypatch, url):
    request = _request(monkeypatch)
    monkeypatch.setenv("XBOW_STRIX_EGRESS_URL", url)

    with pytest.raises(StrixBrokerClientError) as exc_info:
        forward_read_only_request(request)

    assert exc_info.value.status_code == 503


def test_client_rejects_oversized_egress_service_response(monkeypatch):
    request = _request(monkeypatch)
    opener = _Opener(_Response(b"x" * (2 * 1024 * 1024 + 1)))
    monkeypatch.setattr("app.strix_broker_client._opener", lambda: opener)

    with pytest.raises(StrixBrokerClientError, match="size limit"):
        forward_read_only_request(request)


def test_client_rejects_invalid_response_shape(monkeypatch):
    request = _request(monkeypatch)
    opener = _Opener(_Response(b'{"status_code":200}'))
    monkeypatch.setattr("app.strix_broker_client._opener", lambda: opener)

    with pytest.raises(StrixBrokerClientError, match="invalid response"):
        forward_read_only_request(request)
