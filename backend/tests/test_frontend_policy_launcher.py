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
