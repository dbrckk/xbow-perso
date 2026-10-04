import base64
import socket

import pytest

from app.main import Campaign, ProgramRules, TargetInput
from app.strix_broker_models import BrokerContractDocument, BrokerHttpRequest
from app.strix_egress_transport import (
    ResolvedEndpoint,
    StrixEgressConcurrencyError,
    StrixEgressNetworkError,
    StrixEgressPolicyError,
    StrixEgressRateLimitError,
    _acquire_request_slot,
    _pinned_create_connection,
    _release_request_slot,
    perform_bounded_http_request,
    reset_rate_limits_for_tests,
    resolve_public_endpoint,
)
from app.strix_execution_contract import build_strix_execution_contract


class _Response:
    def __init__(
        self,
        payload=b"ok",
        *,
        status=200,
        reason="OK",
        headers=None,
    ):
        self.payload = payload
        self.status = status
        self.reason = reason
        self._headers = headers or [("Content-Type", "text/plain")]
        self.read_calls = []

    def read(self, amount):
        self.read_calls.append(amount)
        return self.payload[:amount]

    def getheaders(self):
        return list(self._headers)


class _Connection:
    instances = []
    response = _Response()

    def __init__(self, host, port=None, **kwargs):
        self.host = host
        self.port = port
        self.kwargs = kwargs
        self.requests = []
        self.closed = False
        self._create_connection = None
        type(self).instances.append(self)

    def request(self, method, path, headers=None):
        self.requests.append((method, path, dict(headers or {})))

    def getresponse(self):
        return type(self).response

    def close(self):
        self.closed = True


class _Socket:
    def __init__(self):
        self.timeout = None
        self.bound = None
        self.connected = None
        self.closed = False

    def settimeout(self, value):
        self.timeout = value

    def bind(self, source):
        self.bound = source

    def connect(self, target):
        self.connected = target

    def close(self):
        self.closed = True


def _campaign():
    return Campaign(
        id="egress-campaign",
        target=TargetInput(
            name="fixture",
            primary_url="https://app.example.test",
            rules=ProgramRules(
                authorization_reference="AUTH-1",
                allowed_targets=["*.example.test"],
                denied_targets=["admin.example.test"],
                max_requests_per_second=2.0,
            ),
        ),
    )


def _request(monkeypatch, **overrides):
    monkeypatch.setenv("XBOW_AUDIT_HMAC_KEY", "egress-secret")
    contract = build_strix_execution_contract(_campaign(), job_id="job-1")
    payload = {
        "contract": BrokerContractDocument.model_validate(contract.to_dict()),
        "target": "https://api.example.test/path?q=1",
        "requested_rps": 2.0,
        "method": "GET",
        "headers": {},
    }
    payload.update(overrides)
    return BrokerHttpRequest(**payload)


@pytest.fixture(autouse=True)
def _reset_rate_state():
    reset_rate_limits_for_tests()
    _Connection.instances.clear()
    _Connection.response = _Response()
    yield
    reset_rate_limits_for_tests()


def test_resolver_rejects_private_ip_literal():
    with pytest.raises(StrixEgressPolicyError, match="non-public"):
        resolve_public_endpoint("127.0.0.1", 80)


def test_resolver_rejects_mixed_public_private_dns(monkeypatch):
    monkeypatch.setattr(
        "app.strix_egress_transport.socket.getaddrinfo",
        lambda *_args, **_kwargs: [
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                6,
                "",
                ("93.184.216.34", 443),
            ),
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                6,
                "",
                ("10.0.0.1", 443),
            ),
        ],
    )

    with pytest.raises(StrixEgressPolicyError, match="non-public"):
        resolve_public_endpoint("api.example.test", 443)


def test_pinned_connection_uses_validated_sockaddr(monkeypatch):
    sock = _Socket()
    monkeypatch.setattr(
        "app.strix_egress_transport.socket.socket",
        lambda *_args, **_kwargs: sock,
    )
    endpoint = ResolvedEndpoint(
        family=socket.AF_INET,
        sockaddr=("93.184.216.34", 443),
        address="93.184.216.34",
        address_type="ipv4",
    )

    create = _pinned_create_connection(endpoint, 5.0)
    result = create(("api.example.test", 443))

    assert result is sock
    assert sock.connected == ("93.184.216.34", 443)
    assert sock.timeout == 5.0


