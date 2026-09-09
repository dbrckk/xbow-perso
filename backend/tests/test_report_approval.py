from app.main import Campaign, Finding, ProgramRules, TargetInput
from app.report_approval import approval_event, approval_status, revocation_event


def _campaign() -> Campaign:
    campaign = Campaign(
        id="c1",
        target=TargetInput(
            name="fixture",
            primary_url="https://example.test",
            rules=ProgramRules(
                authorization_reference="explicit-test-authorization",
                allowed_targets=["example.test"],
            ),
        ),
    )
    campaign.findings.append(
        Finding(
            id="f1",
            title="confirmed fixture",
            severity="medium",
            asset="https://example.test",
            summary="bounded fixture",
            impact="fixture impact",
            remediation="fixture remediation",
            status="confirmed",
            discovered_by="scanner",
            validated_by="independent-validator",
        )
    )
    return campaign


def _artifact() -> dict:
    return {
        "id": "report-1",
        "kind": "report",
        "sha256": "a" * 64,
    }


def test_exact_report_and_campaign_state_can_be_approved():
    campaign = _campaign()
    artifact = _artifact()
    campaign.events.append(approval_event(campaign, artifact, "human-reviewer", "2026-09-09T21:00:00Z"))

    status = approval_status(campaign, artifact)

    assert status.approved is True
    assert status.stale is False
    assert status.reviewer == "human-reviewer"


def test_campaign_change_invalidates_existing_approval():
    campaign = _campaign()
    artifact = _artifact()
    campaign.events.append(approval_event(campaign, artifact, "human-reviewer", "2026-09-09T21:00:00Z"))
    campaign.findings[0].impact = "changed after approval"

    status = approval_status(campaign, artifact)

    assert status.approved is False
    assert status.stale is True


def test_report_hash_change_invalidates_existing_approval():
    campaign = _campaign()
    artifact = _artifact()
    campaign.events.append(approval_event(campaign, artifact, "human-reviewer", "2026-09-09T21:00:00Z"))
    artifact = {**artifact, "sha256": "b" * 64}

    status = approval_status(campaign, artifact)

    assert status.approved is False
    assert status.stale is True


def test_revocation_disables_approval():
    campaign = _campaign()
    artifact = _artifact()
    campaign.events.append(approval_event(campaign, artifact, "human-reviewer", "2026-09-09T21:00:00Z"))
    campaign.events.append(revocation_event(artifact["id"], "human-reviewer", "2026-09-09T21:05:00Z"))

    status = approval_status(campaign, artifact)

    assert status.approved is False
    assert status.stale is False


def test_non_report_artifact_cannot_be_approved():
    campaign = _campaign()
    artifact = {**_artifact(), "kind": "http_evidence"}

    try:
        approval_event(campaign, artifact, "human-reviewer", "2026-09-09T21:00:00Z")
    except ValueError as exc:
        assert "only report artifacts" in str(exc)
    else:
        raise AssertionError("approval must reject non-report artifacts")
