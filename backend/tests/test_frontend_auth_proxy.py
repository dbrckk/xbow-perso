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

    assert "/auth-status" in sw
    assert "/live" in sw
    assert "/ready" in sw
    assert "/health" in sw
    assert "fetch(event.request)" in sw


def test_frontend_assets_are_explicitly_cache_busted():
    index = _text("frontend/index.html")
    sw = _text("frontend/sw.js")

    assert '/app.js?v=59' in index
    assert '/hackerone.js?v=59' in index
    assert '/app.css?v=59' in index
    assert "xbow-perso-v59" in sw



def test_api_token_is_persisted_across_browser_sessions():
    app = _text("frontend/simple.js")
    html = _text("frontend/index.html")

    assert "API_TOKEN_STORAGE_KEY='xbowApiToken'" in app
    assert "localStorage.getItem(API_TOKEN_STORAGE_KEY)" in app
    assert "localStorage.setItem(API_TOKEN_STORAGE_KEY" in app
    assert "sessionStorage.getItem(API_TOKEN_STORAGE_KEY)" in app
    assert "sessionStorage.removeItem(API_TOKEN_STORAGE_KEY)" in app
    assert "Le jeton reste enregistré sur cet appareil." in html



def test_frontend_has_no_totp_control():
    app = _text("frontend/app.js")
    html = _text("frontend/index.html")

    assert 'id="totp"' not in html
    assert "Code TOTP" not in html
    assert "x-totp-code" not in app
    assert "$('totp')" not in app
