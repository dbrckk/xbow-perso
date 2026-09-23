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
    assert "/api/hackerone/simple-review-package" in schema["paths"]
    assert "/api/hackerone/journal" in schema["paths"]


def test_minimal_frontend_exposes_only_primary_operator_flow():
    html = _text("frontend/index.html")
    script = _text("frontend/simple.js")

    for element_id in ("token", "prepare", "selection", "mode", "start", "runtimeStatus", "runtimeAction", "status", "journal", "cancelActive", "refresh"):
        assert f'id="{element_id}"' in html

    assert '<script src="/simple.js?v=81" defer></script>' in html
    assert "Trouver 1 ou 2 bug bounties accessibles" in html
    assert "Toutes à la fois" in html
    assert "Une après l’autre" in html
    assert "/hackerone/simple-review-package" in script
    assert "/imports/hackerone/batches/launch-reviewed" in script
    assert "/imports/hackerone/batches/go-no-go" not in script
    assert "/hackerone/journal?limit=50" in script
    assert "void refreshRuntimeReadiness({quiet:true});" in script
    assert "void refreshJournal({quiet:true});" in script
    assert "},15000);" in script


def test_minimal_frontend_preserves_safety_and_server_persistence():
    html = _text("frontend/index.html")
    script = _text("frontend/simple.js")

    assert "valide leur politique si nécessaire" in html
    assert "revalidé juste avant son démarrage" in html
    assert "continue sur le serveur" in html
    assert "localStorage.setItem(TOKEN_KEY" in script
    assert "x-totp-code" not in script
    assert "hackerone.js" not in html


def test_minimal_launcher_rechecks_runtime_without_reselection():
    script = _text("frontend/simple.js")
    assert "void refreshRuntimeReadiness({quiet:true});" in script
    assert "updateStartAvailability();" in script
    assert "timer=setInterval" in script


def test_minimal_launcher_uses_single_final_reviewed_launch_request():
    script = _text("frontend/simple.js")
    start_block = script.split("async function start()", 1)[1].split("function repoSyncLabel", 1)[0]
    assert "/imports/hackerone/batches/launch-reviewed" in start_block
    assert "/imports/hackerone/batches/go-no-go" not in start_block
    assert "Validation finale serveur" in start_block
    assert "batch_go_no_go_blocked" in start_block
