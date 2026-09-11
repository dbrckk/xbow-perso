from __future__ import annotations

import hashlib

from .main import Campaign, Finding
from .observation_graph import Observation
from .storage import Storage


def observation_id(prefix: str, value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]
    return f"{prefix}:{digest}"


def record_asset(
    store: Storage,
    campaign: Campaign,
    asset: str,
    source: str,
) -> str:
    observation = Observation(
        id=observation_id("asset", f"{source}\x1f{asset}"),
        kind="asset",
        value=asset,
        source=source,
    )
    store.put_observation(campaign.id, observation.to_dict())
    return observation.id


def record_endpoint(
    store: Storage,
    campaign: Campaign,
    endpoint: str,
    *,
    source: str,
    parent_id: str,
) -> str:
    observation = Observation(
        id=observation_id("endpoint", f"{source}\x1f{endpoint}"),
        kind="endpoint",
        value=endpoint,
        source=source,
        parent_ids=(parent_id,),
    )
    store.put_observation(campaign.id, observation.to_dict())
    return observation.id


def record_finding_chain(
    store: Storage,
    campaign: Campaign,
    finding: Finding,
) -> str:
    asset_id = record_asset(store, campaign, finding.asset, finding.discovered_by)
    parent_id = asset_id

    if finding.endpoint:
        endpoint_value = str(finding.endpoint)
        if endpoint_value.startswith("/"):
            endpoint_value = str(finding.asset).rstrip("/") + endpoint_value
        parent_id = record_endpoint(
            store,
            campaign,
            endpoint_value,
            source=finding.discovered_by,
            parent_id=asset_id,
        )

    observation = Observation(
        id=f"finding:{finding.id}",
        kind="finding",
        value=finding.id,
        source=finding.discovered_by,
        parent_ids=(parent_id,),
        metadata={
            "title": finding.title,
            "severity": finding.severity,
            "endpoint": finding.endpoint,
            "cwe": finding.cwe,
            "cvss": finding.cvss,
        },
    )
    store.put_observation(campaign.id, observation.to_dict())

    for index, evidence in enumerate(finding.evidence[:50], start=1):
        evidence_observation = Observation(
            id=observation_id(
                "evidence",
                f"{finding.discovered_by}\x1f{finding.id}\x1f{index}\x1f{evidence}",
            ),
            kind="evidence",
            value=str(evidence),
            source=finding.discovered_by,
            parent_ids=(observation.id,),
            metadata={
                "finding_id": finding.id,
                "scanner_evidence": True,
                "ordinal": index,
            },
        )
        store.put_observation(campaign.id, evidence_observation.to_dict())

    return observation.id


def record_artifact(
    store: Storage,
    campaign: Campaign,
    artifact: dict,
    *,
    source: str,
    parent_ids: tuple[str, ...] = (),
    kind: str = "evidence",
    value: str | None = None,
    metadata: dict | None = None,
) -> str:
    observation = Observation(
        id=f"{kind}:{artifact['id']}",
        kind=kind,
        value=value or artifact["id"],
        source=source,
        parent_ids=parent_ids,
        metadata={"artifact_id": artifact["id"], **(metadata or {})},
    )
    store.put_observation(campaign.id, observation.to_dict())
    return observation.id


def record_typed_child(
    store: Storage,
    campaign: Campaign,
    *,
    kind: str,
    value: str,
    source: str,
    parent_id: str,
    metadata: dict | None = None,
    identity: str | None = None,
) -> str:
    observation = Observation(
        id=observation_id(kind, identity or f"{source}\x1f{value}"),
        kind=kind,
        value=value,
        source=source,
        parent_ids=(parent_id,),
        metadata=metadata or {},
    )
    store.put_observation(campaign.id, observation.to_dict())
    return observation.id
