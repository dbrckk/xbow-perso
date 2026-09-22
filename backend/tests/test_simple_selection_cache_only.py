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


def test_simple_dashboard_initializes_catalog_once_then_retries_selection():
    script = _text("frontend/simple.js")

    assert "async function loadSimpleSelection(excludedHandles=[])" in script
    assert "hackerone_catalog_not_initialized" in script
    assert "/imports/hackerone/connection" in script
    assert "/imports/hackerone/programs?refresh=true" in script
    assert "return await api('/hackerone/simple-selection'+query)" in script
    assert "Remplacement automatique de " in script


def test_simple_dashboard_surfaces_actionable_hackerone_errors():
    script = _text("frontend/simple.js")

    assert "Connexion HackerOne absente sur le serveur" in script
    assert "Identifiants HackerOne refusés par HackerOne" in script
    assert "HackerOne est momentanément inaccessible" in script



def test_simple_selection_supports_excluding_unavailable_review_candidates():
    source = _text("backend/app/hackerone_api.py")
    block = source.split('@router.get("/api/hackerone/simple-selection")', 1)[1]
    block = block.split('@router.get("/api/hackerone/journal")', 1)[0]

    assert 'exclude: str = ""' in block
    assert "excluded_handles" in block
    assert '"excluded_handles": sorted(excluded_handles)' in block


def test_simple_dashboard_replaces_individually_unavailable_review_programs():
    script = _text("frontend/simple.js")

    assert "const REVIEW_CONCURRENCY=2;" in script
    assert "reviewWorker" in script
    assert "hackerone_program_review_unavailable" in script
    assert "Remplacement automatique de " in script
    assert "loadSimpleSelection(excluded)" in script


def test_simple_dashboard_auto_replaces_preflight_stale_programmes():
    script = _text("frontend/simple.js")
    assert "async function prepare(initialExcluded=[])" in script
    assert "preflight?.replaceable_handles" in script
    assert "preflight?.runtime_ready===true&&replaceable.length" in script
    assert "await prepare(replaceable);" in script
    assert "programme(s) ont changé. Remplacement automatique" in script


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


def test_simple_dashboard_auto_replaces_loaded_but_incompatible_review_drafts():
    script = _text("frontend/simple.js")
    assert "if(reviewableDraft(draft))continue;" in script
    assert "if(handle&&!failedHandles.includes(handle))failedHandles.push(handle);" in script
    assert "if(failedHandles.length)return {failedHandles};" in script
