from app.main import Campaign, CampaignState, Finding, ProgramRules, TargetInput
from app.worker_service import _state_after_scan


def _campaign(findings):
    return Campaign(
        id="c1",
        target=TargetInput(
            name="fixture",
            primary_url="https://example.test",
            rules=ProgramRules(
                authorization_reference="test-authorization",
                allowed_targets=["example.test"],
            ),
        ),
        findings=findings,
    )


def _finding(status):
    return Finding(
        id=f"f-{status}",
        title="fixture",
        severity="low",
        asset="https://example.test",
        summary="fixture",
        status=status,
        discovered_by="scanner",
    )


def test_post_scan_state_stays_validating_for_known_unresolved_finding():
    campaign = _campaign([_finding("validation_required")])

    assert _state_after_scan(campaign) == CampaignState.validating


def test_post_scan_state_completes_only_when_all_findings_are_resolved():
    campaign = _campaign([_finding("confirmed"), _finding("rejected")])

    assert _state_after_scan(campaign) == CampaignState.completed


def test_post_scan_state_completes_when_scan_has_no_findings():
    assert _state_after_scan(_campaign([])) == CampaignState.completed
