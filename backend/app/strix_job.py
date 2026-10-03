from __future__ import annotations

import hashlib
from typing import Any

from .main import Campaign
from .queue_backend import QueueBackend
from .strix_execution_contract import (
    StrixExecutionContract,
    StrixExecutionContractError,
    build_strix_execution_contract,
    strix_execution_contract_from_dict,
    verify_strix_execution_contract,
)


STRIX_CONTRACT_PAYLOAD_FIELD = "_strix_execution_contract"


class StrixPreparedJobError(RuntimeError):
    pass


def deterministic_strix_job_id(
    campaign_id: str,
    dedupe_key: str,
) -> str:
    material = "\x1f".join(
        ("strix_scan", str(campaign_id), str(dedupe_key))
    ).encode("utf-8")
    return "strix-" + hashlib.sha256(material).hexdigest()


def _prepared_contract(
    job: dict[str, Any],
) -> StrixExecutionContract:
    payload = job.get("payload")
    if not isinstance(payload, dict):
        raise StrixPreparedJobError("Strix job payload is invalid")
    document = payload.get(STRIX_CONTRACT_PAYLOAD_FIELD)
    try:
        return strix_execution_contract_from_dict(document)
    except StrixExecutionContractError as exc:
        raise StrixPreparedJobError(
            "Strix job execution contract is invalid"
        ) from exc


def require_prepared_strix_contract(
    job: dict[str, Any],
    campaign: Campaign,
) -> StrixExecutionContract:
    contract = _prepared_contract(job)
    try:
        verify_strix_execution_contract(
            contract,
            campaign,
            job_id=str(job.get("id") or ""),
        )
    except StrixExecutionContractError as exc:
        raise StrixPreparedJobError(
            "Strix job execution contract no longer matches campaign policy"
        ) from exc
    return contract


def enqueue_prepared_strix_scan(
    queue: QueueBackend,
    campaign: Campaign,
    payload: dict[str, Any],
    *,
    dedupe_key: str,
    max_attempts: int = 2,
) -> dict[str, Any]:
    if STRIX_CONTRACT_PAYLOAD_FIELD in payload:
        raise StrixPreparedJobError(
            "caller must not provide a Strix execution contract"
        )

    existing = queue.get_by_dedupe(
        campaign.id,
        "strix_scan",
        dedupe_key,
    )
    if existing is not None:
        require_prepared_strix_contract(existing, campaign)
        return existing

    job_id = deterministic_strix_job_id(campaign.id, dedupe_key)
    contract = build_strix_execution_contract(
        campaign,
        job_id=job_id,
    )
    prepared_payload = {
        **payload,
        STRIX_CONTRACT_PAYLOAD_FIELD: contract.to_dict(),
    }
    job = queue.enqueue(
        campaign.id,
        "strix_scan",
        prepared_payload,
        max_attempts=max_attempts,
        dedupe_key=dedupe_key,
        job_id=job_id,
    )
    require_prepared_strix_contract(job, campaign)
    return job
