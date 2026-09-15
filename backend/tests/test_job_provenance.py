import pytest

from app import main
from app.job_provenance import (
    GOVERNED_JOB_KINDS,
    JobProvenanceError,
    attach_job_provenance,
    build_job_provenance,
    policy_snapshot_fingerprint,
    provenance_required_for_job_kind,
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


def test_wrong_job_kind_is_rejected():
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


def test_governed_job_registry_is_explicit_and_closed():
    assert GOVERNED_JOB_KINDS == frozenset(
        {
            "strix_scan",
            "nuclei_scan",
            "recon_task",
            "browser_flow",
            "independent_validation",
            "report",
        }
    )
    assert all(provenance_required_for_job_kind(kind) for kind in GOVERNED_JOB_KINDS)
    assert provenance_required_for_job_kind("maintenance") is False


def test_job_provenance_status_route_is_registered():
    assert "/api/jobs/{job_id}/provenance" in main.app.openapi()["paths"]


def test_job_provenance_status_is_redacted(monkeypatch):
    campaign = _campaign()
    payload = attach_job_provenance(
        {
            "campaign_id": campaign.id,
            "target": str(campaign.target.primary_url),
            "secret": "secret-value",
        },
        campaign,
        job_kind="strix_scan",
        action="automated_scan",
    )
    job = {
        "id": "job-1",
        "campaign_id": campaign.id,
        "kind": "strix_scan",
        "payload": payload,
    }

    class FakeQueue:
        def get(self, job_id):
            return job if job_id == job["id"] else None

    monkeypatch.setattr(main, "queue", lambda: FakeQueue())
    monkeypatch.setattr(main, "assert_campaign_exists", lambda campaign_id: campaign)

    result = main.get_job_provenance_status("job-1")

    assert result["job_id"] == "job-1"
    assert result["campaign_id"] == campaign.id
    assert result["job_kind"] == "strix_scan"
    assert result["provenance"]["valid"] is True
    assert result["read_only"] is True
    assert result["payload_exposed"] is False
    assert result["fail_closed_capable"] is True
    assert set(result) == {
        "job_id",
        "campaign_id",
        "job_kind",
        "provenance",
        "read_only",
        "payload_exposed",
        "fail_closed_capable",
    }
    rendered = str(result)
    assert "authorization-1" not in rendered
    assert "https://example.test" not in rendered
    assert "secret-value" not in rendered
    assert "_provenance" not in rendered


def test_capabilities_advertise_policy_bound_job_provenance():
    assert main.system_capabilities()["campaign_control"]["policy_bound_job_provenance"] is True
