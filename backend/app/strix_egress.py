from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException

from .strix_broker_models import BrokerHttpRequest, BrokerHttpResponse
from .strix_egress_transport import (
    StrixEgressConcurrencyError,
    StrixEgressNetworkError,
    StrixEgressPolicyError,
    StrixEgressRateLimitError,
    perform_bounded_http_request,
)


app = FastAPI(
    title="xbow Strix read-only egress",
    version="0.1.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


def _verification_secret() -> str:
    secret = os.getenv("XBOW_STRIX_EGRESS_HMAC_KEY", "")
    if not secret:
        raise HTTPException(
            status_code=503,
            detail="Strix egress verification key is unavailable",
        )
    if len(secret.encode("utf-8")) > 4096:
        raise HTTPException(
            status_code=503,
            detail="Strix egress verification key is invalid",
        )
    return secret


def _enabled() -> bool:
    raw = os.getenv("XBOW_STRIX_EGRESS_ENABLED", "false").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    raise HTTPException(
        status_code=503,
        detail="XBOW_STRIX_EGRESS_ENABLED must be a boolean",
    )


@app.get("/healthz")
def healthz() -> dict:
    try:
        enabled = _enabled()
    except HTTPException:
        enabled = False
    return {
        "status": "ok",
        "ready": bool(
            enabled and os.getenv("XBOW_STRIX_EGRESS_HMAC_KEY", "")
        ),
        "mode": "read_only_http",
        "methods": ["GET", "HEAD"],
        "public_network_only": True,
        "redirects_followed": False,
    }


@app.get("/readyz")
def readyz() -> dict:
    if not _enabled():
        raise HTTPException(
            status_code=503,
            detail="Strix read-only egress is disabled",
        )
    _verification_secret()
    return {
        "status": "ready",
        "mode": "read_only_http",
        "methods": ["GET", "HEAD"],
        "public_network_only": True,
        "redirects_followed": False,
    }


@app.post("/v1/fetch", response_model=BrokerHttpResponse)
def fetch(request: BrokerHttpRequest) -> BrokerHttpResponse:
    if not _enabled():
        raise HTTPException(
            status_code=503,
            detail="Strix read-only egress is disabled",
        )
    secret = _verification_secret()
    try:
        return perform_bounded_http_request(
            request,
            verification_secret=secret,
        )
    except StrixEgressRateLimitError as exc:
        raise HTTPException(
            status_code=429,
            detail="Strix egress request rate exceeded",
            headers={
                "Retry-After": f"{exc.retry_after_seconds:.3f}",
            },
        ) from exc
    except StrixEgressConcurrencyError as exc:
        raise HTTPException(
            status_code=429,
            detail="Strix egress request already in flight",
            headers={"Retry-After": "0.100"},
        ) from exc
    except StrixEgressPolicyError as exc:
        raise HTTPException(
            status_code=403,
            detail={
                "message": "Strix egress policy rejected",
                "reason": str(exc),
            },
        ) from exc
    except StrixEgressNetworkError as exc:
        raise HTTPException(
            status_code=502,
            detail="Strix egress request failed",
        ) from exc
