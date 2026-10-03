from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .strix_execution_contract import StrixExecutionContract


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


class BrokerHttpRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract: BrokerContractDocument
    target: str = Field(min_length=1, max_length=2048)
    requested_rps: float = Field(gt=0, le=20)
    method: Literal["GET", "HEAD"] = "GET"
    headers: dict[str, str] = Field(default_factory=dict, max_length=32)


class BrokerHttpResponse(BaseModel):
    status_code: int = Field(ge=100, le=599)
    reason: str = Field(max_length=256)
    headers: dict[str, str]
    body_base64: str
    body_bytes: int = Field(ge=0)
    truncated: bool
    contract_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    host: str
    method: Literal["GET", "HEAD"]
    mode: Literal["read_only_http"] = "read_only_http"
    egress_enforced: Literal[True] = True
    network_io_performed: Literal[True] = True
    redirect_followed: Literal[False] = False
