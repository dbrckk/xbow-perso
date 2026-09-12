import json

import pytest

import app.alert_delivery as delivery
from app.alert_delivery import AlertDeliveryError, deliver_alerts


class Response:
    status = 204

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class Opener:
    def __init__(self):
        self.requests = []

    def open(self, request, timeout):
        self.requests.append((request, timeout))
        return Response()


def _alerts():
    return {
        "status": "alert",
        "alerts": [
            {
                "code": "queue_stalled",
                "severity": "critical",
                "value": 301,
                "threshold": 300,
                "target": "https://must-not-leak.example",
                "job_id": "must-not-leak",
            }
        ],
        "internal": {"secret": "must-not-leak"},
    }


def test_webhook_delivery_is_redacted_and_https_only(monkeypatch):
    monkeypatch.setenv("XBOW_ALERT_WEBHOOK_URL", "https://alerts.example/hook")
    monkeypatch.setenv("XBOW_VAULT_ENABLED", "false")
    opener = Opener()
    monkeypatch.setattr(delivery, "build_opener", lambda *_args: opener)

    result = deliver_alerts(_alerts())

    assert result == {"delivered": True, "status_code": 204, "signed": False}
    request, timeout = opener.requests[0]
    body = json.loads(request.data.decode("utf-8"))
    assert body == {
        "status": "alert",
        "alerts": [
            {
                "code": "queue_stalled",
                "severity": "critical",
                "value": 301,
                "threshold": 300,
            }
        ],
        "aggregate_only": True,
    }
    assert timeout == 5.0
    assert "must-not-leak" not in request.data.decode("utf-8")


def test_webhook_delivery_skips_when_no_active_alerts(monkeypatch):
    monkeypatch.delenv("XBOW_ALERT_WEBHOOK_URL", raising=False)

    result = deliver_alerts({"status": "ok", "alerts": []})

    assert result == {"delivered": False, "reason": "no active alerts"}


@pytest.mark.parametrize(
    "url",
    [
        "http://alerts.example/hook",
        "https://user:pass@alerts.example/hook",
        "https://alerts.example:9000/hook",
        "https://alerts.example/hook#fragment",
    ],
)
def test_webhook_rejects_unsafe_destinations(monkeypatch, url):
    monkeypatch.setenv("XBOW_ALERT_WEBHOOK_URL", url)
    monkeypatch.setenv("XBOW_VAULT_ENABLED", "false")

    with pytest.raises(AlertDeliveryError):
        deliver_alerts(_alerts())


def test_webhook_hmac_signature(monkeypatch):
    monkeypatch.setenv("XBOW_ALERT_WEBHOOK_URL", "https://alerts.example/hook")
    monkeypatch.setenv("XBOW_ALERT_WEBHOOK_HMAC_KEY", "signing-secret")
    monkeypatch.setenv("XBOW_VAULT_ENABLED", "false")
    opener = Opener()
    monkeypatch.setattr(delivery, "build_opener", lambda *_args: opener)

    result = deliver_alerts(_alerts())

    request, _timeout = opener.requests[0]
    signature = request.headers["X-xbow-signature-sha256"]
    assert len(signature) == 64
    assert result["signed"] is True


def test_webhook_vault_mode_refuses_legacy_signing_secret(monkeypatch):
    monkeypatch.setenv("XBOW_ALERT_WEBHOOK_URL", "https://alerts.example/hook")
    monkeypatch.setenv("XBOW_ALERT_WEBHOOK_HMAC_KEY", "legacy")
    monkeypatch.setenv("XBOW_VAULT_ENABLED", "true")
    monkeypatch.setenv("XBOW_VAULT_MASTER_KEY", "invalid-but-not-read")

    with pytest.raises(AlertDeliveryError, match="legacy alert webhook signing secret"):
        deliver_alerts(_alerts())


def test_webhook_timeout_configuration_fails_closed(monkeypatch):
    monkeypatch.setenv("XBOW_ALERT_WEBHOOK_URL", "https://alerts.example/hook")
    monkeypatch.setenv("XBOW_ALERT_WEBHOOK_TIMEOUT_SECONDS", "30")
    monkeypatch.setenv("XBOW_VAULT_ENABLED", "false")
    opener = Opener()
    monkeypatch.setattr(delivery, "build_opener", lambda *_args: opener)

    with pytest.raises(AlertDeliveryError, match="between 1 and 15"):
        deliver_alerts(_alerts())
