import pytest

from app.job_provenance import (
    JobProvenanceError,
    attach_job_provenance,
    build_job_provenance,
    policy_snapshot_fingerprint,
    require_job_provenance,
    verify_job_provenance,
)
from app.main import Campaign, ProgramRules, TargetInput


def _campaign(*, allowed_targets=None, rps=2.0):
    return Campaign(
        id="campaign-1",
        target=TargetInput(
            name="fixture",
            primary_url="https://example.test",
            rules=ProgramRules(
                authorization_reference="authorization-1",
                allowed_targets=allowed_targets or ["example.test"],
                denied_targets=["admin.example.test"],
                max_requests_per_second=rps,
            ),
        ),
    )


def test_policy_fingerprint_is_deterministic_and_order_stable():
    first = _campaign(allowed_targets=["example.test", "*.example.test"])
    second = _campaign(allowed_targets=["*.example.test", "example.test"])

    assert policy_snapshot_fingerprint(first) == policy_snapshot_fingerprint(second)


def test_policy_fingerprint_changes_when_governance_changes():
    base = _campaign(rps=2.0)
    changed = _campaign(rps=1.0)

    assert policy_snapshot_fingerprint(base) != policy_snapshot_fingerprint(changed)


def test_attached_provenance_verifies_against_current_campaign():
    campaign = _campaign()
    payload = attach_job_provenance(
        {"campaign_id": campaign.id, "target": str(campaign.target.primary_url)},
        campaign,
        job_kind="strix_scan",
        action="automated_scan",
    )
    job = {
        "campaign_id": campaign.id,
        "kind": "strix_scan",
        "payload": payload,
    }

    verification = verify_job_provenance(job, campaign)

    assert verification["valid"] is True
    assert verification["reasons"] == []
    assert payload["_provenance"]["schema"] == "job-provenance-v1"


def test_stale_policy_fingerprint_fails_closed():
    campaign = _campaign(rps=2.0)
    payload = attach_job_provenance(
        {"campaign_id": campaign.id},
        campaign,
        job_kind="strix_scan",
        action="automated_scan",
    )
    stale_job = {
        "campaign_id": campaign.id,
        "kind": "strix_scan",
        "payload": payload,
    }
    campaign.target.rules.max_requests_per_second = 1.0

    verification = verify_job_provenance(stale_job, campaign)

    assert verification["valid"] is False
    assert "policy_fingerprint_mismatch" in verification["reasons"]
    assert "request_rate_limit_mismatch" in verification["reasons"]
    with pytest.raises(JobProvenanceError, match="job provenance rejected"):
        require_job_provenance(stale_job, campaign)


def test_wrong_job_kind_or_campaign_is_rejected():
    campaign = _campaign()
    provenance = build_job_provenance(
        campaign,
        job_kind="strix_scan",
        action="automated_scan",
    )
    job = {
        "campaign_id": campaign.id,
        "kind": "nuclei_scan",
        "payload": {"_provenance": provenance},
    }

    verification = verify_job_provenance(job, campaign)

    assert verification["valid"] is False
    assert "job_kind_mismatch" in verification["reasons"]


def test_missing_provenance_is_rejected_by_strict_verifier():
    campaign = _campaign()
    job = {
        "campaign_id": campaign.id,
        "kind": "strix_scan",
        "payload": {},
    }

    verification = verify_job_provenance(job, campaign)

    assert verification["valid"] is False
    assert verification["reasons"] == ["provenance_missing"]
    with pytest.raises(JobProvenanceError, match="provenance_missing"):
        require_job_provenance(job, campaign)


def test_duplicate_provenance_injection_is_rejected():
    campaign = _campaign()
    with pytest.raises(JobProvenanceError, match="already contains provenance"):
        attach_job_provenance(
            {"_provenance": {}},
            campaign,
            job_kind="strix_scan",
            action="automated_scan",
        )
