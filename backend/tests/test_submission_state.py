from app.main import Campaign, Finding, ProgramRules, TargetInput
from app.report_approval import approval_event, revocation_event
from app.submission_state import assert_submission_allowed, submission_event, submission_status


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
            status="confirmed",
            discovered_by="scanner",
            validated_by="independent-validator",
        )
    )
    return campaign


def _artifact() -> dict:
    return {"id": "report-1", "kind": "report", "sha256": "a" * 64}


def test_report_starts_as_draft():
    status = submission_status(_campaign(), _artifact())
    assert status.state == "draft"
    assert status.approved is False


def test_current_human_approval_unlocks_submission():
    campaign = _campaign()
    artifact = _artifact()
    campaign.events.append(approval_event(campaign, artifact, "reviewer", "2026-09-10T08:00:00Z"))

    status = assert_submission_allowed(campaign, artifact)

    assert status.state == "approved"
    assert status.reviewer == "reviewer"


def test_submission_is_recorded_only_after_approval():
    campaign = _campaign()
    artifact = _artifact()
    campaign.events.append(approval_event(campaign, artifact, "reviewer", "2026-09-10T08:00:00Z"))
    campaign.events.append(submission_event(artifact["id"], "operator", "generic", "2026-09-10T08:05:00Z"))

    status = submission_status(campaign, artifact)

    assert status.state == "submitted"
    assert status.submitted_by == "operator"
    assert status.platform == "generic"


def test_revocation_reblocks_previously_submitted_report():
    campaign = _campaign()
    artifact = _artifact()
    campaign.events.append(approval_event(campaign, artifact, "reviewer", "2026-09-10T08:00:00Z"))
    campaign.events.append(submission_event(artifact["id"], "operator", "generic", "2026-09-10T08:05:00Z"))
    campaign.events.append(revocation_event(artifact["id"], "reviewer", "2026-09-10T08:06:00Z"))

    status = submission_status(campaign, artifact)

    assert status.state == "review_required"
    assert status.approved is False
    assert status.submitted_at is None


def test_campaign_change_makes_approval_stale_and_reblocks_submission():
    campaign = _campaign()
    artifact = _artifact()
    campaign.events.append(approval_event(campaign, artifact, "reviewer", "2026-09-10T08:00:00Z"))
    campaign.findings[0].impact = "changed after approval"

    status = submission_status(campaign, artifact)

    assert status.state == "review_required"
    assert status.stale is True


def test_unapproved_submission_attempt_is_rejected():
    try:
        assert_submission_allowed(_campaign(), _artifact())
    except ValueError as exc:
        assert "current human approval" in str(exc)
    else:
        raise AssertionError("unapproved reports must not be submission-ready")


def test_submission_event_requires_actor_and_platform():
    for actor, platform in (("", "generic"), ("operator", "")):
        try:
            submission_event("report-1", actor, platform, "2026-09-10T08:05:00Z")
        except ValueError:
            pass
        else:
            raise AssertionError("invalid submission metadata must be rejected")
