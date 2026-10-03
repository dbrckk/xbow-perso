from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException

from .strix_broker_client import (
    StrixBrokerClientError,
    forward_read_only_request,
)
from .strix_broker_models import (
    BrokerAdmissionRequest,
    BrokerAdmissionResponse,
    BrokerContractDocument,
    BrokerHttpRequest,
    BrokerHttpResponse,
)
from .strix_execution_contract import (
    STRIX_EXECUTION_CONTRACT_SCHEMA,
    StrixExecutionContractError,
    authorize_strix_contract_request,
)


app = FastAPI(
    title="xbow Strix admission broker",
    version="0.2.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


def _broker_verification_secret() -> str:
    secret = os.getenv("XBOW_STRIX_BROKER_HMAC_KEY", "")
    if not secret:
        raise HTTPException(
            status_code=503,
            detail="Strix broker verification key is unavailable",
        )
    if len(secret.encode("utf-8")) > 4096:
        raise HTTPException(
            status_code=503,
            detail="Strix broker verification key is invalid",
        )
    return secret


def _read_only_egress_enabled() -> bool:
    raw = os.getenv(
        "XBOW_STRIX_BROKER_ENABLE_READONLY_EGRESS",
        "false",
    ).strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    raise HTTPException(
        status_code=503,
        detail="XBOW_STRIX_BROKER_ENABLE_READONLY_EGRESS must be a boolean",
    )


def _authorize(
    request: BrokerAdmissionRequest | BrokerHttpRequest,
):
    secret = _broker_verification_secret()
    try:
        return authorize_strix_contract_request(
            request.contract.to_contract(),
            target=request.target,
            requested_rps=request.requested_rps,
            verification_secret=secret,
        )
    except StrixExecutionContractError as exc:
        raise HTTPException(
            status_code=403,
            detail={
                "message": "Strix broker admission rejected",
                "reason": str(exc),
            },
        ) from exc


@app.get("/healthz")
def healthz() -> dict:
    try:
        egress_enabled = _read_only_egress_enabled()
    except HTTPException:
        egress_enabled = False
    return {
        "status": "ok",
        "ready": bool(os.getenv("XBOW_STRIX_BROKER_HMAC_KEY", "")),
        "mode": (
            "read_only_http_proxy"
            if egress_enabled
            else "admission_only"
        ),
        "egress_enabled": egress_enabled,
        "network_io_performed": False,
        "contract_schema": STRIX_EXECUTION_CONTRACT_SCHEMA,
        "allowed_http_methods": ["GET", "HEAD"],
    }


@app.get("/readyz")
def readyz() -> dict:
    _broker_verification_secret()
    egress_enabled = _read_only_egress_enabled()
    return {
        "status": "ready",
        "mode": (
            "read_only_http_proxy"
            if egress_enabled
            else "admission_only"
        ),
        "egress_enabled": egress_enabled,
        "contract_schema": STRIX_EXECUTION_CONTRACT_SCHEMA,
        "allowed_http_methods": ["GET", "HEAD"],
    }


@app.post("/v1/admit", response_model=BrokerAdmissionResponse)
def admit(request: BrokerAdmissionRequest) -> BrokerAdmissionResponse:
    authorized = _authorize(request)
    return BrokerAdmissionResponse(
        allowed=True,
        contract_hash=authorized.contract_hash,
        host=authorized.host,
        target=authorized.target,
        max_requests_per_second=authorized.max_requests_per_second,
    )


@app.post("/v1/request", response_model=BrokerHttpResponse)
def request_http(request: BrokerHttpRequest) -> BrokerHttpResponse:
    if not _read_only_egress_enabled():
        raise HTTPException(
            status_code=503,
            detail="Strix broker read-only egress is disabled",
        )

    _authorize(request)
    try:
        return forward_read_only_request(request)
    except StrixBrokerClientError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=str(exc),
        ) from exc


__all__ = [
    "BrokerAdmissionRequest",
    "BrokerAdmissionResponse",
    "BrokerContractDocument",
    "BrokerHttpRequest",
    "BrokerHttpResponse",
    "admit",
    "healthz",
    "readyz",
    "request_http",
]
