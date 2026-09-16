from __future__ import annotations

import hashlib
import json

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


def _differential_artifact_metadata(
    store: Storage,
    campaign: Campaign,
    artifact: dict,
    *,
    source: str,
    kind: str,
) -> dict[str, object]:
    if (
        kind != "validation"
        or source != "independent-http-validator"
        or artifact.get("kind") != "validation"
        or artifact.get("media_type") != "application/json"
    ):
        return {}
    _metadata, content = store.read_artifact(campaign.id, str(artifact["id"]))
    try:
        payload = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    from .differential_intelligence import differential_signal_metadata

    differential = payload.get("differential")
    return differential_signal_metadata(differential if isinstance(differential, dict) else None)


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
    artifact_metadata = {
        "artifact_id": artifact["id"],
        "artifact_sha256": artifact.get("sha256"),
        "artifact_kind": artifact.get("kind"),
        "artifact_size_bytes": artifact.get("size_bytes"),
        "artifact_media_type": artifact.get("media_type"),
    }
    artifact_metadata = {
        key: value for key, value in artifact_metadata.items() if value is not None
    }
    differential_metadata = _differential_artifact_metadata(
        store,
        campaign,
        artifact,
        source=source,
        kind=kind,
    )
    observation = Observation(
        id=f"{kind}:{artifact['id']}",
        kind=kind,
        value=value or artifact["id"],
        source=source,
        parent_ids=parent_ids,
        metadata={**(metadata or {}), **differential_metadata, **artifact_metadata},
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
