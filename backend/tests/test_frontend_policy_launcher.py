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
        "h1ReportRemoteStatus",
        "h1NeedsInfoPanel",
        "h1NeedsInfoRequest",
        "h1NeedsInfoCopy",
        "h1NeedsInfoDraft",
        "h1ActivitySummary",
        "h1ReportTimeline",
        "h1ReportStatus",
    ):
        assert f'id="{element_id}"' in html

    assert "renderHackerOneFindings" in launcher
    assert "queueHackerOneReport" in launcher
    assert "downloadHackerOneReport" in launcher
    assert "approveHackerOneReport" in launcher
    assert "submitHackerOneReport" in launcher
    assert "renderHackerOneRemoteReportStatus" in launcher
    assert "renderHackerOneNeedsInfo" in launcher
    assert "copyHackerOneNeedsInfoDraft" in launcher
    assert "renderHackerOneReportTimeline" in launcher
    assert "hackerOneActivityLabel" in launcher
    assert "hackerone_report_status_synced" in launcher
    assert "hackerone_public_activity_observed" in launcher
    assert "activity-bounty-awarded" in launcher
    assert "activity-bug-duplicate" in launcher
    assert "activity-bug-informative" in launcher
    assert "activity-bug-resolved" in launcher
    assert "revokeHackerOneReportApproval" in launcher
    assert "report-readiness" in launcher
    assert "reports?platform=hackerone" in launcher
    assert "'/artifacts/'+encodeURIComponent(artifactId)" in launcher
    assert "'/approval'" in launcher
    assert "'/approval/revoke'" in launcher
    assert "'/submit-to-hackerone'" in launcher
    assert "'/hackerone-status'" in launcher
    assert "'/hackerone-needs-info-draft'" in launcher
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


def test_frontend_needs_info_flow_has_no_remote_send_action():
    launcher = (ROOT / "frontend" / "hackerone.js").read_text(encoding="utf-8")

    assert "navigator.clipboard.writeText" in launcher
    assert "hackerone-needs-info-draft" in launcher
    assert "needs_more_info" in launcher
    assert "send_supported" not in launcher
    assert "post-needs-info" not in launcher
    assert "reply-to-hackerone" not in launcher


def test_frontend_exposes_hackerone_attention_center_contract():
    html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    launcher = (ROOT / "frontend" / "hackerone.js").read_text(encoding="utf-8")

    for element_id in (
        "h1AttentionPanel",
        "h1AttentionRefresh",
        "h1AttentionAction",
        "h1AttentionActive",
        "h1AttentionBounty",
        "h1AttentionResolved",
        "h1AttentionDuplicate",
        "h1AttentionInformative",
        "h1AttentionList",
        "h1AttentionUpdated",
    ):
        assert f'id="{element_id}"' in html

    assert "refreshHackerOneAttention" in launcher
    assert "renderHackerOneAttention" in launcher
    assert "focusHackerOneAttentionCampaign" in launcher
    assert "startHackerOneAttentionMonitor" in launcher
    assert "'/hackerone/attention?limit=200'" in launcher
    assert "setInterval(()=>void refreshHackerOneAttention(),15000)" in launcher
    assert "activateCampaign(campaign)" in launcher


def test_frontend_tracks_hackerone_attention_seen_state_locally():
    html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    launcher = (ROOT / "frontend" / "hackerone.js").read_text(encoding="utf-8")

    for element_id in (
        "h1AttentionUnread",
        "h1AttentionMarkAll",
    ):
        assert f'id="{element_id}"' in html

    assert "ATTENTION_SEEN_STORAGE_KEY" in launcher
    assert "xbow:hackerone:attention-seen:v1" in launcher
    assert "loadAttentionSeen" in launcher
    assert "saveAttentionSeen" in launcher
    assert "ensureAttentionBaseline" in launcher
    assert "isAttentionUnread" in launcher
    assert "markHackerOneAttentionSeen" in launcher
    assert "markAllHackerOneAttentionSeen" in launcher
    assert "notification_cursor" in launcher
    assert "notification_kind" in launcher
    assert "localStorage.getItem" in launcher
    assert "localStorage.setItem" in launcher
    assert "Marquer vu" in launcher
    assert "Tout marquer vu" in html


def test_frontend_filters_and_sorts_hackerone_attention_center():
    html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    launcher = (ROOT / "frontend" / "hackerone.js").read_text(encoding="utf-8")

    for element_id in (
        "h1AttentionSearch",
        "h1AttentionReadFilter",
        "h1AttentionBucketFilter",
        "h1AttentionProgramFilter",
        "h1AttentionStateFilter",
        "h1AttentionBountyFilter",
        "h1AttentionRecentFilter",
        "h1AttentionSort",
        "h1AttentionResetFilters",
        "h1AttentionResults",
    ):
        assert f'id="{element_id}"' in html

    assert "filterAndSortHackerOneAttention" in launcher
    assert "syncHackerOneAttentionFilterOptions" in launcher
    assert "hackerOneAttentionMatchesRecent" in launcher
    assert "resetHackerOneAttentionFilters" in launcher
    assert "Date.now()" in launcher
    assert "24h" in launcher
    assert "7d" in launcher
    assert "30d" in launcher
    assert "priority" in launcher
    assert "newest" in launcher
    assert "oldest" in launcher
    assert "program" in launcher
    assert "state" in launcher
    assert "Aucun report ne correspond aux filtres." in launcher


