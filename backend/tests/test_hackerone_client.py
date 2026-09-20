import base64
import json
import os
import subprocess
import sys
from email.message import Message

import pytest

from app.hackerone_client import (
    HackerOneClient,
    HackerOneClientError,
    HackerOneCredentials,
    _NoRedirect,
    load_hackerone_credentials,
)
from app.secret_vault import set_secret


def _vault_key() -> str:
    return base64.urlsafe_b64encode(b"h" * 32).decode("ascii")


class _Response:
    def __init__(self, payload: bytes, *, status: int = 200, content_type: str = "application/json"):
        self._payload = payload
        self._offset = 0
        self.status = status
        self.headers = Message()
        self.headers["Content-Type"] = content_type

    def getcode(self):
        return self.status

    def read(self, amount: int = -1):
        if amount < 0:
            amount = len(self._payload) - self._offset
        chunk = self._payload[self._offset:self._offset + amount]
        self._offset += len(chunk)
        return chunk


class _Opener:
    def __init__(self, response):
        self.response = response
        self.requests = []
        self.timeouts = []

    def open(self, request, timeout):
        self.requests.append(request)
        self.timeouts.append(timeout)
        return self.response


def test_credentials_read_env_and_emit_basic_auth_without_repr_leak(monkeypatch):
    monkeypatch.setenv("XBOW_VAULT_ENABLED", "false")
    monkeypatch.setenv("XBOW_HACKERONE_API_USERNAME", "researcher")
    monkeypatch.setenv("XBOW_HACKERONE_API_TOKEN", "secret-token-value-123456")

    credentials = load_hackerone_credentials()

    expected = base64.b64encode(b"researcher:secret-token-value-123456").decode("ascii")
    assert credentials.headers()["Authorization"] == f"Basic {expected}"
    assert credentials.headers()["Accept"] == "application/json"
    assert "secret-token-value-123456" not in repr(credentials)


def test_credentials_read_vault_and_refuse_env_fallback(monkeypatch, tmp_path):
    vault_path = tmp_path / "vault.json"
    monkeypatch.setenv("XBOW_VAULT_ENABLED", "true")
    monkeypatch.setenv("XBOW_VAULT_PATH", str(vault_path))
    monkeypatch.setenv("XBOW_VAULT_MASTER_KEY", _vault_key())
    monkeypatch.delenv("XBOW_HACKERONE_API_USERNAME", raising=False)
    monkeypatch.delenv("XBOW_HACKERONE_API_TOKEN", raising=False)
    set_secret("hackerone_api_username", "vault-user")
    set_secret("hackerone_api_token", "vault-token-1234567890")

    credentials = load_hackerone_credentials()
    assert credentials.username == "vault-user"

    monkeypatch.setenv("XBOW_HACKERONE_API_USERNAME", "must-not-win")
    monkeypatch.setenv("XBOW_HACKERONE_API_TOKEN", "must-not-win-token-123")
    vault_path.write_text(json.dumps({"version": 1, "secrets": {}}), encoding="utf-8")
    os.chmod(vault_path, 0o600)

    with pytest.raises(HackerOneClientError, match="credentials are unavailable"):
        load_hackerone_credentials()


def test_missing_credentials_fail_closed(monkeypatch):
    monkeypatch.setenv("XBOW_VAULT_ENABLED", "false")
    monkeypatch.delenv("XBOW_HACKERONE_API_USERNAME", raising=False)
    monkeypatch.delenv("XBOW_HACKERONE_API_TOKEN", raising=False)

    with pytest.raises(HackerOneClientError, match="not configured"):
        load_hackerone_credentials()


@pytest.mark.parametrize("path", ["https://evil.example/test", "//evil.example/test", "/v1/hackers/programs", "../programs"])
def test_client_rejects_paths_that_can_escape_fixed_origin(path):
    client = HackerOneClient(HackerOneCredentials(username="researcher", token="token-value-1234567890"))

    with pytest.raises(HackerOneClientError, match="path"):
        client.get_json(path)


