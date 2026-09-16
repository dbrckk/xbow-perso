from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_frontend_requires_authorization_and_scope_review_before_launch():
    html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    javascript = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")

    required_ids = (
        "h1ScopeJson",
        "h1Auth",
        "h1PolicyVersion",
        "h1ReviewedAt",
        "h1ReviewedBy",
        "h1SafeHarbor",
        "h1Automation",
        "h1Rps",
        "h1Preview",
        "h1Confirm",
        "h1Launch",
        "h1PreviewCard",
    )
    for element_id in required_ids:
        assert f'id="{element_id}"' in html

    assert "api('/imports/hackerone/rules-preview'" in javascript
    assert 'id="h1Launch"' in html