def test_frontend_persists_hackerone_attention_filters_and_saved_views():
    html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    launcher = (ROOT / "frontend" / "hackerone.js").read_text(encoding="utf-8")

    assert 'id="h1AttentionViewState"' in html
    for view in ("action", "today", "bounty", "nmi", "unread"):
        assert f'data-h1-attention-view="{view}"' in html

    assert 'value="today"' in html
    assert "ATTENTION_FILTER_STORAGE_KEY" in launcher
    assert "xbow:hackerone:attention-filters:v1" in launcher
    assert "currentHackerOneAttentionFilters" in launcher
    assert "loadHackerOneAttentionFilters" in launcher
    assert "saveHackerOneAttentionFilters" in launcher
    assert "applyHackerOneAttentionFilters" in launcher
    assert "restoreHackerOneAttentionFilters" in launcher
    assert "ATTENTION_SAVED_VIEWS" in launcher
    assert "applyHackerOneAttentionSavedView" in launcher
    assert "renderHackerOneAttentionViewState" in launcher
    assert "Vue personnalisée" in html
    assert "À traiter" in html
    assert "Nouveaux aujourd’hui" in html
    assert "Avec bounty" in html
    assert ">NMI<" in html
    assert ">Non lus<" in html


def test_frontend_bulk_hackerone_attention_actions_and_sanitized_export():
    html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    launcher = (ROOT / "frontend" / "hackerone.js").read_text(encoding="utf-8")

    for element_id in (
        "h1AttentionMarkVisible",
        "h1AttentionOpenNextAction",
        "h1AttentionExportJson",
        "h1AttentionExportCsv",
    ):
        assert f'id="{element_id}"' in html

    assert "visibleHackerOneAttentionItems" in launcher
    assert "markVisibleHackerOneAttentionSeen" in launcher
    assert "openNextHackerOneActionRequired" in launcher
    assert "attentionExportRows" in launcher
    assert "exportHackerOneAttentionJson" in launcher
    assert "exportHackerOneAttentionCsv" in launcher
    assert "downloadAttentionExport" in launcher
    assert "URL.createObjectURL" in launcher
    assert "text/csv;charset=utf-8" in launcher
    assert "application/json;charset=utf-8" in launcher
    assert "notification_kind" in launcher
    assert "bounty_amount" in launcher
    assert "needs_more_info?.message" not in launcher.split("function attentionExportRows()", 1)[1].split("function downloadAttentionExport", 1)[0]
    assert "latest_public_activity?.message" not in launcher.split("function attentionExportRows()", 1)[1].split("function downloadAttentionExport", 1)[0]
    assert "notification_cursor" not in launcher.split("function attentionExportRows()", 1)[1].split("function downloadAttentionExport", 1)[0]


def test_frontend_supports_named_custom_hackerone_attention_views():
    html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    launcher = (ROOT / "frontend" / "hackerone.js").read_text(encoding="utf-8")

    for element_id in (
        "h1AttentionCustomView",
        "h1AttentionCustomViewName",
        "h1AttentionSaveCustomView",
        "h1AttentionDeleteCustomView",
    ):
        assert f'id="{element_id}"' in html

    assert 'maxlength="60"' in html
    assert "ATTENTION_CUSTOM_VIEWS_STORAGE_KEY" in launcher
    assert "xbow:hackerone:attention-custom-views:v1" in launcher
    assert "ATTENTION_CUSTOM_VIEW_LIMIT=20" in launcher
    assert "ATTENTION_CUSTOM_VIEW_NAME_LIMIT=60" in launcher
    assert "normalizeAttentionCustomViewName" in launcher
    assert "sanitizeAttentionCustomViewFilters" in launcher
    assert "loadHackerOneAttentionCustomViews" in launcher
    assert "saveHackerOneAttentionCustomViews" in launcher
    assert "renderHackerOneAttentionCustomViews" in launcher
    assert "selectedHackerOneAttentionCustomView" in launcher
    assert "saveCurrentHackerOneAttentionCustomView" in launcher
    assert "applySelectedHackerOneAttentionCustomView" in launcher
    assert "deleteSelectedHackerOneAttentionCustomView" in launcher
    assert "Maximum de 20 vues personnalisées atteint." in launcher
    assert "Nom de vue requis." in launcher


def test_frontend_exposes_hackerone_live_readiness_preflight():
    html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    launcher = (ROOT / "frontend" / "hackerone.js").read_text(encoding="utf-8")

    for element_id in (
        "h1LiveReadinessPanel",
        "h1LiveReadinessState",
        "h1LiveReadinessRefresh",
        "h1InterfaceUrl",
        "h1LiveReadinessSummary",
        "h1LiveReadinessChecks",
        "h1LiveReadinessNext",
    ):
        assert f'id="{element_id}"' in html

    assert "renderHackerOneLiveReadiness" in launcher
    assert "refreshHackerOneLiveReadiness" in launcher
    assert "'/hackerone/live-readiness'" in launcher
    assert "window.location.origin" in launcher
    assert "PRÊT SCAN RÉEL" in launcher
    assert "PRÊT POUR REVUE" in launcher
    assert "BLOQUÉ" in launcher
