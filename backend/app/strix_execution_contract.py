from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from .job_provenance import policy_snapshot_fingerprint
from .scope_policy import is_host_allowed, normalize_pattern
from .secret_vault import SecretVaultError, resolve_secret


if TYPE_CHECKING:
    from .main import Campaign


STRIX_EXECUTION_CONTRACT_SCHEMA = "strix-execution-contract-v1"
_SIGNATURE_DOMAIN = b"xbow:strix-execution-contract:v1\x00"


class StrixExecutionContractError(RuntimeError):
    pass


@dataclass(frozen=True)
class StrixExecutionContract:
    schema: str
    engine: str
    campaign_id: str
    job_id: str
    primary_target: str
    policy_fingerprint: str
    allowed_targets: tuple[str, ...]
    denied_targets: tuple[str, ...]
    max_requests_per_second: float
    direct_egress_allowed: bool
    host_container_socket_allowed: bool
    independent_validation_required: bool
    contract_hash: str
    signature_alg: str | None
    signature: str | None

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["allowed_targets"] = list(self.allowed_targets)
        payload["denied_targets"] = list(self.denied_targets)
        return payload

    def redacted_summary(self) -> dict:
        return {
            "schema": self.schema,
            "contract_hash": self.contract_hash,
            "policy_fingerprint": self.policy_fingerprint,
            "max_requests_per_second": self.max_requests_per_second,
            "authenticated": self.signature is not None,
            "direct_egress_allowed": self.direct_egress_allowed,
            "host_container_socket_allowed": self.host_container_socket_allowed,
            "independent_validation_required": self.independent_validation_required,
        }


@dataclass(frozen=True)
class StrixAuthorizedRequest:
    contract_hash: str
    target: str
    host: str
    max_requests_per_second: float


def _validate_job_id(job_id: str) -> str:
    value = str(job_id).strip()
    if (
        not value
        or len(value) > 128
        or any(ord(ch) < 33 or ord(ch) == 127 for ch in value)
    ):
        raise StrixExecutionContractError("Strix execution contract job id is invalid")
    return value


def _canonical_payload(contract: StrixExecutionContract) -> bytes:
    payload = {
        "schema": contract.schema,
        "engine": contract.engine,
        "campaign_id": contract.campaign_id,
        "job_id": contract.job_id,
        "primary_target": contract.primary_target,
        "policy_fingerprint": contract.policy_fingerprint,
        "allowed_targets": list(contract.allowed_targets),
        "denied_targets": list(contract.denied_targets),
        "max_requests_per_second": contract.max_requests_per_second,
        "direct_egress_allowed": contract.direct_egress_allowed,
        "host_container_socket_allowed": contract.host_container_socket_allowed,
        "independent_validation_required": contract.independent_validation_required,
    }
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _contract_secret() -> str | None:
    try:
        return resolve_secret("audit_hmac_key", "XBOW_AUDIT_HMAC_KEY")
    except SecretVaultError as exc:
        raise StrixExecutionContractError(
            "Strix execution contract signing key is unavailable"
        ) from exc


def _unsafe_campaign_reasons(campaign: Campaign) -> list[str]:
    rules = campaign.target.rules
    reasons: list[str] = []
    if not rules.automated_scanning:
        reasons.append("automated_scanning_disabled")
    if rules.destructive_testing:
        reasons.append("destructive_testing_enabled")
    if rules.denial_of_service:
        reasons.append("denial_of_service_enabled")
    if rules.social_engineering:
        reasons.append("social_engineering_enabled")
    if rules.credential_attacks:
        reasons.append("credential_attacks_enabled")

    parsed = urlparse(str(campaign.target.primary_url))
    host = (parsed.hostname or "").lower().rstrip(".")
    if not host or not is_host_allowed(
        host,
        rules.allowed_targets,
        rules.denied_targets,
    ):
        reasons.append("primary_target_outside_scope")
    return reasons


def build_strix_execution_contract(
    campaign: Campaign,
    *,
    job_id: str,
) -> StrixExecutionContract:
    reasons = _unsafe_campaign_reasons(campaign)
    if reasons:
        raise StrixExecutionContractError(
            "Strix execution contract denied: " + ",".join(reasons)
        )

    job_id = _validate_job_id(job_id)
    allowed_targets = tuple(
        sorted({normalize_pattern(item) for item in campaign.target.rules.allowed_targets})
    )
    denied_targets = tuple(
        sorted({normalize_pattern(item) for item in campaign.target.rules.denied_targets})
    )
    unsigned = StrixExecutionContract(
        schema=STRIX_EXECUTION_CONTRACT_SCHEMA,
        engine="strix",
        campaign_id=str(campaign.id),
        job_id=job_id,
        primary_target=str(campaign.target.primary_url),
        policy_fingerprint=policy_snapshot_fingerprint(campaign),
        allowed_targets=allowed_targets,
        denied_targets=denied_targets,
        max_requests_per_second=float(
            campaign.target.rules.max_requests_per_second
        ),
        direct_egress_allowed=False,
        host_container_socket_allowed=False,
        independent_validation_required=True,
        contract_hash="",
        signature_alg=None,
        signature=None,
    )
    canonical = _canonical_payload(unsigned)
    digest = hashlib.sha256(canonical).hexdigest()
    secret = _contract_secret()
    signature = (
        hmac.new(
            secret.encode("utf-8"),
            _SIGNATURE_DOMAIN + canonical,
            hashlib.sha256,
        ).hexdigest()
        if secret
        else None
    )
    return StrixExecutionContract(
        **{
            **unsigned.to_dict(),
            "allowed_targets": unsigned.allowed_targets,
            "denied_targets": unsigned.denied_targets,
            "contract_hash": digest,
            "signature_alg": "hmac-sha256" if signature else None,
            "signature": signature,
        }
    )


