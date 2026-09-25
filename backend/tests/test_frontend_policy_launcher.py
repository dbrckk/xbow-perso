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

    assert '<script src="/simple.js?v=87" defer></script>' in html
    assert "Trouver un bug bounty accessible" in html
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


def test_htb_training_route_exists_and_frontend_keeps_it_separate_from_hackerone():
    schema = app.openapi()
    html = _text("frontend/index.html")
    script = _text("frontend/simple.js")
    assert "/api/labs/htb/campaigns" in schema["paths"]
    assert 'id="htbTarget"' in html
    assert "authorized_lab:true" in script
    assert "/imports/hackerone/batches/launch-reviewed" in script


def test_htb_benchmark_route_is_separate_from_hackerone_launch():
    schema = app.openapi()
    script = _text("frontend/simple.js")
    assert "/api/labs/htb/benchmark" in schema["paths"]
    assert "/labs/htb/benchmark" in script
    assert "/imports/hackerone/batches/launch-reviewed" in script


def test_htb_status_route_exists():
    assert "/api/labs/htb/campaigns/{campaign_id}/status" in app.openapi()["paths"]