def test_client_get_json_uses_fixed_hackerone_origin_and_basic_auth(monkeypatch):
    response = _Response(b'{"data":[]}')
    opener = _Opener(response)
    monkeypatch.setattr("app.hackerone_client.urllib.request.build_opener", lambda *args: opener)
    credentials = HackerOneCredentials(username="researcher", token="token-value-1234567890")
    client = HackerOneClient(credentials)

    result = client.get_json("hackers/programs", {"page[number]": 2, "page[size]": 100})

    assert result == {"data": []}
    assert opener.timeouts == [10.0]
    request = opener.requests[0]
    assert request.full_url == "https://api.hackerone.com/v1/hackers/programs?page%5Bnumber%5D=2&page%5Bsize%5D=100"
    assert request.get_method() == "GET"
    assert request.get_header("Authorization").startswith("Basic ")
    assert request.get_header("Accept") == "application/json"


def test_client_rejects_redirects():
    handler = _NoRedirect()

    with pytest.raises(HackerOneClientError, match="redirect"):
        handler.redirect_request(None, None, 302, "Found", {}, "https://evil.example")


def test_client_rejects_non_json_and_oversized_response(monkeypatch):
    credentials = HackerOneCredentials(username="researcher", token="token-value-1234567890")
    client = HackerOneClient(credentials)

    opener = _Opener(_Response(b"ok", content_type="text/plain"))
    monkeypatch.setattr("app.hackerone_client.urllib.request.build_opener", lambda *args: opener)
    with pytest.raises(HackerOneClientError, match="not JSON"):
        client.get_json("hackers/programs")

    monkeypatch.setenv("XBOW_HACKERONE_MAX_RESPONSE_BYTES", "1024")
    opener = _Opener(_Response(b"{" + b"x" * 2048 + b"}"))
    monkeypatch.setattr("app.hackerone_client.urllib.request.build_opener", lambda *args: opener)
    with pytest.raises(HackerOneClientError, match="size limit"):
        client.get_json("hackers/programs")


def test_get_all_pages_collects_until_short_page(monkeypatch):
    client = HackerOneClient(HackerOneCredentials(username="researcher", token="token-value-1234567890"))
    pages = {
        1: {"data": [{"id": str(i)} for i in range(100)]},
        2: {"data": [{"id": "last"}]},
    }
    calls = []

    def get_json(path, query=None):
        calls.append((path, dict(query or {})))
        return pages[query["page[number]"]]

    monkeypatch.setattr(client, "get_json", get_json)

    result = client.get_all_pages("hackers/programs")

    assert len(result) == 101
    assert result[-1]["id"] == "last"
    assert calls == [
        ("hackers/programs", {"page[number]": 1, "page[size]": 100}),
        ("hackers/programs", {"page[number]": 2, "page[size]": 100}),
    ]


def test_client_post_json_uses_fixed_origin_and_bounded_json_body(monkeypatch):
    response = _Response(b'{"data":{"id":"4242","type":"report"}}', status=201)
    opener = _Opener(response)
    monkeypatch.setattr("app.hackerone_client.urllib.request.build_opener", lambda *args: opener)
    credentials = HackerOneCredentials(username="researcher", token="token-value-1234567890")
    client = HackerOneClient(credentials)

    payload = {
        "data": {
            "type": "report",
            "attributes": {
                "team_handle": "security",
                "title": "Fixture",
                "vulnerability_information": "Approved report body",
                "impact": "Fixture impact",
                "severity_rating": "medium",
            },
        }
    }
    result = client.post_json("hackers/reports", payload)

    assert result["data"]["id"] == "4242"
    request = opener.requests[0]
    assert request.full_url == "https://api.hackerone.com/v1/hackers/reports"
    assert request.get_method() == "POST"
    assert request.get_header("Content-type") == "application/json"
    assert json.loads(request.data.decode("utf-8")) == payload


def test_client_post_json_rejects_non_object_payload():
    client = HackerOneClient(
        HackerOneCredentials(username="researcher", token="token-value-1234567890")
    )

    with pytest.raises(HackerOneClientError, match="payload"):
        client.post_json("hackers/reports", ["not", "an", "object"])


def test_hackerone_client_imports_cleanly_in_isolated_process():
    result = subprocess.run(
        [sys.executable, "-c", "import app.hackerone_client; print('ok')"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"
