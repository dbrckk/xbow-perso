from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException

from .strix_broker_client import (
    StrixBrokerClientError,
    check_egress_ready,
    forward_read_only_request,
)
from .strix_broker_models import (
    BrokerAdmissionRequest,
    BrokerAdmissionResponse,
    BrokerCommandTicketRequest,
    BrokerCommandTicketResponse,
    BrokerContractDocument,
    BrokerHttpRequest,
    BrokerHttpResponse,
    BrokerRunnerExecTicketDocument,
)
from .strix_command_admission import (
    StrixCommandAdmissionError,
    authorize_strix_command,
)
from .strix_execution_contract import (
    STRIX_EXECUTION_CONTRACT_SCHEMA,
    StrixExecutionContractError,
    authorize_strix_contract_request,
)
from .strix_runner_exec_ticket import (
    STRIX_RUNNER_EXEC_TICKET_SCHEMA,
    StrixRunnerExecTicketError,
    build_strix_runner_exec_ticket,
    validate_strix_runner_exec_ticket_secret,
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


def _runner_admission_signing_secret() -> str:
    secret = os.getenv("XBOW_STRIX_RUNNER_ADMISSION_HMAC_KEY", "")
    if not secret:
        raise HTTPException(
            status_code=503,
            detail="Strix runner admission signing key is unavailable",
        )
    try:
        validate_strix_runner_exec_ticket_secret(secret)
    except StrixRunnerExecTicketError as exc:
        raise HTTPException(
            status_code=503,
            detail="Strix runner admission signing key is invalid",
        ) from exc
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
        "ready": bool(os.getenv("XBOW_STRIX_BROKER_HMAC_KEY", ""))
        and bool(os.getenv("XBOW_STRIX_RUNNER_ADMISSION_HMAC_KEY", "")),
        "contract_verifier_ready": bool(
            os.getenv("XBOW_STRIX_BROKER_HMAC_KEY", "")
        ),
        "ticket_issuer_ready": bool(
            os.getenv("XBOW_STRIX_RUNNER_ADMISSION_HMAC_KEY", "")
        ),
        "ticket_schema": STRIX_RUNNER_EXEC_TICKET_SCHEMA,
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
    _runner_admission_signing_secret()
    egress_enabled = _read_only_egress_enabled()
    if egress_enabled:
        try:
            check_egress_ready()
        except StrixBrokerClientError as exc:
            raise HTTPException(
                status_code=503,
                detail="Strix read-only egress is not ready",
            ) from exc
    return {
        "status": "ready",
        "mode": (
            "read_only_http_proxy"
            if egress_enabled
            else "admission_only"
        ),
        "egress_enabled": egress_enabled,
        "contract_schema": STRIX_EXECUTION_CONTRACT_SCHEMA,
        "ticket_schema": STRIX_RUNNER_EXEC_TICKET_SCHEMA,
        "ticket_issuer_ready": True,
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


@app.post(
    "/v1/command-ticket",
    response_model=BrokerCommandTicketResponse,
)
def issue_command_ticket(
    request: BrokerCommandTicketRequest,
) -> BrokerCommandTicketResponse:
    verification_secret = _broker_verification_secret()
    try:
        authorized = authorize_strix_command(
            request.contract.to_contract(),
            session_id=request.session_id,
            request_id=request.request_id,
            profile=request.profile,
            argv=request.argv,
            timeout_seconds=request.timeout_seconds,
            verification_secret=verification_secret,
        )
    except StrixCommandAdmissionError as exc:
        raise HTTPException(
            status_code=403,
            detail={
                "message": "Strix command admission rejected",
                "reason": str(exc),
            },
        ) from exc

    signing_secret = _runner_admission_signing_secret()
    ticket = build_strix_runner_exec_ticket(
        authorized.to_dict(),
        signing_secret=signing_secret,
    )
    return BrokerCommandTicketResponse(
        allowed=True,
        ticket=BrokerRunnerExecTicketDocument.model_validate(
            ticket.to_dict()
        ),
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
    "BrokerCommandTicketRequest",
    "BrokerCommandTicketResponse",
    "BrokerContractDocument",
    "BrokerHttpRequest",
    "BrokerHttpResponse",
    "admit",
    "healthz",
    "issue_command_ticket",
    "readyz",
    "request_http",
]
