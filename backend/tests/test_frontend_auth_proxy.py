from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_frontend_proxies_redacted_backend_diagnostics():
    nginx = _text("frontend/nginx.conf")
    for route in ("/auth-status", "/live", "/ready", "/health"):
        assert f"location {route}" in nginx
        assert f"proxy_pass http://backend:8000{route};" in nginx


def test_diagnostic_routes_bypass_service_worker_cache():
    sw = _text("frontend/sw.js")
    for route in ("/auth-status", "/live", "/ready", "/health"):
        assert route in sw
    assert "fetch(event.request)" in sw


def test_frontend_assets_are_explicitly_cache_busted():
    index = _text("frontend/index.html")
    sw = _text("frontend/sw.js")
    assert '/simple.js?v=78' in index
    assert '/app.css?v=78' in index
    assert "xbow-perso-v78" in sw


def test_api_token_is_persisted_across_browser_sessions():
    script = _text("frontend/simple.js")
    html = _text("frontend/index.html")
    assert "TOKEN_KEY='xbowApiToken'" in script
    assert "localStorage.getItem(TOKEN_KEY)" in script
    assert "localStorage.setItem(TOKEN_KEY" in script
    assert "Enregistré sur cet appareil." in html


def test_frontend_has_no_totp_control():
    script = _text("frontend/simple.js")
    html = _text("frontend/index.html")
    assert 'id="totp"' not in html
    assert "Code TOTP" not in html
    assert "x-totp-code" not in script



def test_simple_dashboard_runtime_is_shipped_in_frontend_image():
    dockerfile = _text("frontend/Dockerfile")
    index = _text("frontend/index.html")
    assert "COPY simple.js /usr/share/nginx/html/simple.js" in dockerfile
    assert '<script src="/simple.js?v=78" defer></script>' in index


def test_service_worker_matches_precache_assets_by_path():
    sw = _text("frontend/sw.js")
    assert "new URL(item,self.location.origin).pathname===url.pathname" in sw



def test_simple_dashboard_exposes_first_run_review_flow():
    script = _text("frontend/simple.js")
    html = _text("frontend/index.html")
    assert 'id="reviewPanel"' in html
    assert 'id="reviewList"' in html
    assert 'id="saveReviews"' in html
    assert "loadReviewDrafts" in script
    assert "saveReviews" in script
    assert "/review-draft" in script
    assert "/rules-preview" in script
    assert "review_profile_persisted" in script


def test_simple_dashboard_grouped_review_and_quiet_journal():
    script = _text("frontend/simple.js")
    html = _text("frontend/index.html")
    assert 'id="reviewAllConfirm"' in html
    assert "Valider les 6 programmes" in html
    assert "async function loadReviewDraft(handle)" in script
    assert "for(let attempt=0;attempt<2;attempt+=1)" in script
    assert "if(!quiet)setStatus('Journal indisponible : '+error.message,'err');" in script


def test_simple_dashboard_bounds_hackerone_review_concurrency():
    script = _text("frontend/simple.js")
    assert "const REVIEW_CONCURRENCY=2;" in script
    assert "retryableReviewError" in script
    assert "await sleep(1200);" in script
    assert "Promise.all(Array.from({length:workers},()=>reviewWorker()))" in script
    assert "Promise.allSettled(\n      candidates.map" not in script


def test_simple_dashboard_shows_review_loading_progress():
    script = _text("frontend/simple.js")
    assert "politiques vérifiées '+completed+'/'+total" in script
    assert "completed+=1;" in script
    assert "updateProgress();" in script
    assert "const total=candidates.length;" in script


def test_simple_dashboard_surfaces_live_scanner_readiness():
    script = _text("frontend/simple.js")
    html = _text("frontend/index.html")
    assert 'id="runtimeStatus"' in html
    assert 'id="runtimeAction"' in html
    assert "/hackerone/live-readiness" in script
    assert "Scanner : prêt pour les programmes autorisés." in script
    assert "Scanner : non prêt" in script
    assert "item?.required===true&&item?.ok!==true" in script


def test_simple_dashboard_bounds_review_profile_persistence():
    script = _text("frontend/simple.js")
    assert "async function persistReviewDraft(draft)" in script
    assert "Validation des profils '+completed+'/'+drafts.length" in script
    assert "const workers=Math.min(REVIEW_CONCURRENCY,drafts.length);" in script
    assert "await Promise.all(Array.from({length:workers},()=>persistWorker()))" in script
    assert "Lis les politiques affichées puis coche la confirmation groupée." in script
    assert "La politique de '+replaceable.length+' programme(s) a changé. Nouvelle sélection" in script


def test_start_button_requires_live_runtime_readiness():
    script = _text("frontend/simple.js")
    assert "let runtimeReady=false;" in script
    assert "function updateStartAvailability()" in script
    assert "selection.length===6" in script
    assert "runtimeReady===true" in script
    assert "runtimeReady=readiness?.live_scan_ready===true;" in script
    assert "runtimeReady=false;" in script
    assert "updateStartAvailability();" in script


def test_simple_dashboard_surfaces_runtime_remediation():
    script = _text("frontend/simple.js")
    assert "firstAction=String(failed[0]?.action||'').trim();" in script
    assert "scanner_start_command" in script
    assert "À faire : " in script
    assert "Tout est prêt côté runtime." in script


def test_simple_dashboard_prevents_duplicate_active_batches():
    script = _text("frontend/simple.js")
    assert "let batchActive=false;" in script
    assert "&& batchActive===false" in script
    assert "batchActive=true;" in script
    assert "batchActive=Boolean(active);" in script
    assert "localStorage.removeItem(ACTIVE_KEY)" in script
    assert "error?.reason===\'active_batch_exists\'" in script
    assert "Aucun doublon n’a été créé." in script


def test_simple_dashboard_reconciles_ambiguous_mobile_launch_response():
    script = _text("frontend/simple.js")
    start_block = script.split("async function start()", 1)[1].split("function repoSyncLabel", 1)[0]
    assert "Serveur inaccessible" in start_block
    assert "await refreshJournal({quiet:true});" in start_block
    assert "if(batchActive)" in start_block
    assert "le lot est bien actif côté serveur" in start_block


def test_simple_dashboard_can_cancel_active_hackerone_batch():
    script = _text("frontend/simple.js")
    html = _text("frontend/index.html")
    assert 'id="cancelActive"' in html
    assert "async function cancelActiveBatch()" in script
    assert "/imports/hackerone/batches/'+" in script
    assert "+'/cancel'" in script
    assert "activeBatchId=active?String(active?.id||''):'';" in script
    assert "Annuler le lot en cours" in html


def test_simple_dashboard_keeps_valid_review_drafts_across_replacement_rounds():
    script = _text("frontend/simple.js")
    assert "loadReviewDrafts(currentResult,draftCache)" in script
    assert "const draftCache=new Map();" in script
    assert "const cached=draftCache.get(handle);" in script
    assert "draftCache.set(handle,draft);" in script
    assert "politiques valides conservées en cache" in script
    assert "politiques vérifiées '+completed+'/'+total" in script


def test_simple_dashboard_preserves_valid_programmes_when_replacing_failures():
    script = _text("frontend/simple.js")
    assert "function replaceFailedSelection(current,replacements,failedHandles)" in script
    assert "const replacementExclude=[...new Set([...excluded,...currentHandles])];" in script
    assert "currentResult=replaceFailedSelection(previousResult,replacements,initialFailed);" in script
    assert "const merged=replaceFailedSelection(currentResult,replacements,failed);" in script
    assert "Remplacement ciblé de " in script
