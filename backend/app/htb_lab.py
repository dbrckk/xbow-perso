from __future__ import annotations

from ipaddress import ip_address
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator

router = APIRouter()


_ALLOWED_TECHNIQUE_CHARS = set("abcdefghijklmnopqrstuvwxyz0123456789-_.:")


def _normalize_technique(value: str) -> str:
    normalized = str(value or "").strip().lower().replace(" ", "-")
    if not normalized or len(normalized) > 80:
        raise ValueError("technique labels must be between 1 and 80 characters")
    if any(ch not in _ALLOWED_TECHNIQUE_CHARS for ch in normalized):
        raise ValueError("technique labels contain unsupported characters")
    return normalized


class HtbLabCampaignInput(BaseModel):
    target_url: HttpUrl
    authorized_lab: bool
    name: str = Field(default="Hack The Box Lab", min_length=2, max_length=120)

    @model_validator(mode="after")
    def validate_authorized_lab_target(self):
        if self.authorized_lab is not True:
            raise ValueError("authorized_lab must be explicitly true")
        parsed = urlparse(str(self.target_url))
        host = (parsed.hostname or "").lower().rstrip(".")
        if not host:
            raise ValueError("target_url has no hostname")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("userinfo, query strings and fragments are forbidden")

        allowed = False
        try:
            address = ip_address(host)
        except ValueError:
            allowed = host.endswith(".htb") and host.count(".") >= 1
        else:
            allowed = address.is_private and not address.is_multicast

        if not allowed:
            raise ValueError(
                "HTB training targets must be an exact private IP or a .htb lab hostname"
            )
        return self


@router.post("/api/labs/htb/campaigns")
def create_htb_lab_campaign(payload: HtbLabCampaignInput):
    from .campaign_audit import append_campaign_event
    from .main import Campaign, CampaignState, ProgramRules, TargetInput, save_campaign, utcnow

    parsed = urlparse(str(payload.target_url))
    host = (parsed.hostname or "").lower().rstrip(".")
    if not host:
        raise HTTPException(status_code=400, detail="HTB lab target has no hostname")

    target = TargetInput(
        name=payload.name,
        primary_url=payload.target_url,
        rules=ProgramRules(
            authorization_reference=f"hackthebox-lab:{host}",
            allowed_targets=[host],
            denied_targets=[],
            max_requests_per_second=1.0,
            destructive_testing=False,
            denial_of_service=False,
            social_engineering=False,
            credential_attacks=False,
            automated_scanning=True,
            notes="Hack The Box training lab; exact target only; no scope expansion.",
        ),
    )
    campaign = Campaign(target=target, state=CampaignState.ready)
    append_campaign_event(
        campaign.events,
        {
            "type": "htb_lab_bound",
            "provider": "hackthebox",
            "training_only": True,
            "exact_scope": [host],
            "at": utcnow(),
        },
    )
    save_campaign(campaign, expected_version=0)
    return {
        "campaign_id": campaign.id,
        "state": campaign.state,
        "provider": "hackthebox",
        "training_only": True,
        "target": str(campaign.target.primary_url),
        "allowed_targets": list(campaign.target.rules.allowed_targets),
        "max_requests_per_second": campaign.target.rules.max_requests_per_second,
        "destructive_testing": campaign.target.rules.destructive_testing,
        "denial_of_service": campaign.target.rules.denial_of_service,
        "social_engineering": campaign.target.rules.social_engineering,
        "credential_attacks": campaign.target.rules.credential_attacks,
        "automatic_scope_expansion": False,
    }


class HtbLabOutcomeInput(BaseModel):
    solved: bool
    successful_techniques: list[str] = Field(default_factory=list, max_length=20)
    missed_techniques: list[str] = Field(default_factory=list, max_length=20)
    notes: str = Field(default="", max_length=1000)

    @field_validator("successful_techniques", "missed_techniques")
    @classmethod
    def validate_techniques(cls, value: list[str]) -> list[str]:
        normalized = [_normalize_technique(item) for item in value]
        return list(dict.fromkeys(normalized))

    @model_validator(mode="after")
    def validate_overlap(self):
        overlap = set(self.successful_techniques) & set(self.missed_techniques)
        if overlap:
            raise ValueError(
                "a technique cannot be both successful and missed: "
                + ", ".join(sorted(overlap))
            )
        return self


def _assert_htb_campaign(campaign) -> None:
    if not is_htb_training_campaign(campaign):
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Campaign is not an HTB training campaign",
                "reason": "not_htb_training_campaign",
            },
        )


