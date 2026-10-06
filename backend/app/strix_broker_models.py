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


class BrokerCommandTicketRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract: BrokerContractDocument
    session_id: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9._:-]+$",
    )
    request_id: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9._:-]+$",
    )
    profile: Literal["bootstrap-v1", "web-active-v1"]
    argv: list[str] = Field(min_length=1, max_length=64)
    timeout_seconds: float = Field(ge=0.1, le=300)


class BrokerRunnerExecTicketDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema: Literal["strix-runner-exec-ticket-v1"]
    command_schema: Literal["strix-command-admission-v1"]
    contract_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    session_id: str = Field(min_length=1, max_length=128)
    request_id: str = Field(min_length=1, max_length=128)
    profile: Literal["bootstrap-v1", "web-active-v1"]
    executable: str = Field(min_length=1, max_length=64)
    argv_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    argc: int = Field(ge=1, le=64)
    argv_bytes: int = Field(ge=1, le=16 * 1024)
    timeout_seconds: float = Field(ge=0.1, le=300)
    shell_interpreter_allowed: Literal[False]
    direct_egress_allowed: Literal[False]
    network_scope_enforcement: Literal["broker_required"]
    active_execution_enabled: Literal[False]
    signature_alg: Literal["hmac-sha256"]
    signature: str = Field(pattern=r"^[0-9a-f]{64}$")


class BrokerCommandTicketResponse(BaseModel):
    allowed: Literal[True]
    ticket: BrokerRunnerExecTicketDocument
    mode: Literal["ticket_issuer_only"] = "ticket_issuer_only"
    network_io_performed: Literal[False] = False
    process_execution_performed: Literal[False] = False


class BrokerManifestAdmissionDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema: Literal["strix-manifest-admission-v1"]
    manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    entry_count: int = Field(ge=0, le=128)
    inline_file_count: int = Field(ge=0, le=128)
    local_dir_count: int = Field(ge=0, le=128)
    inline_file_bytes: int = Field(ge=0, le=4 * 1024 * 1024)
    environment_value_bytes: int = Field(ge=0, le=16 * 1024)
    host_paths_included: Literal[False]
    raw_file_content_included: Literal[False]
    filesystem_io_performed: Literal[False]
    manifest_materialized: Literal[False]
    upload_enabled: Literal[False]

    @model_validator(mode="after")
    def validate_counts(self):
        if self.inline_file_count + self.local_dir_count != self.entry_count:
            raise ValueError("manifest entry counts are inconsistent")
        return self


class BrokerManifestTicketRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract: BrokerContractDocument
    request_id: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9._:-]+$",
    )
    image: str = Field(min_length=1, max_length=512)
    exposed_ports: list[int] = Field(default_factory=list, max_length=16)
    manifest: BrokerManifestAdmissionDocument

    @model_validator(mode="after")
    def validate_ports(self):
        if (
            any(
                isinstance(port, bool)
                or not 1 <= port <= 65535
                for port in self.exposed_ports
            )
            or len(set(self.exposed_ports)) != len(self.exposed_ports)
        ):
            raise ValueError("exposed ports are invalid")
        return self


class BrokerRunnerManifestTicketDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema: Literal["strix-runner-manifest-ticket-v1"]
    manifest_schema: Literal["strix-manifest-admission-v1"]
    contract_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    request_id: str = Field(min_length=1, max_length=128)
    image: str = Field(min_length=1, max_length=512)
    exposed_ports: list[int] = Field(default_factory=list, max_length=16)
    manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    entry_count: int = Field(ge=0, le=128)
    inline_file_count: int = Field(ge=0, le=128)
    local_dir_count: int = Field(ge=0, le=128)
    inline_file_bytes: int = Field(ge=0, le=4 * 1024 * 1024)
    environment_value_bytes: int = Field(ge=0, le=16 * 1024)
    host_paths_included: Literal[False]
    raw_file_content_included: Literal[False]
    filesystem_io_performed: Literal[False]
    manifest_materialized: Literal[False]
    upload_enabled: Literal[False]
    active_execution_enabled: Literal[False]
    signature_alg: Literal["hmac-sha256"]
    signature: str = Field(pattern=r"^[0-9a-f]{64}$")


class BrokerManifestTicketResponse(BaseModel):
    allowed: Literal[True]
    ticket: BrokerRunnerManifestTicketDocument
    mode: Literal["ticket_issuer_only"] = "ticket_issuer_only"
    network_io_performed: Literal[False] = False
    process_execution_performed: Literal[False] = False
    manifest_materialized: Literal[False] = False


class BrokerHttpRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract: BrokerContractDocument
    target: str = Field(min_length=1, max_length=2048)
    requested_rps: float = Field(gt=0, le=20)
    method: Literal["GET", "HEAD"] = "GET"
    headers: dict[str, str] = Field(default_factory=dict, max_length=32)


class BrokerHeader(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    value: str = Field(max_length=4096)


class BrokerHttpResponse(BaseModel):
    status_code: int = Field(ge=100, le=599)
    reason: str = Field(max_length=256)
    headers: list[BrokerHeader] = Field(default_factory=list, max_length=64)
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