def test_transport_returns_redirect_without_following_it(monkeypatch):
    request = _request(monkeypatch)
    endpoint = ResolvedEndpoint(
        family=socket.AF_INET,
        sockaddr=("93.184.216.34", 443),
        address="93.184.216.34",
        address_type="ipv4",
    )
    monkeypatch.setattr(
        "app.strix_egress_transport.resolve_public_endpoint",
        lambda *_args, **_kwargs: endpoint,
    )
    monkeypatch.setattr(
        "app.strix_egress_transport.http.client.HTTPSConnection",
        _Connection,
    )
    _Connection.response = _Response(
        b"redirect",
        status=302,
        reason="Found",
        headers=[
            ("Location", "https://outside.invalid/"),
            ("Connection", "close"),
        ],
    )

    result = perform_bounded_http_request(
        request,
        verification_secret="egress-secret",
    )

    assert result.status_code == 302
    assert result.redirect_followed is False
    rendered_headers = [(item.name, item.value) for item in result.headers]
    assert ("Location", "https://outside.invalid/") in rendered_headers
    assert all(name != "Connection" for name, _value in rendered_headers)
    assert base64.b64decode(result.body_base64) == b"redirect"
    connection = _Connection.instances[-1]
    assert connection.host == "api.example.test"
    assert connection.requests == [
        (
            "GET",
            "/path?q=1",
            {
                "User-Agent": "xbow-strix-egress/1.0",
                "Accept": "*/*",
            },
        )
    ]
    assert connection.closed is True


def test_transport_rejects_unsafe_header_before_dns(monkeypatch):
    request = _request(
        monkeypatch,
        headers={"Host": "evil.invalid"},
    )
    called = {"dns": 0}

    def fail_if_called(*_args, **_kwargs):
        called["dns"] += 1
        raise AssertionError("DNS must not run")

    monkeypatch.setattr(
        "app.strix_egress_transport.resolve_public_endpoint",
        fail_if_called,
    )

    with pytest.raises(StrixEgressPolicyError, match="unsafe"):
        perform_bounded_http_request(
            request,
            verification_secret="egress-secret",
        )

    assert called["dns"] == 0


def test_transport_bounds_response_body(monkeypatch):
    request = _request(monkeypatch)
    monkeypatch.setenv("XBOW_STRIX_EGRESS_MAX_RESPONSE_BYTES", "1024")
    monkeypatch.setattr(
        "app.strix_egress_transport.resolve_public_endpoint",
        lambda *_args, **_kwargs: ResolvedEndpoint(
            family=socket.AF_INET,
            sockaddr=("93.184.216.34", 443),
            address="93.184.216.34",
            address_type="ipv4",
        ),
    )
    monkeypatch.setattr(
        "app.strix_egress_transport.http.client.HTTPSConnection",
        _Connection,
    )
    _Connection.response = _Response(b"x" * 2048)

    result = perform_bounded_http_request(
        request,
        verification_secret="egress-secret",
    )

    assert result.body_bytes == 1024
    assert result.truncated is True
    assert len(base64.b64decode(result.body_base64)) == 1024


def test_head_does_not_read_response_body(monkeypatch):
    request = _request(monkeypatch, method="HEAD")
    response = _Response(b"should-not-be-read")
    _Connection.response = response
    monkeypatch.setattr(
        "app.strix_egress_transport.resolve_public_endpoint",
        lambda *_args, **_kwargs: ResolvedEndpoint(
            family=socket.AF_INET,
            sockaddr=("93.184.216.34", 443),
            address="93.184.216.34",
            address_type="ipv4",
        ),
    )
    monkeypatch.setattr(
        "app.strix_egress_transport.http.client.HTTPSConnection",
        _Connection,
    )

    result = perform_bounded_http_request(
        request,
        verification_secret="egress-secret",
    )

    assert result.body_bytes == 0
    assert result.body_base64 == ""
    assert response.read_calls == []


def test_rate_limit_is_enforced_per_contract(monkeypatch):
    request = _request(monkeypatch, requested_rps=1.0)
    monkeypatch.setattr(
        "app.strix_egress_transport.resolve_public_endpoint",
        lambda *_args, **_kwargs: ResolvedEndpoint(
            family=socket.AF_INET,
            sockaddr=("93.184.216.34", 443),
            address="93.184.216.34",
            address_type="ipv4",
        ),
    )
    monkeypatch.setattr(
        "app.strix_egress_transport.http.client.HTTPSConnection",
        _Connection,
    )
    times = iter([100.0, 100.1])
    monkeypatch.setattr(
        "app.strix_egress_transport.time.monotonic",
        lambda: next(times),
    )

    perform_bounded_http_request(
        request,
        verification_secret="egress-secret",
    )
    with pytest.raises(StrixEgressRateLimitError) as exc_info:
        perform_bounded_http_request(
            request,
            verification_secret="egress-secret",
        )

    assert exc_info.value.retry_after_seconds > 0.8


