from __future__ import annotations

from ipaddress import ip_address
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, HttpUrl, model_validator

router = APIRouter()


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
