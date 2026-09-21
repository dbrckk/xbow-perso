from pathlib import Path

from app.main import app


ROOT = Path(__file__).resolve().parents[2]


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_hackerone_reviewed_batch_routes_exist():
    schema = app.openapi()
    assert "/api/imports/hackerone/batches/launch-reviewed" in schema["paths"]
    assert "/api/imports/hackerone/batches/go-no-go" in schema["paths"]
    assert "/api/hackerone/simple-selection" in schema["paths"]
    assert "/api/hackerone/journal" in schema["paths"]


def test_minimal_frontend_exposes_only_primary_operator_flow():
    html = _text("frontend/index.html")
    script = _text("frontend/simple.js")

    for element_id in ("token", "prepare", "selection", "mode", "start", "status", "journal", "refresh"):
        assert f'id="{element_id}"' in html

    assert '<script src="/simple.js?v=60" defer></script>' in html
    assert "2 faciles + 2 moyens + 2 fort potentiel" in html
    assert "Toutes à la fois" in html
    assert "Une après l’autre" in html
    assert "/hackerone/simple-selection" in script
    assert "/imports/hackerone/batches/launch-reviewed" in script
    assert "/hackerone/journal?limit=50" in script
    assert "setInterval(()=>void refreshJournal(),15000)" in script


def test_minimal_frontend_preserves_safety_and_server_persistence():
    html = _text("frontend/index.html")
    script = _text("frontend/simple.js")

    assert "déjà revus" in html
    assert "revalidé juste avant son démarrage" in html
    assert "continue sur le serveur" in html
    assert "localStorage.setItem(TOKEN_KEY" in script
    assert "x-totp-code" not in script
    assert "hackerone.js" not in html
