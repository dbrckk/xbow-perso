from pathlib import Path

from app.main import app


ROOT = Path(__file__).resolve().parents[2]


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_quick_console_exposes_minimal_operator_flow():
    html = _text("frontend/index.html")
    js = _text("frontend/quick.js")
    css = _text("frontend/app.css")

    for element_id in (
        "quickConsole",
        "quickSelect",
        "quickStart",
        "quickMessage",
        "quickSelection",
        "quickJournal",
        "quickJournalRefresh",
    ):
        assert f'id="{element_id}"' in html

    assert 'value="parallel" checked' in html
    assert 'value="sequential"' in html
    assert "/hackerone/quick/selection" in js
    assert "/hackerone/quick/launch" in js
    assert "/hackerone/quick/journal?limit=30" in js
    assert "setInterval(()=>void refreshJournal(),15000)" in js
    assert "quick-ui" in css
    assert "quick-token-ready" in css


def test_quick_console_surfaces_errors_instead_of_silent_buttons():
    js = _text("frontend/quick.js")

    assert "Sélection impossible :" in js
    assert "Démarrage bloqué :" in js
    assert "Journal indisponible :" in js
    assert "response.status===401||response.status===403" in js


def test_quick_backend_routes_are_exposed():
    paths = app.openapi()["paths"]

    assert "/api/hackerone/quick/selection" in paths
    assert "get" in paths["/api/hackerone/quick/selection"]
    assert "/api/hackerone/quick/launch" in paths
    assert "post" in paths["/api/hackerone/quick/launch"]
    assert "/api/hackerone/quick/journal" in paths
    assert "get" in paths["/api/hackerone/quick/journal"]


def test_quick_launch_remains_reviewed_and_revalidated_server_side():
    api_source = _text("backend/app/hackerone_api.py")

    assert "launch_reviewed_hackerone_batch" in api_source
    assert "Quick launch requires exactly six READY programs" in api_source
    assert "Quick selection changed; select the six programs again" in api_source
    assert "HackerOneReviewedBatchLaunchInput" in api_source
