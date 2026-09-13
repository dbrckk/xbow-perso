from email.message import Message

import pytest

from app.pentagi_auth import PentagiAuth
from app.pentagi_flow_status import fetch_pentagi_flow_status
from app.pentagi_transport import PentagiTransportError


class _Socket:
    def settimeout(self, value):
        self.value = value


class _Raw:
    def __init__(self, sock):
        self._sock = sock


class _FP:
    def __init__(self, sock):
        self.raw = _Raw(sock)


class _Response:
    def __init__(self, payload: bytes, content_type: str = "application/json"):
        self._payload = payload
        self._offset = 0
        self.status = 200
        self.headers = Message()
        self.headers["Content-Type"] = content_type
        self.fp = _FP(_Socket())

    def getcode(self):
        return self.status

    def read(self, amount):
        chunk = self._payload[self._offset:self._offset + amount]
        self._offset += len(chunk)
        return chunk


class _Opener:
    def __init__(self, response):
        self.response = response
        self.request = None

    def open(self, request, timeout):
        self.request = request
        return self.response


def _auth(monkeypatch):
    monkeypatch.setattr(
        "app.pentagi_flow_status.load_pentagi_auth",
        lambda: PentagiAuth(token="secret-token-secret"),
    )


def test_fetch_flow_status_is_read_only_and_validated(monkeypatch):
    _auth(monkeypatch)
    opener = _Opener(
        _Response(b'{"id":"flow-42","title":"scan","status":"running"}')
    )
    monkeypatch.setattr(
        "app.pentagi_flow_status.urllib.request.build_opener",
        lambda *args: opener,
    )

    result = fetch_pentagi_flow_status(
        "https://pentagi.example.test/api/v1/graphql",
        "flow-42",
    )

    assert result.flow_id == "flow-42"
    assert result.status == "running"
    assert result.title == "scan"
    assert opener.request.get_method() == "GET"
    assert opener.request.full_url == "https://pentagi.example.test/api/v1/flows/flow-42"


@pytest.mark.parametrize("status", ["created", "running", "waiting", "finished", "failed"])
def test_fetch_flow_status_accepts_documented_states(monkeypatch, status):
    _auth(monkeypatch)
    opener = _Opener(_Response(
        ('{"id":"flow-42","status":"' + status + '"}').encode()
    ))
    monkeypatch.setattr(
        "app.pentagi_flow_status.urllib.request.build_opener",
        lambda *args: opener,
    )

    assert fetch_pentagi_flow_status(
        "https://pentagi.example.test/api/v1/graphql",
        "flow-42",
    ).status == status


@pytest.mark.parametrize(
    "payload",
    [
        b'{"id":"other","status":"running"}',
        b'{"id":"flow-42","status":"unknown"}',
        b'{"id":"flow-42"}',
        b'[]',
    ],
)
def test_fetch_flow_status_fails_closed_on_invalid_response(monkeypatch, payload):
    _auth(monkeypatch)
    opener = _Opener(_Response(payload))
    monkeypatch.setattr(
        "app.pentagi_flow_status.urllib.request.build_opener",
        lambda *args: opener,
    )

    with pytest.raises(PentagiTransportError):
        fetch_pentagi_flow_status(
            "https://pentagi.example.test/api/v1/graphql",
            "flow-42",
        )


def test_fetch_flow_status_rejects_unsafe_base_endpoint(monkeypatch):
    _auth(monkeypatch)
    with pytest.raises(PentagiTransportError):
        fetch_pentagi_flow_status(
            "http://pentagi.example.test/api/v1/graphql",
            "flow-42",
        )
