from app.main import Campaign, Finding, ProgramRules, TargetInput
from app.report import render_markdown


def _campaign() -> Campaign:
    target = TargetInput(
        name="Local demo",
        primary_url="https://demo.local",
        rules=ProgramRules(
            authorization_reference="local-test",
            allowed_targets=["demo.local"],
            denied_targets=[],
        ),
    )
    campaign = Campaign(target=target)
    campaign.findings.append(
        Finding(
            title="Example issue",
            severity="medium",
            asset="https://demo.local",
            endpoint="/example",
            summary="Synthetic test finding.",
            impact="Synthetic impact.",
            remediation="Synthetic remediation.",
            reproduction_steps=["Open the local fixture."],
            status="confirmed",
            discovered_by="fixture",
            validated_by="independent-fixture-validator",
            cwe="CWE-200",
            cvss=5.3,
        )
    )
    return campaign


def test_hackerone_report_contains_submission_sections():
    report = render_markdown(_campaign(), platform="hackerone")
    assert "Submission format:** HackerOne" in report
    assert "## Submission candidates" in report
    assert "#### Steps to reproduce" in report
    assert "#### Security impact" in report
    assert "## Submission checklist" in report
    assert "Example issue" in report


def test_report_excludes_unconfirmed_findings():
    campaign = _campaign()
    campaign.findings[0].status = "validation_required"
    report = render_markdown(campaign, platform="bugcrowd")
    assert "Submission format:** Bugcrowd" in report
    assert "No independently validated vulnerabilities" in report
    assert "Example issue" not in report