@router.post("/api/labs/htb/campaigns/{campaign_id}/outcome")
def record_htb_lab_outcome(campaign_id: str, payload: HtbLabOutcomeInput):
    """Record bounded operator feedback as reusable training evidence."""
    import hashlib

    from .campaign_audit import append_campaign_event
    from .main import assert_campaign_record, save_campaign, storage, utcnow
    from .observation_graph import Observation

    campaign, version = assert_campaign_record(campaign_id)
    _assert_htb_campaign(campaign)

    successful = list(payload.successful_techniques)
    missed = list(payload.missed_techniques)
    timestamp = utcnow()
    digest_source = "|".join(
        [campaign_id, str(payload.solved), *successful, "--", *missed]
    )
    digest = hashlib.sha256(digest_source.encode("utf-8")).hexdigest()[:20]

    append_campaign_event(
        campaign.events,
        {
            "type": "htb_training_outcome",
            "solved": bool(payload.solved),
            "successful_technique_count": len(successful),
            "missed_technique_count": len(missed),
            "notes_present": bool(payload.notes.strip()),
            "at": timestamp,
        },
    )
    save_campaign(campaign, expected_version=version)

    store = storage()
    for technique in successful:
        store.put_observation(
            campaign.id,
            Observation(
                id=f"htb-learning:{digest}:success:{technique}",
                kind="evidence",
                value=technique,
                source="htb-training-feedback",
                metadata={
                    "memory_type": "htb_training_feedback",
                    "technique": technique,
                    "outcome": "success",
                    "training_only": True,
                },
            ).to_dict(),
        )
    for technique in missed:
        store.put_observation(
            campaign.id,
            Observation(
                id=f"htb-learning:{digest}:failure:{technique}",
                kind="evidence",
                value=technique,
                source="htb-training-feedback",
                metadata={
                    "memory_type": "htb_training_feedback",
                    "technique": technique,
                    "outcome": "failure",
                    "training_only": True,
                },
            ).to_dict(),
        )

    return {
        "campaign_id": campaign.id,
        "provider": "hackthebox",
        "training_only": True,
        "solved": bool(payload.solved),
        "successful_techniques": successful,
        "missed_techniques": missed,
        "learning_observations_written": len(successful) + len(missed),
        "notes_stored": False,
        "contains_exploit_payloads": False,
    }


def is_htb_training_campaign(campaign) -> bool:
    events = (
        list(getattr(campaign, "events", ()) or ())
        if not isinstance(campaign, dict)
        else list(campaign.get("events") or [])
    )
    return any(
        isinstance(event, dict)
        and event.get("type") == "htb_lab_bound"
        and event.get("training_only") is True
        for event in events
    )


def collect_htb_cross_lab_learning(store, *, limit_campaigns: int = 200):
    """Aggregate bounded HTB training evidence across prior authorized labs only."""
    from .learning_memory import build_learning_memory, summarize_worker_outcomes
    from .observation_graph import Observation, ObservationGraph

    if not 1 <= limit_campaigns <= 1000:
        raise ValueError("HTB campaign learning limit must be between 1 and 1000")

    graph = ObservationGraph()
    worker_events: list[dict] = []
    campaign_count = 0
    feedback_observations = 0

    for campaign in store.list_campaigns(limit=limit_campaigns):
        if not is_htb_training_campaign(campaign):
            continue
        campaign_id = str(campaign.get("id") or "")
        if not campaign_id:
            continue
        campaign_count += 1

        for item in store.list_observations(campaign_id):
            metadata = dict(item.get("metadata") or {})
            if (
                item.get("kind") != "evidence"
                or metadata.get("memory_type") != "htb_training_feedback"
                or metadata.get("training_only") is not True
            ):
                continue
            graph.add(
                Observation(
                    id=f"{campaign_id}:{item['id']}",
                    kind="evidence",
                    value=str(item.get("value") or ""),
                    source=f"{item.get('source') or 'htb-training'}:{campaign_id}",
                    metadata=metadata,
                )
            )
            feedback_observations += 1

        worker_events.extend(
            event
            for event in list(campaign.get("events") or [])
            if isinstance(event, dict) and event.get("type") == "worker_outcome"
        )

    memories = build_learning_memory(graph, limit=100)
    worker_outcomes = summarize_worker_outcomes(worker_events, recent_limit=50)
    return memories, worker_outcomes, {
        "campaign_count": campaign_count,
        "feedback_observations": feedback_observations,
        "training_only": True,
        "scope_expansion": False,
    }


def build_htb_cross_lab_learning_summary(store, *, limit_campaigns: int = 200):
    memories, worker_outcomes, metadata = collect_htb_cross_lab_learning(
        store,
        limit_campaigns=limit_campaigns,
    )
    return {
        **metadata,
        "techniques": [item.to_dict() for item in memories],
        "worker_outcomes": worker_outcomes,
        "read_only": True,
        "contains_exploit_payloads": False,
    }


@router.get("/api/labs/htb/learning")
def htb_global_learning_summary(limit_campaigns: int = 200):
    from .main import storage

    return build_htb_cross_lab_learning_summary(
        storage(),
        limit_campaigns=limit_campaigns,
    )


@router.get("/api/labs/htb/campaigns/{campaign_id}/learning")
def htb_lab_learning_summary(campaign_id: str):
    from .learning_memory import build_learning_memory, summarize_worker_outcomes
    from .main import assert_campaign_exists, storage
    from .observation_graph import load_observation_graph

    campaign = assert_campaign_exists(campaign_id)
    _assert_htb_campaign(campaign)
    graph = load_observation_graph(storage(), campaign.id)
    memories = build_learning_memory(graph, limit=50)
    outcomes = [
        event
        for event in list(campaign.events or [])
        if isinstance(event, dict) and event.get("type") == "htb_training_outcome"
    ]
    return {
        "campaign_id": campaign.id,
        "provider": "hackthebox",
        "training_only": True,
        "outcomes": outcomes[-20:],
        "techniques": [item.to_dict() for item in memories],
        "worker_outcomes": summarize_worker_outcomes(campaign.events),
        "read_only": True,
        "scope_expansion": False,
    }