def verify_strix_contract_integrity(
    contract: StrixExecutionContract,
    *,
    require_signature: bool,
    verification_secret: str | None = None,
) -> None:
    canonical = _canonical_payload(contract)
    expected_hash = hashlib.sha256(canonical).hexdigest()
    if not hmac.compare_digest(contract.contract_hash, expected_hash):
        raise StrixExecutionContractError("Strix execution contract hash mismatch")

    if contract.signature is None:
        if require_signature:
            raise StrixExecutionContractError(
                "Strix execution contract signature is required"
            )
        if contract.signature_alg is not None:
            raise StrixExecutionContractError(
                "Strix execution contract signature metadata is invalid"
            )
        return

    if contract.signature_alg != "hmac-sha256":
        raise StrixExecutionContractError(
            "Strix execution contract signature algorithm is unsupported"
        )
    secret = (
        verification_secret
        if verification_secret is not None
        else _contract_secret()
    )
    if not secret:
        raise StrixExecutionContractError(
            "Strix execution contract verification key is unavailable"
        )
    expected_signature = hmac.new(
        secret.encode("utf-8"),
        _SIGNATURE_DOMAIN + canonical,
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(contract.signature, expected_signature):
        raise StrixExecutionContractError("Strix execution contract signature mismatch")


def verify_strix_execution_contract(
    contract: StrixExecutionContract,
    campaign: Campaign,
    *,
    job_id: str,
) -> None:
    verify_strix_contract_integrity(contract, require_signature=False)
    if contract.schema != STRIX_EXECUTION_CONTRACT_SCHEMA or contract.engine != "strix":
        raise StrixExecutionContractError("Strix execution contract schema is unsupported")
    if contract.campaign_id != str(campaign.id):
        raise StrixExecutionContractError("Strix execution contract campaign mismatch")
    if contract.job_id != _validate_job_id(job_id):
        raise StrixExecutionContractError("Strix execution contract job mismatch")
    if contract.policy_fingerprint != policy_snapshot_fingerprint(campaign):
        raise StrixExecutionContractError("Strix execution contract policy changed")

    expected_allowed = tuple(
        sorted({normalize_pattern(item) for item in campaign.target.rules.allowed_targets})
    )
    expected_denied = tuple(
        sorted({normalize_pattern(item) for item in campaign.target.rules.denied_targets})
    )
    if contract.allowed_targets != expected_allowed or contract.denied_targets != expected_denied:
        raise StrixExecutionContractError("Strix execution contract scope changed")
    if contract.primary_target != str(campaign.target.primary_url):
        raise StrixExecutionContractError("Strix execution contract target changed")
    if contract.max_requests_per_second != float(
        campaign.target.rules.max_requests_per_second
    ):
        raise StrixExecutionContractError("Strix execution contract rate changed")
    if _unsafe_campaign_reasons(campaign):
        raise StrixExecutionContractError(
            "Strix execution contract campaign is no longer admissible"
        )
    if (
        contract.direct_egress_allowed
        or contract.host_container_socket_allowed
        or not contract.independent_validation_required
    ):
        raise StrixExecutionContractError(
            "Strix execution contract safety invariants changed"
        )


def authorize_strix_contract_request(
    contract: StrixExecutionContract,
    *,
    target: str,
    requested_rps: float,
    verification_secret: str | None = None,
) -> StrixAuthorizedRequest:
    """Authorize one future broker request against a signed immutable contract.

    This function performs no network I/O. It is intended for the isolated
    Strix runtime/broker boundary, where unsigned contracts fail closed.
    """

    verify_strix_contract_integrity(
        contract,
        require_signature=True,
        verification_secret=verification_secret,
    )
    if contract.schema != STRIX_EXECUTION_CONTRACT_SCHEMA or contract.engine != "strix":
        raise StrixExecutionContractError("Strix execution contract schema is unsupported")
    if (
        contract.direct_egress_allowed
        or contract.host_container_socket_allowed
        or not contract.independent_validation_required
    ):
        raise StrixExecutionContractError(
            "Strix execution contract safety invariants changed"
        )

    try:
        parsed = urlparse(str(target))
        host = (parsed.hostname or "").lower().rstrip(".")
        port = parsed.port
    except ValueError as exc:
        raise StrixExecutionContractError("Strix request target is outside scope") from exc

    if (
        parsed.scheme not in {"http", "https"}
        or not host
        or parsed.username
        or parsed.password
        or parsed.fragment
        or port is not None and not 1 <= port <= 65535
        or not is_host_allowed(
            host,
            list(contract.allowed_targets),
            list(contract.denied_targets),
        )
    ):
        raise StrixExecutionContractError("Strix request target is outside scope")

    try:
        rate = float(requested_rps)
    except (TypeError, ValueError) as exc:
        raise StrixExecutionContractError("Strix request rate is invalid") from exc
    if rate <= 0 or rate > contract.max_requests_per_second:
        raise StrixExecutionContractError("Strix request rate exceeds contract cap")

    return StrixAuthorizedRequest(
        contract_hash=contract.contract_hash,
        target=str(target),
        host=host,
        max_requests_per_second=rate,
    )
