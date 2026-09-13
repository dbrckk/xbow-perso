from pathlib import Path


def _frontend() -> str:
    return (Path(__file__).resolve().parents[2] / "frontend" / "index.html").read_text(
        encoding="utf-8"
    )


def test_mobile_ui_exposes_guarded_pentagi_controls():
    html = _frontend()

    assert 'id="pentagi-preview"' in html
    assert 'id="pentagi-dispatch"' in html
    assert 'id="pentagi-refresh"' in html
    assert "/pentagi/preview" in html
    assert "/pentagi/dispatch" in html
    assert "+'/pentagi'" in html or "+'/pentagi');" in html
    assert "pentagiReady=Boolean(r.ready)" in html


def test_mobile_ui_does_not_accept_pentagi_runtime_configuration():
    html = _frontend()

    assert "XBOW_PENTAGI_BASE_URL" not in html
    assert "XBOW_PENTAGI_MODEL_PROVIDER" not in html
    assert "XBOW_PENTAGI_API_TOKEN" not in html
    assert 'id="pentagi-endpoint"' not in html
    assert 'id="pentagi-provider"' not in html


def test_mobile_ui_binds_preview_and_dispatch_to_same_campaign():
    html = _frontend()

    assert "let pentagiPreviewCampaignId=null" in html
    assert "const requestedCampaignId=campaign.id" in html
    assert "campaign.id!==requestedCampaignId" in html
    assert "pentagiPreviewCampaignId!==campaign.id" in html


def test_mobile_ui_reports_server_job_status():
    html = _frontend()

    assert "r.job.status" in html
    assert "Job PentAGI en file" not in html
