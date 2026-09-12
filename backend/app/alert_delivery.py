from __future__ import annotations

import hashlib
import hmac
import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .secret_vault import SecretVaultError, resolve_secret


class AlertDeliveryError(RuntimeError):
    pass


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _webhook_url() -> str:
    raw = os.getenv("XBOW_ALERT_WEBHOOK_URL", "").strip()
    if not raw:
        raise AlertDeliveryError("alert webhook URL is not configured")
    parsed = urlparse(raw)
    if parsed.scheme != "https" or not parsed.hostname:
        raise AlertDeliveryError("alert webhook URL must use HTTPS")
    if parsed.username or parsed.password or parsed.fragment:
        raise AlertDeliveryError("alert webhook URL contains forbidden components")
    if parsed.port not in {None, 443, 8443}:
        raise AlertDeliveryError("alert webhook port is not allowed")
    return raw


def _timeout_seconds() -> float:
    raw = os.getenv("XBOW_ALERT_WEBHOOK_TIMEOUT_SECONDS", "5").strip()
    try:
        value = float(raw)
    except ValueError as exc:
        raise AlertDeliveryError("alert webhook timeout must be numeric") from exc
    if not 1.0 <= value <= 15.0:
        raise AlertDeliveryError("alert webhook timeout must be between 1 and 15 seconds")
    return value


def _redacted_payload(alerts: dict) -> dict:
    safe_alerts = []
    for item in alerts.get("alerts") or []:
        safe_alerts.append(
            {
                "code": str(item.get("code") or "")[:64],
                "severity": str(item.get("severity") or "")[:16],
                "value": int(item.get("value") or 0),
                "threshold": int(item.get("threshold") or 0),
            }
        )
    return {
        "status": "alert" if safe_alerts else "ok",
        "alerts": safe_alerts,
        "aggregate_only": True,
    }


def _signature(body: bytes) -> str | None:
    try:
        secret = resolve_secret("alert_webhook_hmac_key", "XBOW_ALERT_WEBHOOK_HMAC_KEY")
    except SecretVaultError as exc:
        raise AlertDeliveryError("alert webhook signing secret is unavailable") from exc
    if not secret:
        return None
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def deliver_alerts(alerts: dict) -> dict:
    payload = _redacted_payload(alerts)
    if payload["status"] != "alert":
        return {"delivered": False, "reason": "no active alerts"}

    url = _webhook_url()
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "xbow-perso-alerts/1.0",
        "Content-Length": str(len(body)),
    }
    signature = _signature(body)
    if signature:
        headers["X-Xbow-Signature-SHA256"] = signature

    request = Request(url, data=body, method="POST", headers=headers)
    opener = build_opener(_NoRedirect())
    try:
        with opener.open(request, timeout=_timeout_seconds()) as response:
            status = int(response.status)
    except HTTPError as exc:
        raise AlertDeliveryError(f"alert webhook returned HTTP {exc.code}") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise AlertDeliveryError("alert webhook delivery failed") from exc

    if not 200 <= status < 300:
        raise AlertDeliveryError(f"alert webhook returned HTTP {status}")
    return {"delivered": True, "status_code": status, "signed": signature is not None}
