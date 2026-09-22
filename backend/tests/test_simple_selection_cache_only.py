from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_simple_selection_never_refreshes_hackerone_inline():
    source = _text("backend/app/hackerone_api.py")
    block = source.split('@router.get("/api/hackerone/simple-selection")', 1)[1]
    block = block.split('@router.get("/api/hackerone/journal")', 1)[0]

    assert "get_hackerone_catalog_state()" in block
    assert "hackerone_catalog_not_initialized" in block
    assert "refresh_hackerone_catalog(" not in block
    assert '"catalog_source": "local-cache"' in block
    assert '"selection_requires_live_hackerone": False' in block


def test_simple_dashboard_initializes_catalog_once_then_retries_atomic_review_package():
    script = _text("frontend/simple.js")

    assert "hackerone_catalog_not_initialized" in script
    assert "/imports/hackerone/connection" in script
    assert "/imports/hackerone/programs?refresh=true" in script
    assert "/hackerone/simple-review-package" in script


def test_simple_dashboard_surfaces_actionable_hackerone_errors():
    script = _text("frontend/simple.js")

    assert "Connexion HackerOne absente sur le serveur" in script
    assert "Identifiants HackerOne refusés par HackerOne" in script
    assert "HackerOne est momentanément inaccessible" in script


def test_simple_selection_supports_excluding_unavailable_review_candidates():
    source = _text("backend/app/hackerone_api.py")
    block = source.split('@router.get("/api/hackerone/simple-selection")', 1)[1]
    block = block.split('@router.get("/api/hackerone/simple-review-package")', 1)[0]

    assert 'exclude: str = ""' in block
    assert "excluded_handles" in block
    assert '"excluded_handles": sorted(excluded_handles)' in block


def test_atomic_review_package_replaces_server_side_without_frontend_round_loop():
    source = _text("backend/app/hackerone_api.py")
    script = _text("frontend/simple.js")
    block = source.split('@router.get("/api/hackerone/simple-review-package")', 1)[1]
    block = block.split('@router.get("/api/hackerone/journal")', 1)[0]

    assert "draft_cache" in block
    assert "rejected" in block
    assert "ThreadPoolExecutor" in block
    assert "review_draft_is_usable" in block
    assert "review_package_rounds" in block
    prepare_block = script.split("async function prepare(", 1)[1].split("function reviewProfilePayload", 1)[0]
    assert "for(let round=" not in prepare_block
    assert "loadSimpleSelection(" not in prepare_block


def test_simple_dashboard_uses_launch_time_replacement_instead_of_duplicate_preflight():
    script = _text("frontend/simple.js")
    start_block = script.split("async function start()", 1)[1].split("function repoSyncLabel", 1)[0]
    assert "/imports/hackerone/batches/go-no-go" not in start_block
    assert "replaceableLaunchReason(error?.reason)" in start_block
    assert "await prepare(handles);" in start_block


def test_simple_dashboard_recovers_launch_time_programme_state_races():
    script = _text("frontend/simple.js")
    assert "function replaceableLaunchReason(reason)" in script
    assert "review_profile_required" in script
    assert "program_submissions_not_open" in script
    assert "stale_hackerone_snapshot" in script
    assert "hackerone_snapshot_document_mismatch" in script
    assert "Array.isArray(error?.detail?.handles)" in script
    assert "ont changé après le pré-vol. Remplacement automatique" in script
    assert "await prepare(handles);" in script


def test_simple_dashboard_surfaces_scanner_activation_command_on_preflight_block():
    script = _text("frontend/simple.js")
    assert "function preflightBlockerMessage(preflight)" in script
    assert "runtime?.scanner_start_command" in script
    assert "À exécuter sur le VPS" in script
    assert "Scanner non prêt" in script


def test_simple_dashboard_does_not_rerank_all_six_when_one_programme_fails():
    script = _text("frontend/simple.js")
    assert "function rebuildSimpleSelection(base,groups)" in script
    assert "function replaceFailedSelection(current,replacements,failedHandles)" in script
    assert "currentItems.filter(item=>" in script
    assert "return handle&&!failed.has(handle);" in script
    assert "if(nextGroups[key].length>=2)break;" in script
    assert "for(let round=0;round<8;round+=1)" in script
