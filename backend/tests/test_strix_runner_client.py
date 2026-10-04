import json
import urllib.error

import pytest

from app.strix_runner_client import (
    StrixRunnerClientError,
    check_runner_readiness,
)


class _Response:
    def __init__(self, payload: bytes, status: int = 200):
        self._payload = payload
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, size=-1):
        return self._payload[:size]


class _Opener:
    def __init__(self, response):
        self.response = response
        self.request = None
        self.timeout = None

    def open(self, request, timeout):
        self.request = request
        self.timeout = timeout
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def _ready_payload(**overrides):
    payload = {
        "status": "ready",
        "protocol": "strix-runner-rpc-v1",
        "active_execution_enabled": False,
        "implemented_operations": [],
        "runner_attested": True,
        "runner_version": "1.6.2",
        "source_commit": "ff5c8cc8e46d8e60c2bc2439f7bcb07c05ca3db2",
        "binary_sha256": "a" * 64,
    }
    payload.update(overrides)
    return json.dumps(payload).encode()


def test_runner_readiness_client_accepts_exact_inert_posture(monkeypatch):
    opener = _Opener(_Response(_ready_payload()))
    monkeypatch.setattr("app.strix_runner_client._opener", lambda: opener)

    result = check_runner_readiness()

    assert result == {
        "ready": True,
        "protocol": "strix-runner-rpc-v1",
        "runner_version": "1.6.2",
        "source_commit": "ff5c8cc8e46d8e60c2bc2439f7bcb07c05ca3db2",
        "binary_sha256": "a" * 64,
        "active_execution_enabled": False,
        "implemented_operations": [],
    }
    assert opener.request.full_url == "http://strix-runner:8092/readyz"
    assert opener.request.get_method() == "GET"
    assert opener.timeout == 5.0


@pytest.mark.parametrize(
    "overrides",
    (
        {"status": "ok"},
        {"protocol": "strix-runner-rpc-v2"},
        {"active_execution_enabled": True},
        {"implemented_operations": ["exec"]},
        {"runner_attested": False},
        {"runner_version": "1.6.3"},
        {"source_commit": "0" * 40},
        {"binary_sha256": "A" * 64},
    ),
)
def test_runner_readiness_client_rejects_unexpected_posture(
    monkeypatch,
    overrides,
):
    opener = _Opener(_Response(_ready_payload(**overrides)))
    monkeypatch.setattr("app.strix_runner_client._opener", lambda: opener)

    with pytest.raises(StrixRunnerClientError, match="posture"):
        check_runner_readiness()


def test_runner_readiness_client_rejects_oversized_response(monkeypatch):
    opener = _Opener(_Response(b"x" * 4097))
    monkeypatch.setattr("app.strix_runner_client._opener", lambda: opener)

    with pytest.raises(StrixRunnerClientError, match="size"):
        check_runner_readiness()


def test_runner_readiness_client_rejects_invalid_json(monkeypatch):
    opener = _Opener(_Response(b"not-json"))
    monkeypatch.setattr("app.strix_runner_client._opener", lambda: opener)

    with pytest.raises(StrixRunnerClientError, match="invalid"):
        check_runner_readiness()


def test_runner_readiness_client_maps_network_failure(monkeypatch):
    opener = _Opener(
        urllib.error.URLError("fixture unavailable")
    )
    monkeypatch.setattr("app.strix_runner_client._opener", lambda: opener)

    with pytest.raises(StrixRunnerClientError, match="unavailable"):
        check_runner_readiness()
