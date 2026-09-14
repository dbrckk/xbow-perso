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



def test_report_marks_high_quality_confirmed_finding_ready_for_review():
    campaign = _campaign()
    finding_id = str(campaign.findings[0].id)

    report = render_markdown(
        campaign,
        evidence_quality={
            finding_id: {
                "grade": "high",
                "score": 1.0,
            }
        },
    )

    assert "1 of 1 confirmed finding(s) currently meet the high-quality evidence threshold." in report
    assert "**Evidence quality:** HIGH (100%)" in report
    assert "**Submission readiness:** READY FOR HUMAN SUBMISSION REVIEW" in report


def test_report_holds_confirmed_finding_when_evidence_quality_is_not_high():
    campaign = _campaign()
    finding_id = str(campaign.findings[0].id)

    report = render_markdown(
        campaign,
        evidence_quality={
            finding_id: {
                "grade": "medium",
                "score": 0.7,
            }
        },
    )

    assert "0 of 1 confirmed finding(s) currently meet the high-quality evidence threshold." in report
    assert "**Evidence quality:** MEDIUM (70%)" in report
    assert "**Submission readiness:** HOLD — strengthen evidence before submission" in report



def test_report_embeds_governance_audit_manifest():
    report = render_markdown(
        _campaign(),
        governance_manifest={
            "schema": "reporting-governance-v1",
            "governance_fingerprint": "a" * 64,
            "provenance_fingerprint": "b" * 64,
            "verification_valid": True,
            "findings": 1,
            "submission_ready": 1,
        },
    )

    assert "## Governance & audit manifest" in report
    assert "**Schema:** reporting-governance-v1" in report
    assert f"**Reporting governance fingerprint:** `{'a' * 64}`" in report
    assert f"**Provenance fingerprint:** `{'b' * 64}`" in report
    assert "**Governance verification:** VALID" in report
    assert "**Findings represented:** 1" in report
    assert "**Submission-ready findings:** 1" in report
