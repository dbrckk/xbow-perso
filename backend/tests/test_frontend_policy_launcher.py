from pathlib import Path

from app.main import app


ROOT = Path(__file__).resolve().parents[2]


def test_hackerone_single_mutation_launch_route_exists():
    schema = app.openapi()

    assert "/api/imports/hackerone/campaigns/launch" in schema["paths"]
    assert "post" in schema["paths"]["/api/imports/hackerone/campaigns/launch"]


def test_frontend_requires_authorization_and_scope_review_before_launch():
    html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    launcher = (ROOT / "frontend" / "hackerone.js").read_text(encoding="utf-8")

    required_ids = (
        "h1Name",
        "h1Url",
        "h1ScopeJson",
        "h1ScopeFile",
        "h1Auth",
        "h1PolicyVersion",
        "h1ReviewedAt",
        "h1ReviewedBy",
        "h1SafeHarbor",
        "h1Automation",
        "h1Rps",
        "h1TestAccountRequired",
        "h1TestAccountConstraints",
        "h1AdditionalRestrictions",
        "h1Notes",
        "h1Preview",
        "h1Confirm",
        "h1Launch",
        "h1PreviewCard",
        "h1AllowedPreview",
        "h1DeniedPreview",
    )
    for element_id in required_ids:
        assert f'id="{element_id}"' in html

    assert '<script src="/hackerone.js" defer></script>' in html
    assert "api('/imports/hackerone/rules-preview'" in launcher
    assert "api('/imports/hackerone/campaigns/launch'" in launcher
    assert '<button id="h1Launch" disabled>' in html
    assert "approvedPreview" in launcher
    assert "invalidatePreview" in launcher



def test_frontend_exposes_remote_hackerone_control_center_contract():
    html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    launcher = (ROOT / "frontend" / "hackerone.js").read_text(encoding="utf-8")

    required_ids = (
        "h1ConnectionState",
        "h1ProgramSearch",
        "h1ProgramSelect",
        "h1LoadProgram",
        "h1ProgramMeta",
        "h1RemoteFingerprint",
        "h1ScopeTable",
        "h1ScopeExclusions",
    )
    for element_id in required_ids:
        assert f'id="{element_id}"' in html

    assert "api('/imports/hackerone/connection'" in launcher
    assert "api('/imports/hackerone/programs'" in launcher
    assert "/snapshot" in launcher
    assert "remote_handle" in launcher
    assert "remote_snapshot_sha256" in launcher
    assert "clearRemoteBinding" in launcher
    assert "renderRemoteScope" in launcher



def test_frontend_exposes_hackerone_live_run_monitor_contract():
    html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    launcher = (ROOT / "frontend" / "hackerone.js").read_text(encoding="utf-8")

    required_ids = (
        "h1RunPanel",
        "h1RunState",
        "h1RunJobs",
        "h1RunFindings",
        "h1RunArtifacts",
        "h1RunUpdated",
    )
    for element_id in required_ids:
        assert f'id="{element_id}"' in html

    assert "startRunMonitor" in launcher
    assert "stopRunMonitor" in launcher
    assert "refreshRunMonitor" in launcher
    assert "api('/campaigns/'+encodeURIComponent(campaignId))" in launcher
    assert "api('/campaigns/'+encodeURIComponent(campaignId)+'/control-status')" in launcher
    assert "api('/campaigns/'+encodeURIComponent(campaignId)+'/artifacts')" in launcher
    assert "setInterval" in launcher


def test_frontend_exposes_hackerone_finding_review_and_report_draft_contract():
    html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    launcher = (ROOT / "frontend" / "hackerone.js").read_text(encoding="utf-8")

    for element_id in (
        "h1RunFindingList",
        "h1ReportDraft",
        "h1ReportDownload",
        "h1ReportApprove",
        "h1ReportSubmit",
        "h1ReportRevoke",
        "h1ReportApprovalStatus",
        "h1ReportStatus",
    ):
        assert f'id="{element_id}"' in html

    assert "renderHackerOneFindings" in launcher
    assert "queueHackerOneReport" in launcher
    assert "downloadHackerOneReport" in launcher
    assert "approveHackerOneReport" in launcher
    assert "submitHackerOneReport" in launcher
    assert "revokeHackerOneReportApproval" in launcher
    assert "report-readiness" in launcher
    assert "reports?platform=hackerone" in launcher
    assert "'/artifacts/'+encodeURIComponent(artifactId)" in launcher
    assert "'/approval'" in launcher
    assert "'/approval/revoke'" in launcher
    assert "'/submit-to-hackerone'" in launcher
    assert "confirm_submission:true" in launcher
    assert "window.confirm" in launcher
    assert "URL.createObjectURL" in launcher
    assert "x-content-sha256" in launcher
    assert "headers.authorization='Bearer '+token" in launcher
    assert "reportApproval" in launcher
    assert "Approbation obsolète" in launcher
    assert "submission_ready" in launcher
    assert "humaine" in html.lower()


def test_frontend_exposes_hackerone_human_review_controls():
    launcher = (ROOT / "frontend" / "hackerone.js").read_text(encoding="utf-8")

    assert "buildFindingReviewEditor" in launcher
    assert "saveFindingReviewMetadata" in launcher
    assert "resolveHackerOneFinding" in launcher
    assert "/review-metadata" in launcher
    assert "/validate?confirmed=" in launcher
    assert "Sauvegarder la revue" in launcher
    assert "Confirmer le finding" in launcher
    assert "Rejeter le finding" in launcher
    assert "CWE" in launcher
    assert "CVSS" in launcher
    assert "ne confirme jamais automatiquement" in launcher