def test_concurrency_limit_is_enforced_per_contract(monkeypatch):
    request = _request(monkeypatch, requested_rps=2.0)
    monkeypatch.setattr(
        "app.strix_egress_transport.resolve_public_endpoint",
        lambda *_args, **_kwargs: ResolvedEndpoint(
            family=socket.AF_INET,
            sockaddr=("93.184.216.34", 443),
            address="93.184.216.34",
            address_type="ipv4",
        ),
    )
    monkeypatch.setattr(
        "app.strix_egress_transport.http.client.HTTPSConnection",
        _Connection,
    )
    monkeypatch.setattr(
        "app.strix_egress_transport.time.monotonic",
        lambda: 100.0,
    )

    contract_hash = request.contract.contract_hash
    _acquire_request_slot(contract_hash, 2.0)
    try:
        with pytest.raises(StrixEgressConcurrencyError, match="in flight"):
            perform_bounded_http_request(
                request,
                verification_secret="egress-secret",
            )
    finally:
        _release_request_slot(contract_hash)


def test_request_slot_is_released_after_network_failure(monkeypatch):
    request = _request(monkeypatch, requested_rps=1.0)
    monkeypatch.setattr(
        "app.strix_egress_transport.resolve_public_endpoint",
        lambda *_args, **_kwargs: ResolvedEndpoint(
            family=socket.AF_INET,
            sockaddr=("93.184.216.34", 443),
            address="93.184.216.34",
            address_type="ipv4",
        ),
    )

    class _FailingConnection(_Connection):
        def request(self, method, path, headers=None):
            raise OSError("fixture network failure")

    monkeypatch.setattr(
        "app.strix_egress_transport.http.client.HTTPSConnection",
        _FailingConnection,
    )
    times = iter([100.0, 102.0])
    monkeypatch.setattr(
        "app.strix_egress_transport.time.monotonic",
        lambda: next(times),
    )

    with pytest.raises(StrixEgressNetworkError, match="Strix egress request failed"):
        perform_bounded_http_request(
            request,
            verification_secret="egress-secret",
        )

    monkeypatch.setattr(
        "app.strix_egress_transport.http.client.HTTPSConnection",
        _Connection,
    )
    result = perform_bounded_http_request(
        request,
        verification_secret="egress-secret",
    )
    assert result.status_code == 200


def test_concurrency_rejection_happens_before_dns(monkeypatch):
    request = _request(monkeypatch, requested_rps=2.0)
    called = {"dns": 0}

    def dns(*_args, **_kwargs):
        called["dns"] += 1
        raise AssertionError("DNS must not run for saturated contract")

    monkeypatch.setattr(
        "app.strix_egress_transport.resolve_public_endpoint",
        dns,
    )
    monkeypatch.setattr(
        "app.strix_egress_transport.time.monotonic",
        lambda: 100.0,
    )

    contract_hash = request.contract.contract_hash
    _acquire_request_slot(contract_hash, 2.0)
    try:
        with pytest.raises(StrixEgressConcurrencyError, match="in flight"):
            perform_bounded_http_request(
                request,
                verification_secret="egress-secret",
            )
    finally:
        _release_request_slot(contract_hash)

    assert called["dns"] == 0


def test_rate_rejection_happens_before_dns(monkeypatch):
    request = _request(monkeypatch, requested_rps=1.0)
    called = {"dns": 0}

    def dns(*_args, **_kwargs):
        called["dns"] += 1
        raise AssertionError("DNS must not run for rate-limited contract")

    monkeypatch.setattr(
        "app.strix_egress_transport.resolve_public_endpoint",
        dns,
    )
    times = iter([100.0, 100.1])
    monkeypatch.setattr(
        "app.strix_egress_transport.time.monotonic",
        lambda: next(times),
    )

    contract_hash = request.contract.contract_hash
    _acquire_request_slot(contract_hash, 1.0)
    _release_request_slot(contract_hash)

    with pytest.raises(StrixEgressRateLimitError):
        perform_bounded_http_request(
            request,
            verification_secret="egress-secret",
        )

    assert called["dns"] == 0
