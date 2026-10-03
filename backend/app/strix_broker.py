from __future__ import annotations

import os
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .strix_execution_contract import (
    STRIX_EXECUTION_CONTRACT_SCHEMA,
    StrixExecutionContract,
    StrixExecutionContractError,
    authorize_strix_contract_request,
)


app = FastAPI(
    title="xbow Strix admission broker",
    version="0.1.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


class BrokerContractDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema: Literal["strix-execution-contract-v1"]
    engine: Literal["strix"]
    campaign_id: str = Field(min_length=1, max_length=128)
    job_id: str = Field(min_length=1, max_length=128)
    primary_target: str = Field(min_length=1, max_length=2048)
    policy_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    allowed_targets: list[str] = Field(min_length=1, max_length=256)
    denied_targets: list[str] = Field(default_factory=list, max_length=256)
    max_requests_per_second: float = Field(gt=0, le=20)
    direct_egress_allowed: Literal[False]
    host_container_socket_allowed: Literal[False]
    independent_validation_required: Literal[True]
    contract_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    signature_alg: Literal["hmac-sha256"]
    signature: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def normalize_scope(self):
        self.allowed_targets = sorted(set(self.allowed_targets))
        self.denied_targets = sorted(set(self.denied_targets))
        return self

    def to_contract(self) -> StrixExecutionContract:
        return StrixExecutionContract(
            schema=self.schema,
            engine=self.engine,
            campaign_id=self.campaign_id,
            job_id=self.job_id,
            primary_target=self.primary_target,
            policy_fingerprint=self.policy_fingerprint,
            allowed_targets=tuple(self.allowed_targets),
            denied_targets=tuple(self.denied_targets),
            max_requests_per_second=self.max_requests_per_second,
            direct_egress_allowed=self.direct_egress_allowed,
            host_container_socket_allowed=self.host_container_socket_allowed,
            independent_validation_required=self.independent_validation_required,
            contract_hash=self.contract_hash,
            signature_alg=self.signature_alg,
            signature=self.signature,
        )


class BrokerAdmissionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract: BrokerContractDocument
    target: str = Field(min_length=1, max_length=2048)
    requested_rps: float = Field(gt=0, le=20)


class BrokerAdmissionResponse(BaseModel):
    allowed: Literal[True]
    contract_hash: str
    host: str
    target: str
    max_requests_per_second: float
    mode: Literal["admission_only"] = "admission_only"
    egress_enabled: Literal[False] = False
    network_io_performed: Literal[False] = False


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


@app.get("/healthz")
def healthz() -> dict:
    return {
        "status": "ok",
        "ready": bool(os.getenv("XBOW_STRIX_BROKER_HMAC_KEY", "")),
        "mode": "admission_only",
        "egress_enabled": False,
        "network_io_performed": False,
        "contract_schema": STRIX_EXECUTION_CONTRACT_SCHEMA,
    }


@app.get("/readyz")
def readyz() -> dict:
    _broker_verification_secret()
    return {
        "status": "ready",
        "mode": "admission_only",
        "egress_enabled": False,
        "contract_schema": STRIX_EXECUTION_CONTRACT_SCHEMA,
    }


@app.post("/v1/admit", response_model=BrokerAdmissionResponse)
def admit(request: BrokerAdmissionRequest) -> BrokerAdmissionResponse:
    secret = _broker_verification_secret()
    try:
        authorized = authorize_strix_contract_request(
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

    return BrokerAdmissionResponse(
        allowed=True,
        contract_hash=authorized.contract_hash,
        host=authorized.host,
        target=authorized.target,
        max_requests_per_second=authorized.max_requests_per_second,
    )
